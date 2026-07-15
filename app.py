# -*- coding: utf-8 -*-
"""
════════════════════════════════════════════════════════════════════
 IP·AI 뉴스 브리핑 — 3단 리더 대시보드 (모듈 3)
════════════════════════════════════════════════════════════════════
 좌측: 카테고리·소스  |  가운데: 기사 목록  |  우측: 본문 리딩 패널
 실행: streamlit run app.py
 데이터: data/news_YYYYMMDD.json  ·  구독 키워드: config/keywords.json
════════════════════════════════════════════════════════════════════
"""

import base64
import html
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

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
        {"name": "AI·지식재산", "groups": [["AI", "인공지능"], ["지식재산", "특허", "디자인"]]}
    ]
}

# 카테고리 색 (색각이상 안전 팔레트) — 지재처 고정 + 구독은 순서대로
MOIP_COLOR = "#0072B2"
SUB_PALETTE = ["#E69F00", "#009E73", "#CC79A7", "#D55E00", "#56B4E9"]
MOIP_DOT = "🔵"
SUB_DOTS = ["🟠", "🟢", "🟣", "🔴", "🔹"]

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
    """로컬 저장 + (Secrets에 토큰이 있으면) GitHub 저장소에 커밋"""
    text = json.dumps(cfg, ensure_ascii=False, indent=2)
    try:
        CONFIG_PATH.parent.mkdir(exist_ok=True)
        CONFIG_PATH.write_text(text, encoding="utf-8")
    except Exception as e:
        return False, f"저장 실패: {e}"

    token = get_secret("GITHUB_TOKEN")
    repo = get_secret("GITHUB_REPO", "UNJUNGSAM/ip-ai-news-brief")
    if not token:
        return True, "이 기기에 저장했습니다. (웹 배포에서 매일 수집에 반영하려면 Secrets에 GITHUB_TOKEN 등록 필요)"

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
            return True, "저장 완료 — 내일 아침 자동 수집부터 새 키워드가 적용됩니다."
        return False, f"GitHub 저장 실패 (HTTP {r2.status_code})"
    except Exception as e:
        return False, f"GitHub 저장 실패: {e}"


config = load_config()
SUBS = config.get("subscriptions", [])
SUB_NAMES = [s.get("name", f"구독{i+1}") for i, s in enumerate(SUBS)]
ALL_CATEGORIES = [MOIP_CATEGORY] + SUB_NAMES
CAT_COLORS = {MOIP_CATEGORY: MOIP_COLOR, **{n: SUB_PALETTE[i % len(SUB_PALETTE)] for i, n in enumerate(SUB_NAMES)}}
CAT_DOTS = {MOIP_CATEGORY: MOIP_DOT, **{n: SUB_DOTS[i % len(SUB_DOTS)] for i, n in enumerate(SUB_NAMES)}}

if "reader_font" not in st.session_state:
    st.session_state.reader_font = 16

# ════════════════════════════════════════════════════════════════════
# CSS — 뉴스 리더 앱 스타일 (라이트/다크 자동)
# ════════════════════════════════════════════════════════════════════

