# -*- coding: utf-8 -*-
"""
════════════════════════════════════════════════════════════════════
 IP·AI 뉴스 브리핑 — 임원 보고용 대시보드 (모듈 3)
════════════════════════════════════════════════════════════════════
 조간신문 스타일 피드 + 기사 클릭 시 팝업으로 본문 표시
 좌측 내비게이션·기사 카드는 순수 HTML 링크(쿼리 파라미터) 기반
 실행: streamlit run app.py
════════════════════════════════════════════════════════════════════
"""

import base64
import hashlib
import html
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import altair as alt
import pandas as pd
import requests
import streamlit as st

KST = timezone(timedelta(hours=9))
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CONFIG_PATH = BASE_DIR / "config" / "keywords.json"

MOIP_CATEGORY = "지재처 보도자료"
DEFAULT_CONFIG = {
    "subscriptions": [
        {"name": "AI·지식재산", "groups": [["AI", "인공지능"], ["지식재산", "특허", "디자인"]]},
        {"name": "AI 업계", "groups": [["오픈AI", "챗GPT", "앤스로픽", "클로드", "제미나이", "엔비디아", "생성형 AI"]]},
    ]
}

# 카테고리 색: [차트색, 라이트모드 글자색, 다크모드 글자색]
MOIP_COLORS = ("#0072B2", "#075985", "#58b0e0")
SUB_COLOR_SETS = [
    ("#E69F00", "#b45309", "#eab308"),
    ("#009E73", "#047857", "#34d399"),
    ("#CC79A7", "#a21caf", "#e879f9"),
    ("#D55E00", "#c2410c", "#fb923c"),
    ("#56B4E9", "#0369a1", "#7dd3fc"),
]

st.set_page_config(
    page_title="IP·AI 뉴스 브리핑",
    page_icon="📰",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ════════════════════════════════════════════════════════════════════
# 설정(구독 키워드) 로드/저장
# ════════════════════════════════════════════════════════════════════

def get_secret(name: str, default: str = "") -> str:
    try:
        return str(st.secrets.get(name, default))
    except Exception:
        return default


@st.cache_data(ttl=60)
def load_config() -> dict:
    try:
        if CONFIG_PATH.exists():
            cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if cfg.get("subscriptions"):
                return cfg
    except Exception:
        pass
    return DEFAULT_CONFIG


def save_config(cfg: dict) -> tuple[bool, str]:
    """로컬 저장 + (Secrets에 토큰이 있으면) GitHub 저장소에 영구 커밋"""
    text = json.dumps(cfg, ensure_ascii=False, indent=2)
    try:
        CONFIG_PATH.parent.mkdir(exist_ok=True)
        CONFIG_PATH.write_text(text, encoding="utf-8")
    except Exception as e:
        return False, f"저장 실패: {e}"

    token = get_secret("GITHUB_TOKEN")
    repo = get_secret("GITHUB_REPO", "UNJUNGSAM/ip-ai-news-brief")
    if not token:
        return True, "⚠️ 임시 저장만 되었습니다. 영구 저장하려면 관리자가 Streamlit Secrets에 GITHUB_TOKEN을 등록해야 합니다."

    try:
        api = f"https://api.github.com/repos/{repo}/contents/config/keywords.json"
        h = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
        sha = None
        r = requests.get(api, headers=h, timeout=15)
        if r.status_code == 200:
            sha = r.json().get("sha")
        payload = {
            "message": "chore: 구독 키워드 설정 변경 (대시보드에서 저장)",
            "content": base64.b64encode(text.encode()).decode(),
        }
        if sha:
            payload["sha"] = sha
        r2 = requests.put(api, headers=h, json=payload, timeout=15)
        if r2.status_code in (200, 201):
            return True, "✅ 영구 저장 완료 — 내일 아침 자동 수집부터 새 키워드가 적용됩니다."
        return False, f"GitHub 저장 실패 (HTTP {r2.status_code})"
    except Exception as e:
        return False, f"GitHub 저장 실패: {e}"


config = load_config()
SUBS = config.get("subscriptions", [])
SUB_NAMES = [s.get("name", f"구독{i+1}") for i, s in enumerate(SUBS)]
ALL_CATEGORIES = [MOIP_CATEGORY] + SUB_NAMES

CAT_CHART = {MOIP_CATEGORY: MOIP_COLORS[0]}
CAT_CSS_CLASS = {MOIP_CATEGORY: "c-moip"}
for i, n in enumerate(SUB_NAMES):
    CAT_CHART[n] = SUB_COLOR_SETS[i % len(SUB_COLOR_SETS)][0]
    CAT_CSS_CLASS[n] = f"c-sub{i % len(SUB_COLOR_SETS)}"

if "reader_font" not in st.session_state:
    st.session_state.reader_font = 17

# ════════════════════════════════════════════════════════════════════
# CSS — 조간신문 에디토리얼 스타일 (v1), 라이트/다크 자동
# ════════════════════════════════════════════════════════════════════

sub_css_light = "\n".join(
    f".c-sub{i} {{ color: {c[1]}; }}" for i, c in enumerate(SUB_COLOR_SETS)
)
sub_css_dark = "\n".join(
    f".c-sub{i} {{ color: {c[2]}; }}" for i, c in enumerate(SUB_COLOR_SETS)
)

st.markdown(f"""
<style>
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css');
@import url('https://fonts.googleapis.com/css2?family=Noto+Serif+KR:wght@600;700;900&display=swap');

:root {{
    --font-body: 'Pretendard Variable', Pretendard, 'Malgun Gothic', sans-serif;
    --font-display: 'Noto Serif KR', 'Batang', serif;
    --reader-size: {st.session_state.reader_font}px;

    --page-bg: #f7f5f0;
    --card-bg: #ffffff;
    --ink: #191c22;
    --ink-2: #555d68;
    --ink-3: #9199a5;
    --rule: #191c22;
    --hair: #e3e0d8;
    --pill-bg: #f0ede6;
    --pill-ink: #6b7280;
    --accent: #0b57d0;
    --accent-soft: #eef3fd;
    --card-shadow: 0 1px 2px rgba(25,28,34,.05), 0 4px 14px rgba(25,28,34,.06);
    .c-moip {{ color: #075985; }}
    {sub_css_light}
}}
@media (prefers-color-scheme: dark) {{
    :root {{
        --page-bg: #15171c;
        --card-bg: #1e2128;
        --ink: #eceef2;
        --ink-2: #a8b0bc;
        --ink-3: #767e8a;
        --rule: #eceef2;
        --hair: #32363f;
        --pill-bg: #2a2e37;
        --pill-ink: #a8b0bc;
        --accent: #7c96ff;
        --accent-soft: #232a44;
        --card-shadow: 0 1px 2px rgba(0,0,0,.4), 0 4px 14px rgba(0,0,0,.3);
        .c-moip {{ color: #58b0e0; }}
        {sub_css_dark}
    }}
}}

.stApp {{ background: var(--page-bg); }}
html, body, [class*="css"] {{ font-family: var(--font-body); }}
#MainMenu, footer {{ visibility: hidden; }}
header[data-testid="stHeader"] {{ display: none; }}
.block-container {{ padding-top: 1.2rem; max-width: 1200px; }}

/* ── 마스트헤드 (신문 제호) ─────────────────────────── */
.masthead {{ text-align: center; padding: .2rem 0 .7rem; }}
.masthead .kicker {{
    font-size: .75rem; letter-spacing: .35em; color: var(--ink-3);
    text-transform: uppercase; margin-bottom: .3rem;
}}
.masthead h1 {{
    font-family: var(--font-display); font-weight: 900;
    font-size: clamp(1.7rem, 4vw, 2.5rem); color: var(--ink);
    margin: 0; line-height: 1.15;
}}
.masthead .dateline {{ font-size: .85rem; color: var(--ink-2); margin-top: .45rem; }}
.masthead-rule {{
    border-top: 3px solid var(--rule); border-bottom: 1px solid var(--rule);
    height: 3px; margin: .3rem 0 1.1rem;
}}

/* ── 좌측 내비게이션 (링크 기반) ────────────────────── */
.rail {{ position: sticky; top: .8rem; }}
.rail .sec {{
    font-size: .7rem; font-weight: 800; letter-spacing: .18em; color: var(--ink-3);
    text-transform: uppercase; margin: 1rem 0 .35rem .4rem;
}}
.rail a {{
    display: flex; justify-content: space-between; align-items: center;
    padding: .42rem .7rem; border-radius: 10px; margin-bottom: 2px;
    text-decoration: none; color: var(--ink-2); font-size: .92rem; font-weight: 600;
}}
.rail a:hover {{ background: var(--accent-soft); color: var(--ink); }}
.rail a.on {{ background: var(--card-bg); color: var(--ink); box-shadow: var(--card-shadow); font-weight: 800; }}
.rail a .n {{ font-size: .74rem; color: var(--ink-3); font-weight: 600; }}
.rail .dot {{ display:inline-block; width:9px; height:9px; border-radius:50%; margin-right:.5rem; }}

/* ── 통계 타일 ─────────────────────────────────────── */
.stat-row {{ display: flex; gap: .7rem; margin-bottom: 1rem; flex-wrap: wrap; }}
.stat-tile {{
    flex: 1 1 120px; background: var(--card-bg); border-radius: 14px;
    padding: .75rem 1rem; box-shadow: var(--card-shadow); border-top: 3px solid var(--hair);
}}
.stat-tile .label {{ font-size: .75rem; color: var(--ink-3); font-weight: 600; }}
.stat-tile .value {{
    font-family: var(--font-display); font-size: 1.55rem; font-weight: 700; color: var(--ink);
}}

/* ── 기사 카드 (제목·언론사·날짜·키워드만) ──────────── */
.feed a.news-card {{
    display: block; background: var(--card-bg); border-radius: 15px;
    padding: 1rem 1.25rem .9rem; box-shadow: var(--card-shadow);
    margin-bottom: .65rem; text-decoration: none;
    border: 1px solid transparent; transition: border-color .12s, transform .08s;
}}
.feed a.news-card:hover {{ border-color: var(--accent); }}
.feed a.news-card:active {{ transform: scale(.995); }}
.news-meta {{
    font-size: .78rem; color: var(--ink-3); margin-bottom: .25rem;
    display: flex; align-items: center; gap: .45rem; flex-wrap: wrap;
}}
.cat-kicker {{ font-weight: 800; letter-spacing: .05em; font-size: .77rem; }}
.news-title {{
    font-family: var(--font-display); font-weight: 700;
    font-size: 1.08rem; color: var(--ink); line-height: 1.42; word-break: keep-all;
}}
.tag-row {{ display: flex; gap: .3rem; flex-wrap: wrap; margin-top: .5rem; }}
.tag-pill {{
    background: var(--pill-bg); color: var(--pill-ink);
    border-radius: 999px; padding: .14rem .6rem; font-size: .72rem; font-weight: 600;
}}

/* ── 기사 팝업(다이얼로그) 내부 ─────────────────────── */
.reader-meta {{ display:flex; align-items:center; gap:.5rem; font-size:.82rem; color:var(--ink-3); margin-bottom:.5rem; flex-wrap:wrap; }}
.reader-chip {{ font-weight:800; font-size:.76rem; padding:.14rem .6rem; border-radius:999px; color:#fff; }}
.reader-title {{
    font-family: var(--font-display); font-size:1.4rem; font-weight:800;
    color:var(--ink); line-height:1.35; margin:.1rem 0 .7rem; word-break:keep-all;
}}
.reader-title a {{ color: var(--ink); text-decoration: none; }}
.reader-title a:hover {{ color: var(--accent); }}
.reader-summary {{
    background: var(--accent-soft); border-radius: 12px; padding: .75rem 1rem;
    font-size: calc(var(--reader-size) * .93); color: var(--ink-2); line-height:1.6;
    margin-bottom: .9rem; word-break: keep-all;
}}
.reader-body p {{
    font-size: var(--reader-size); color: var(--ink-2); line-height: 1.78;
    margin-bottom: .85rem; word-break: keep-all; overflow-wrap: anywhere;
}}
.open-btn {{
    display:inline-block; background: var(--accent); color:#fff !important;
    font-weight:700; font-size:.92rem; padding:.55rem 1.15rem; border-radius:11px;
    text-decoration:none;
}}
.open-btn:hover {{ filter: brightness(1.1); }}

.section-label {{
    font-size:.78rem; font-weight:800; letter-spacing:.2em; color:var(--ink-3);
    text-transform:uppercase; margin:.3rem 0 .55rem .1rem;
}}
.stTextInput input {{ border-radius: 12px !important; }}

/* 갤럭시탭 세로모드 등 좁은 화면: 레일을 위로 쌓기 */
@media (max-width: 860px) {{
    div[data-testid="stHorizontalBlock"] {{ flex-wrap: wrap; }}
    div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {{ min-width: 100% !important; }}
    .rail {{ position: static; }}
    .rail a {{ display: inline-flex; gap:.4rem; margin-right:.25rem; }}
}}
</style>
""", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════════
# 데이터 로드
# ════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=600, show_spinner="뉴스 데이터를 불러오는 중...")
def load_news() -> pd.DataFrame:
    rows = []
    if DATA_DIR.exists():
        for f in sorted(DATA_DIR.glob("news_*.json")):
            try:
                for item in json.loads(f.read_text(encoding="utf-8")):
                    rows.append({
                        "title": item.get("title", ""),
                        "link": item.get("link", ""),
                        "category": item.get("category", "기타"),
                        "date": item.get("date", ""),
                        "summary": item.get("summary", ""),
                        "content": item.get("content", ""),
                        "source": item.get("source", "-"),
                        "keywords": item.get("keywords", []),
                    })
            except Exception:
                continue
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.drop_duplicates(subset=["link"]).drop_duplicates(subset=["title"])
    df["id"] = df["link"].map(lambda x: hashlib.md5(str(x).encode()).hexdigest()[:10])
    df["date_dt"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date_dt"])
    cat_order = {c: i for i, c in enumerate(ALL_CATEGORIES)}
    df["_rank"] = df["category"].map(cat_order).fillna(99)
    df = df.sort_values(["date_dt", "_rank"], ascending=[False, True]).drop(columns="_rank")
    return df.reset_index(drop=True)


df = load_news()
today = datetime.now(KST).date()


def human_date(d) -> str:
    dd = d.date() if hasattr(d, "date") else d
    if dd == today:
        return "오늘"
    if dd == today - timedelta(days=1):
        return "어제"
    return f"{dd.month}.{dd.day}" if dd.year == today.year else f"{dd.year}.{dd.month}.{dd.day}"


# ════════════════════════════════════════════════════════════════════
# URL 상태 (view / cat / src / sel)
# ════════════════════════════════════════════════════════════════════

VIEWS = {"today": "오늘", "week": "최근 7일", "all": "전체 기사", "trend": "트렌드"}
qp = st.query_params
view = qp.get("view", "week")
if view not in VIEWS:
    view = "week"
sel_cat = qp.get("cat", "전체")
sel_src = qp.get("src", "전체")
sel_id = qp.get("sel", "")
if sel_id:
    # 팝업을 한 번만 띄우기 위해 URL에서 제거 (닫은 뒤 재실행 시 다시 열리지 않도록)
    try:
        del st.query_params["sel"]
    except Exception:
        pass


def make_url(**over) -> str:
    params = {"view": view, "cat": sel_cat, "src": sel_src}
    params.update(over)
    parts = []
    for k, v in params.items():
        v = str(v)
        if not v or v == "전체" or (k == "view" and v == "week" and "sel" not in over):
            if k != "view":
                continue
        parts.append(f"{k}={quote(v)}")
    return "?" + "&".join(parts)


# 기간 필터
if df.empty:
    df_v = df
elif view == "today":
    df_v = df[df["date_dt"].dt.date >= today]
elif view == "week":
    df_v = df[df["date_dt"].dt.date >= today - timedelta(days=6)]
else:
    df_v = df

# ════════════════════════════════════════════════════════════════════
# 기사 팝업 (다이얼로그)
# ════════════════════════════════════════════════════════════════════

@st.dialog(" ", width="large")
def article_dialog(row):
    color = CAT_CHART.get(row["category"], "#666")
    title_esc = html.escape(row["title"])
    link_esc = html.escape(row["link"], quote=True)
    date_str = row["date_dt"].strftime("%Y.%m.%d")

    body_text = row["content"] or ""
    summary_text = row["summary"] if row["summary"] != row["title"] else ""
    if body_text:
        sents = re.split(r"(?<=다\.)\s+", body_text)
        chunks = [" ".join(sents[j:j + 3]).strip() for j in range(0, len(sents), 3)]
        paras_html = "".join(f"<p>{html.escape(c)}</p>" for c in chunks if c)
    elif summary_text:
        paras_html = f"<p>{html.escape(summary_text)}</p>"
    else:
        paras_html = '<p style="color:var(--ink-3)">본문 미리보기가 없는 기사입니다. 아래 버튼으로 원문을 확인하세요.</p>'

    summary_html = ""
    if summary_text and body_text:
        summary_html = f'<div class="reader-summary"><b>요약</b> — {html.escape(summary_text)}</div>'

    st.markdown(f"""
<div class="reader-meta">
  <span class="reader-chip" style="background:{color}">{html.escape(row['category'])}</span>
  <span>{html.escape(str(row['source']))}</span><span>·</span><span>{date_str}</span>
</div>
<div class="reader-title"><a href="{link_esc}" target="_blank" rel="noopener">{title_esc}</a></div>
{summary_html}
<div class="reader-body">{paras_html}</div>
<div style="margin-top:.9rem;"><a class="open-btn" href="{link_esc}" target="_blank" rel="noopener">원문 기사 열기 ↗</a></div>
""", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════
# 설정 다이얼로그
# ════════════════════════════════════════════════════════════════════

@st.dialog("설정", width="large")
def settings_dialog():
    fs = st.slider("본문 글자 크기", 13, 24, value=st.session_state.reader_font, key="reader_font_widget")
    st.session_state.reader_font = fs
    st.divider()
    st.markdown("##### 구독 키워드")
    if get_secret("GITHUB_TOKEN"):
        st.caption("영구 저장 사용 가능 — 저장하면 모든 사용자에게 적용되고, 다음날 수집부터 반영됩니다.")
    else:
        st.caption("현재 임시 저장만 가능합니다. 관리자가 Streamlit Secrets에 GITHUB_TOKEN을 등록하면 영구 저장됩니다.")
    st.caption(
        "쉼표(,) = 같은 의미(OR) · 세미콜론(;) = 반드시 함께(AND)  \n"
        "예: `AI, 인공지능 ; 지식재산, 특허, 디자인` → (AI 또는 인공지능) 이면서 (지식재산·특허·디자인 중 하나)"
    )
    rows = [
        {"구독명": s.get("name", ""), "키워드": " ; ".join(", ".join(g) for g in s.get("groups", []))}
        for s in SUBS
    ]
    edited = st.data_editor(
        pd.DataFrame(rows, columns=["구독명", "키워드"]),
        num_rows="dynamic", hide_index=True, width="stretch", key="kw_editor",
    )
    st.caption("행 추가(+)로 구독을 늘릴 수 있습니다. 지재처 보도자료는 키워드와 무관하게 항상 전량 수집됩니다.")
    if st.button("저장", type="primary", width="stretch"):
        subs = []
        for _, r in edited.iterrows():
            name = str(r.get("구독명") or "").strip()
            kw = str(r.get("키워드") or "").strip()
            if not name or not kw or kw == "None":
                continue
            groups = [[w.strip() for w in g.split(",") if w.strip()] for g in kw.split(";")]
            groups = [g for g in groups if g]
            if groups:
                subs.append({"name": name, "groups": groups})
        if not subs:
            st.error("구독이 최소 1개 필요합니다.")
            return
        ok, msg = save_config({"subscriptions": subs})
        if ok:
            st.success(msg)
            load_config.clear()
        else:
            st.error(msg)


# ════════════════════════════════════════════════════════════════════
# 마스트헤드
# ════════════════════════════════════════════════════════════════════

WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]
dateline = f"{today.year}년 {today.month}월 {today.day}일 {WEEKDAYS[today.weekday()]}요일"
st.markdown(f"""
<div class="masthead">
    <div class="kicker">Daily Executive Briefing</div>
    <h1>IP·AI 뉴스 브리핑</h1>
    <div class="dateline">{dateline} · 지식재산 &amp; 인공지능 정책·기술 동향</div>
</div>
<div class="masthead-rule"></div>
""", unsafe_allow_html=True)

if df.empty:
    st.info("아직 수집된 뉴스가 없습니다. `python data_pipeline.py`를 실행하세요.")
    st.stop()

# ════════════════════════════════════════════════════════════════════
# 레이아웃: [내비게이션 | 피드]
# ════════════════════════════════════════════════════════════════════

rail_col, feed_col = st.columns([1, 3.7], gap="medium")

with rail_col:
    counts = df_v["category"].value_counts()
    nav = ['<div class="rail">']
    nav.append('<div class="sec">보기</div>')
    for k, label in VIEWS.items():
        on = " on" if view == k else ""
        nav.append(f'<a class="{on}" href="{make_url(view=k)}" target="_self">{label}</a>')
    nav.append('<div class="sec">카테고리</div>')
    on = " on" if sel_cat == "전체" else ""
    nav.append(f'<a class="{on}" href="{make_url(cat="전체")}" target="_self">전체 보기 <span class="n">{len(df_v)}</span></a>')
    for c in ALL_CATEGORIES:
        on = " on" if sel_cat == c else ""
        dot = CAT_CHART.get(c, "#999")
        nav.append(
            f'<a class="{on}" href="{make_url(cat=c)}" target="_self">'
            f'<span><span class="dot" style="background:{dot}"></span>{html.escape(c)}</span>'
            f'<span class="n">{counts.get(c, 0)}</span></a>'
        )
    top_srcs = df_v["source"].value_counts().head(10)
    if len(top_srcs) > 1:
        nav.append('<div class="sec">소스</div>')
        on = " on" if sel_src == "전체" else ""
        nav.append(f'<a class="{on}" href="{make_url(src="전체")}" target="_self">전체</a>')
        for s, cnt in top_srcs.items():
            on = " on" if sel_src == s else ""
            nav.append(f'<a class="{on}" href="{make_url(src=s)}" target="_self">{html.escape(str(s))} <span class="n">{cnt}</span></a>')
    nav.append("</div>")
    st.markdown("".join(nav), unsafe_allow_html=True)
    st.write("")
    if st.button("키워드 설정", width="stretch"):
        settings_dialog()

# ── 필터 적용 ──────────────────────────────────────────
filtered = df_v
if sel_cat != "전체":
    filtered = filtered[filtered["category"] == sel_cat]
if sel_src != "전체":
    filtered = filtered[filtered["source"] == sel_src]

with feed_col:
    # ── 트렌드 뷰 ─────────────────────────────────────
    if view == "trend":
        st.markdown('<div class="section-label">Trend — 누적 수집 데이터</div>', unsafe_allow_html=True)
        st.markdown("##### 일자별 수집 기사 (최근 14일)")
        t = df[df["date_dt"].dt.date >= today - timedelta(days=13)]
        daily = t.groupby([t["date_dt"].dt.strftime("%m/%d"), "category"]).size().reset_index(name="count")
        daily.columns = ["날짜", "카테고리", "기사 수"]
        chart1 = (
            alt.Chart(daily)
            .mark_bar(size=20)
            .encode(
                x=alt.X("날짜:O", title=None, axis=alt.Axis(labelAngle=0)),
                y=alt.Y("기사 수:Q", title=None),
                color=alt.Color("카테고리:N",
                                scale=alt.Scale(domain=ALL_CATEGORIES,
                                                range=[CAT_CHART[c] for c in ALL_CATEGORIES]),
                                legend=alt.Legend(orient="top", title=None)),
                tooltip=["날짜", "카테고리", "기사 수"],
            )
            .properties(height=280)
        )
        st.altair_chart(chart1, width="stretch")

        st.markdown("##### 핵심 키워드 Top 12 (최근 7일)")
        kws = df[df["date_dt"].dt.date >= today - timedelta(days=6)].explode("keywords")["keywords"].dropna()
        if not kws.empty:
            kt = kws.value_counts().head(12).reset_index()
            kt.columns = ["키워드", "빈도"]
            chart2 = (
                alt.Chart(kt)
                .mark_bar(size=16, cornerRadiusEnd=4, color=MOIP_COLORS[0])
                .encode(x=alt.X("빈도:Q", title=None),
                        y=alt.Y("키워드:N", sort="-x", title=None),
                        tooltip=["키워드", "빈도"])
                .properties(height=300)
            )
            st.altair_chart(chart2, width="stretch")
        with st.expander("데이터 표로 보기"):
            st.dataframe(
                df[["date", "category", "source", "title", "link"]]
                .rename(columns={"date": "날짜", "category": "카테고리", "source": "소스", "title": "제목", "link": "링크"}),
                width="stretch", hide_index=True,
                column_config={"링크": st.column_config.LinkColumn("링크", display_text="원문 열기")},
            )
    else:
        # ── 피드 뷰 ───────────────────────────────────
        cat_counts = df_v["category"].value_counts()
        tiles = [f'<div class="stat-tile"><div class="label">수집 기사 ({VIEWS[view]})</div><div class="value">{len(df_v):,}</div></div>']
        for c in ALL_CATEGORIES[:3]:
            tiles.append(
                f'<div class="stat-tile" style="border-top-color:{CAT_CHART.get(c, "#999")}">'
                f'<div class="label">{html.escape(c)}</div><div class="value">{cat_counts.get(c, 0)}</div></div>'
            )
        st.markdown(f'<div class="stat-row">{"".join(tiles)}</div>', unsafe_allow_html=True)

        q = st.text_input("검색", placeholder="검색 — 제목·요약·본문에서 찾습니다",
                          label_visibility="collapsed", key="search_q")
        if q.strip():
            qq = q.strip().lower()
            filtered = filtered[
                filtered["title"].str.lower().str.contains(qq, regex=False)
                | filtered["summary"].str.lower().str.contains(qq, regex=False)
                | filtered["content"].str.lower().str.contains(qq, regex=False)
            ]

        n = len(filtered)
        st.markdown(f'<div class="section-label">기사 {n}건 · 카드를 누르면 본문이 열립니다</div>', unsafe_allow_html=True)
        if n == 0:
            st.warning("조건에 맞는 기사가 없습니다.")
        MAX_SHOW = 80
        cards = ['<div class="feed">']
        for _, r in filtered.head(MAX_SHOW).iterrows():
            cat_cls = CAT_CSS_CLASS.get(r["category"], "")
            tags = "".join(f'<span class="tag-pill">#{html.escape(k)}</span>' for k in r["keywords"][:5])
            tags_html = f'<div class="tag-row">{tags}</div>' if tags else ""
            cards.append(
                f'<a class="news-card" href="{make_url(sel=r["id"])}" target="_self">'
                f'<div class="news-meta"><span class="cat-kicker {cat_cls}">{html.escape(r["category"])}</span>'
                f'<span>·</span><span>{html.escape(str(r["source"]))}</span><span>·</span><span>{human_date(r["date_dt"])}</span></div>'
                f'<div class="news-title">{html.escape(r["title"])}</div>'
                f'{tags_html}</a>'
            )
        cards.append("</div>")
        st.markdown("".join(cards), unsafe_allow_html=True)
        if n > MAX_SHOW:
            st.caption(f"상위 {MAX_SHOW}건 표시 중 (전체 {n}건) — 검색·필터로 좁혀 보세요.")

    st.markdown(
        f'<div style="text-align:center; color:var(--ink-3); font-size:.75rem; padding:1.2rem 0 .4rem;">'
        f'매일 오전 7시 자동 수집 · 누적 {len(df):,}건 · 마지막 수집 {df["date_dt"].max().strftime("%Y.%m.%d")}</div>',
        unsafe_allow_html=True,
    )

# ── 기사 팝업 열기 (URL에 sel이 있었을 때) ─────────────
if sel_id:
    hit = df[df["id"] == sel_id]
    if not hit.empty:
        article_dialog(hit.iloc[0])