st.markdown(f"""
<style>
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css');

:root {{
    --font: 'Pretendard Variable', Pretendard, 'Malgun Gothic', sans-serif;
    --reader-size: {st.session_state.reader_font}px;
    --page-bg: #f4f5f8;
    --card-bg: #ffffff;
    --line: #e6e8ee;
    --ink: #14171e;
    --ink-2: #545b68;
    --ink-3: #8b93a2;
    --accent: #2f54eb;
    --accent-soft: #eef2ff;
    --shadow: 0 1px 2px rgba(20,23,30,.04), 0 6px 20px rgba(20,23,30,.05);
}}
@media (prefers-color-scheme: dark) {{
    :root {{
        --page-bg: #101216;
        --card-bg: #1a1d24;
        --line: #2b2f38;
        --ink: #edeff3;
        --ink-2: #aab1bd;
        --ink-3: #737b89;
        --accent: #7c96ff;
        --accent-soft: #232a44;
        --shadow: 0 1px 2px rgba(0,0,0,.4), 0 6px 20px rgba(0,0,0,.35);
    }}
}}

.stApp {{ background: var(--page-bg); }}
html, body, [class*="css"] {{ font-family: var(--font); }}
#MainMenu, footer {{ visibility: hidden; }}
.block-container {{ padding: .9rem 1.4rem 2rem; max-width: 1600px; }}

/* ── 좌측 레일 고정(sticky) ─────────────────────────── */
div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:first-of-type > div {{
    position: sticky; top: .8rem;
}}

/* 앱 로고 */
.app-logo {{ display:flex; align-items:center; gap:.5rem; padding:.2rem .3rem .9rem; }}
.app-logo .mark {{
    width: 34px; height: 34px; border-radius: 10px; background: var(--accent);
    color:#fff; display:flex; align-items:center; justify-content:center;
    font-size:1.05rem; font-weight:800; box-shadow: var(--shadow);
}}
.app-logo .name {{ font-weight: 800; font-size: 1.02rem; color: var(--ink); line-height:1.2; }}
.app-logo .sub {{ font-size: .68rem; color: var(--ink-3); letter-spacing:.14em; }}

.rail-label {{
    font-size:.7rem; font-weight:800; letter-spacing:.16em; color:var(--ink-3);
    text-transform:uppercase; margin:.9rem 0 .25rem .3rem;
}}

/* ── 라디오 공통: 동그라미 숨기고 메뉴/카드처럼 ─────── */
div[role="radiogroup"] label[data-baseweb="radio"] > div:first-child {{ display:none; }}
div[role="radiogroup"] label[data-baseweb="radio"] {{ width:100%; margin-right:0; }}

/* 좌측 레일 메뉴 스타일 */
.st-key-nav_view div[role="radiogroup"] label[data-baseweb="radio"],
.st-key-nav_cat  div[role="radiogroup"] label[data-baseweb="radio"] {{
    padding:.42rem .65rem; border-radius:10px; margin-bottom:2px;
    transition: background .12s;
}}
.st-key-nav_view div[role="radiogroup"] label[data-baseweb="radio"]:hover,
.st-key-nav_cat  div[role="radiogroup"] label[data-baseweb="radio"]:hover {{ background: var(--accent-soft); }}
.st-key-nav_view div[role="radiogroup"] label[data-baseweb="radio"]:has(input:checked),
.st-key-nav_cat  div[role="radiogroup"] label[data-baseweb="radio"]:has(input:checked) {{
    background: var(--card-bg); box-shadow: var(--shadow);
}}
.st-key-nav_view div[role="radiogroup"] p, .st-key-nav_cat div[role="radiogroup"] p {{
    font-size:.92rem; font-weight:600; color:var(--ink);
}}

/* ── 가운데: 기사 목록 카드 ─────────────────────────── */
.st-key-artlist div[role="radiogroup"] label[data-baseweb="radio"] {{
    background: var(--card-bg); border:1px solid var(--line); border-radius:14px;
    padding: .85rem 1rem; margin-bottom:.55rem; box-shadow: var(--shadow);
    transition: border-color .12s, transform .08s;
}}
.st-key-artlist div[role="radiogroup"] label[data-baseweb="radio"]:hover {{ border-color: var(--accent); }}
.st-key-artlist div[role="radiogroup"] label[data-baseweb="radio"]:has(input:checked) {{
    border: 1.6px solid var(--accent); background: var(--card-bg);
}}
.st-key-artlist div[role="radiogroup"] p {{
    font-size:.95rem; font-weight:700; color:var(--ink); line-height:1.4;
}}
.st-key-artlist div[role="radiogroup"] label [data-testid="stCaptionContainer"] p,
.st-key-artlist div[role="radiogroup"] label small {{
    font-weight:400; font-size:.8rem; color:var(--ink-3) !important; line-height:1.5;
}}

/* ── 우측: 리딩 패널 ────────────────────────────────── */
.reader-pane {{
    background: var(--card-bg); border:1px solid var(--line); border-radius:18px;
    box-shadow: var(--shadow); padding: 1.5rem 1.7rem 1.6rem;
    position: sticky; top: .8rem; max-height: calc(100vh - 1.6rem); overflow-y: auto;
}}
.reader-meta {{ display:flex; align-items:center; gap:.5rem; font-size:.82rem; color:var(--ink-3); margin-bottom:.6rem; flex-wrap:wrap; }}
.reader-chip {{ font-weight:800; font-size:.78rem; padding:.15rem .6rem; border-radius:999px; color:#fff; }}
.reader-title {{ font-size:1.45rem; font-weight:800; color:var(--ink); line-height:1.32; margin:.1rem 0 .8rem; word-break:keep-all; }}
.reader-title a {{ color: var(--ink); text-decoration: none; }}
.reader-title a:hover {{ color: var(--accent); }}
.reader-summary {{
    background: var(--accent-soft); border-radius: 12px; padding: .8rem 1rem;
    font-size: calc(var(--reader-size) * .95); color: var(--ink-2); line-height:1.65;
    margin-bottom: 1rem; word-break: keep-all;
}}
.reader-body p {{
    font-size: var(--reader-size); color: var(--ink-2); line-height: 1.78;
    margin-bottom: .9rem; word-break: keep-all; overflow-wrap:anywhere;
}}
.tag-row {{ display:flex; gap:.35rem; flex-wrap:wrap; margin:.2rem 0 1rem; }}
.tag-pill {{ background:var(--accent-soft); color:var(--ink-2); border-radius:999px; padding:.16rem .6rem; font-size:.74rem; font-weight:600; }}
.open-btn {{
    display:inline-block; background: var(--accent); color:#fff !important;
    font-weight:700; font-size:.92rem; padding:.55rem 1.15rem; border-radius:11px;
    text-decoration:none; box-shadow: var(--shadow);
}}
.open-btn:hover {{ filter: brightness(1.08); }}
.reader-empty {{ color: var(--ink-3); text-align:center; padding: 4rem 1rem; font-size:.95rem; }}

/* 검색창 */
.stTextInput input {{ border-radius: 12px !important; }}

/* 통계 헤더 */
.list-head {{ font-size:.78rem; font-weight:800; letter-spacing:.14em; color:var(--ink-3); text-transform:uppercase; margin:.35rem 0 .5rem .15rem; }}
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
    df["date_dt"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date_dt"])
    cat_order = {c: i for i, c in enumerate(ALL_CATEGORIES)}
    df["_rank"] = df["category"].map(cat_order).fillna(99)
    df = df.sort_values(["date_dt", "_rank"], ascending=[False, True]).drop(columns="_rank")
    return df.reset_index(drop=True)


df = load_news()
today = datetime.now(KST).date()


def md_safe(s: str) -> str:
    """라디오 라벨(마크다운)에서 수식/서식 오작동 방지"""
    return s.replace("$", "＄").replace("*", "∗").replace("`", "'").replace("#", "＃")


def human_date(d) -> str:
    dd = d.date() if hasattr(d, "date") else d
    if dd == today:
        return "오늘"
    if dd == today - timedelta(days=1):
        return "어제"
    return f"{dd.month}.{dd.day}" if dd.year == today.year else f"{dd.year}.{dd.month}.{dd.day}"


# ════════════════════════════════════════════════════════════════════
# 설정 다이얼로그 — 글자 크기 + 구독 키워드 편집
# ════════════════════════════════════════════════════════════════════

@st.dialog("⚙️ 설정", width="large")
def settings_dialog():
    fs = st.slider("본문 글자 크기", 13, 24, value=st.session_state.reader_font, key="reader_font_widget")
    st.session_state.reader_font = fs
    st.divider()
    st.markdown("##### 구독 키워드")
    st.caption(
        "쉼표(,) = 같은 의미(OR) · 세미콜론(;) = 반드시 함께(AND)  \n"
        "예: `AI, 인공지능 ; 지식재산, 특허, 디자인` → (AI 또는 인공지능) 이면서 (지식재산·특허·디자인 중 하나)"
    )
    rows = [
        {
            "구독명": s.get("name", ""),
            "키워드": " ; ".join(", ".join(g) for g in s.get("groups", [])),
        }
        for s in SUBS
    ]
    edited = st.data_editor(
        pd.DataFrame(rows, columns=["구독명", "키워드"]),
        num_rows="dynamic",
        hide_index=True,
        width="stretch",
        key="kw_editor",
    )
    st.caption("행 추가(+)로 구독을 늘릴 수 있습니다. 지재처 보도자료는 키워드와 무관하게 항상 전량 수집됩니다.")
    if st.button("💾 저장", type="primary", width="stretch"):
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
            st.rerun()
        else:
            st.error(msg)


# ════════════════════════════════════════════════════════════════════
# 레이아웃: [좌측 레일 | 메인]
# ════════════════════════════════════════════════════════════════════

rail, main = st.columns([1, 4.35], gap="medium")

with rail:
    st.markdown(
        '<div class="app-logo"><div class="mark">IP</div>'
        '<div><div class="name">IP·AI 브리핑</div><div class="sub">DAILY NEWS</div></div></div>',
        unsafe_allow_html=True,
    )

    with st.container(key="nav_view"):
        view = st.radio("보기", ["📅 오늘", "🗓️ 최근 7일", "📰 전체 기사", "📈 트렌드"],
                        index=1, label_visibility="collapsed")

    # 기간 필터
    if view == "📅 오늘":
        df_v = df[df["date_dt"].dt.date >= today] if not df.empty else df
    elif view == "🗓️ 최근 7일":
        df_v = df[df["date_dt"].dt.date >= today - timedelta(days=6)] if not df.empty else df
    else:
        df_v = df

    st.markdown('<div class="rail-label">카테고리</div>', unsafe_allow_html=True)
    counts = df_v["category"].value_counts() if not df_v.empty else {}
    cat_options = ["전체"] + ALL_CATEGORIES
    def cat_label(c):
        if c == "전체":
            return f"전체 보기 ({len(df_v)})"
        return f"{CAT_DOTS.get(c, '⚪')} {md_safe(c)} ({counts.get(c, 0) if hasattr(counts, 'get') else 0})"
    with st.container(key="nav_cat"):
        sel_cat = st.radio("카테고리", cat_options, format_func=cat_label, label_visibility="collapsed")

    st.markdown('<div class="rail-label">소스</div>', unsafe_allow_html=True)
    src_options = ["전체"] + (df_v["source"].value_counts().head(15).index.tolist() if not df_v.empty else [])
    sel_src = st.selectbox("소스", src_options, label_visibility="collapsed")

    st.write("")
    if st.button("⚙️ 설정 · 키워드", width="stretch"):
        settings_dialog()

# ── 필터 적용 ──────────────────────────────────────────
filtered = df_v
if not filtered.empty:
    if sel_cat != "전체":
        filtered = filtered[filtered["category"] == sel_cat]
    if sel_src != "전체":
        filtered = filtered[filtered["source"] == sel_src]

# ════════════════════════════════════════════════════════════════════
# 메인 영역
# ════════════════════════════════════════════════════════════════════

with main:
    if df.empty:
        st.info("아직 수집된 뉴스가 없습니다. 터미널에서 `python data_pipeline.py`를 실행하세요.")
        st.stop()

    # ── 트렌드 뷰 ─────────────────────────────────────
    if view == "📈 트렌드":
        st.markdown('<div class="list-head">Trend — 누적 수집 데이터</div>', unsafe_allow_html=True)
        c1, c2 = st.columns(2, gap="medium")
        with c1:
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
                                                    range=[CAT_COLORS[c] for c in ALL_CATEGORIES]),
                                    legend=alt.Legend(orient="top", title=None)),
                    tooltip=["날짜", "카테고리", "기사 수"],
                )
                .properties(height=280)
            )
            st.altair_chart(chart1, width="stretch")
        with c2:
            st.markdown("##### 핵심 키워드 Top 12 (최근 7일)")
            kws = df[df["date_dt"].dt.date >= today - timedelta(days=6)].explode("keywords")["keywords"].dropna()
            if not kws.empty:
                kt = kws.value_counts().head(12).reset_index()
                kt.columns = ["키워드", "빈도"]
                chart2 = (
                    alt.Chart(kt)
                    .mark_bar(size=16, cornerRadiusEnd=4, color=MOIP_COLOR)
                    .encode(x=alt.X("빈도:Q", title=None),
                            y=alt.Y("키워드:N", sort="-x", title=None),
                            tooltip=["키워드", "빈도"])
                    .properties(height=280)
                )
                st.altair_chart(chart2, width="stretch")
            else:
                st.caption("최근 7일 키워드 데이터가 없습니다.")
        with st.expander("📄 데이터 표로 보기"):
            st.dataframe(
                df[["date", "category", "source", "title", "link"]]
                .rename(columns={"date": "날짜", "category": "카테고리", "source": "소스", "title": "제목", "link": "링크"}),
                width="stretch", hide_index=True,
                column_config={"링크": st.column_config.LinkColumn("링크", display_text="원문 열기")},
            )
        st.stop()

    # ── 리더 뷰: [기사 목록 | 본문] ────────────────────
    list_col, read_col = st.columns([1, 1.32], gap="medium")

    with list_col:
        q = st.text_input("검색", placeholder="🔍 검색 — 제목·요약·본문",
                          label_visibility="collapsed", key="search_q")
        if q.strip():
            qq = q.strip().lower()
            filtered = filtered[
                filtered["title"].str.lower().str.contains(qq, regex=False)
                | filtered["summary"].str.lower().str.contains(qq, regex=False)
                | filtered["content"].str.lower().str.contains(qq, regex=False)
            ]

        n = len(filtered)
        st.markdown(f'<div class="list-head">기사 {n}건</div>', unsafe_allow_html=True)

        MAX_SHOW = 60
        shown = filtered.head(MAX_SHOW)
        if n == 0:
            st.warning("조건에 맞는 기사가 없습니다.")
            sel_idx = None
        else:
            ids = shown.index.tolist()
            labels = {}
            captions = []
            for i in ids:
                r = shown.loc[i]
                labels[i] = f"**{md_safe(r['title'])}**"
                summ = r["summary"] if r["summary"] != r["title"] else ""
                summ = md_safe(summ[:110] + ("…" if len(summ) > 110 else ""))
                meta = f"{md_safe(str(r['source']))} · {human_date(r['date_dt'])}"
                captions.append(f"{summ}  \n{meta}" if summ else meta)
            with st.container(key="artlist"):
                sel_idx = st.radio("기사 목록", ids, format_func=lambda i: labels[i],
                                   captions=captions, label_visibility="collapsed")
            if n > MAX_SHOW:
                st.caption(f"상위 {MAX_SHOW}건 표시 중 (전체 {n}건) — 검색·필터로 좁혀 보세요.")

    with read_col:
        if n == 0 or sel_idx is None:
            st.markdown('<div class="reader-pane"><div class="reader-empty">👈 왼쪽 목록에서 기사를 선택하세요</div></div>',
                        unsafe_allow_html=True)
        else:
            r = filtered.loc[sel_idx]
            cat = r["category"]
            color = CAT_COLORS.get(cat, "#666")
            title_esc = html.escape(r["title"])
            link_esc = html.escape(r["link"], quote=True)
            date_str = r["date_dt"].strftime("%Y.%m.%d")

            # 본문: content 우선, 없으면 summary → 3문장 단위 문단으로
            body_text = r["content"] or ""
            summary_text = r["summary"] if r["summary"] != r["title"] else ""
            paras_html = ""
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

            tags = "".join(f'<span class="tag-pill">#{html.escape(k)}</span>' for k in r["keywords"][:6])
            tags_html = f'<div class="tag-row">{tags}</div>' if tags else ""

            st.markdown(f"""
<div class="reader-pane">
  <div class="reader-meta">
    <span class="reader-chip" style="background:{color}">{html.escape(cat)}</span>
    <span>{html.escape(str(r['source']))}</span><span>·</span><span>{date_str}</span>
  </div>
  <div class="reader-title"><a href="{link_esc}" target="_blank" rel="noopener">{title_esc}</a></div>
  {tags_html}
  {summary_html}
  <div class="reader-body">{paras_html}</div>
  <div style="margin-top:1.1rem;"><a class="open-btn" href="{link_esc}" target="_blank" rel="noopener">원문 기사 열기 ↗</a></div>
</div>
""", unsafe_allow_html=True)

    st.markdown(
        f'<div style="color:var(--ink-3); font-size:.75rem; padding:1rem .2rem 0;">'
        f'매일 오전 7시 자동 수집 · 누적 {len(df):,}건 · 마지막 수집 {df["date_dt"].max().strftime("%Y.%m.%d")}</div>',
        unsafe_allow_html=True,
    )
