# -*- coding: utf-8 -*-
"""
════════════════════════════════════════════════════════════════════
 IP·AI 뉴스 브리핑 — 임원 보고용 대시보드 (모듈 3)
════════════════════════════════════════════════════════════════════
 실행: streamlit run app.py
 데이터: data/news_YYYYMMDD.json (data_pipeline.py가 매일 생성)
════════════════════════════════════════════════════════════════════
"""

import html
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

KST = timezone(timedelta(hours=9))
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

# 카테고리 고정 순서 + 색 (색각이상 안전 팔레트, 항상 같은 카테고리 = 같은 색)
CATEGORIES = ["특허청", "AI+IP", "AI 기술"]
CAT_CHART_COLORS = {"특허청": "#0072B2", "AI+IP": "#E69F00", "AI 기술": "#009E73"}

# ════════════════════════════════════════════════════════════════════
# 페이지 설정
# ════════════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="IP·AI 뉴스 브리핑",
    page_icon="📰",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ════════════════════════════════════════════════════════════════════
# 사이드바 — 디스플레이 설정
# ════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("### ⚙️ 디스플레이 설정")
    font_size = st.slider("글자 크기 (본문)", min_value=14, max_value=24, value=17, step=1)
    st.caption("요약 본문 글자 크기를 조절합니다. E-book처럼 편하게 읽으세요.")
    st.divider()
    period = st.radio(
        "표시 기간",
        ["오늘", "최근 3일", "최근 7일", "전체"],
        index=2,
        horizontal=False,
    )
    st.divider()
    if st.button("🔄 데이터 새로고침", width="stretch"):
        st.cache_data.clear()
        st.rerun()

# ════════════════════════════════════════════════════════════════════
# 맞춤형 CSS — 에디토리얼(조간신문) 스타일, 라이트/다크 자동 전환
# ════════════════════════════════════════════════════════════════════

st.markdown(f"""
<style>
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css');
@import url('https://fonts.googleapis.com/css2?family=Noto+Serif+KR:wght@600;700;900&display=swap');

:root {{
    --font-body: 'Pretendard Variable', Pretendard, 'Malgun Gothic', sans-serif;
    --font-display: 'Noto Serif KR', 'Batang', serif;
    --reader-size: {font_size}px;

    --page-bg: #f7f5f0;          /* 신문지 느낌의 웜 화이트 */
    --card-bg: #ffffff;
    --ink: #191c22;
    --ink-2: #555d68;
    --ink-3: #9199a5;
    --rule: #191c22;              /* 마스트헤드 굵은 괘선 */
    --hair: #e3e0d8;              /* 얇은 괘선 */
    --pill-bg: #f0ede6;
    --pill-ink: #6b7280;
    --card-shadow: 0 1px 2px rgba(25,28,34,.05), 0 4px 14px rgba(25,28,34,.06);

    --cat-kipo: #075985;
    --cat-aiip: #b45309;
    --cat-aitech: #047857;
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
        --card-shadow: 0 1px 2px rgba(0,0,0,.4), 0 4px 14px rgba(0,0,0,.3);

        --cat-kipo: #58b0e0;
        --cat-aiip: #eab308;
        --cat-aitech: #34d399;
    }}
}}

.stApp {{ background: var(--page-bg); }}
html, body, [class*="css"] {{ font-family: var(--font-body); }}
#MainMenu, footer {{ visibility: hidden; }}
.block-container {{ padding-top: 1.6rem; max-width: 980px; }}

/* ── 마스트헤드 (신문 제호) ─────────────────────────── */
.masthead {{ text-align: center; padding: .2rem 0 .9rem; }}
.masthead .kicker {{
    font-size: .78rem; letter-spacing: .35em; color: var(--ink-3);
    text-transform: uppercase; margin-bottom: .35rem;
}}
.masthead h1 {{
    font-family: var(--font-display); font-weight: 900;
    font-size: clamp(1.9rem, 4.5vw, 2.9rem); color: var(--ink);
    margin: 0; line-height: 1.15; letter-spacing: -.01em;
}}
.masthead .dateline {{
    font-size: .88rem; color: var(--ink-2); margin-top: .5rem;
}}
.masthead-rule {{
    border-top: 3px solid var(--rule); border-bottom: 1px solid var(--rule);
    height: 3px; margin: .3rem 0 1.2rem;
}}

/* ── 통계 타일 ─────────────────────────────────────── */
.stat-row {{ display: flex; gap: .7rem; margin-bottom: 1.1rem; flex-wrap: wrap; }}
.stat-tile {{
    flex: 1 1 130px; background: var(--card-bg); border-radius: 14px;
    padding: .85rem 1.1rem; box-shadow: var(--card-shadow);
    border-top: 3px solid var(--hair);
}}
.stat-tile .label {{ font-size: .78rem; color: var(--ink-3); font-weight: 600; }}
.stat-tile .value {{
    font-family: var(--font-display); font-size: 1.75rem; font-weight: 700;
    color: var(--ink); line-height: 1.2;
}}
.stat-tile.c-kipo   {{ border-top-color: var(--cat-kipo); }}
.stat-tile.c-aiip   {{ border-top-color: var(--cat-aiip); }}
.stat-tile.c-aitech {{ border-top-color: var(--cat-aitech); }}

/* ── 기사 카드 ─────────────────────────────────────── */
.news-card {{
    background: var(--card-bg); border-radius: 16px;
    padding: 1.15rem 1.35rem 1.05rem; box-shadow: var(--card-shadow);
    transition: transform .12s ease;
}}
.news-card:active {{ transform: scale(.995); }}
.news-meta {{
    font-size: .8rem; color: var(--ink-3); margin-bottom: .3rem;
    display: flex; align-items: center; gap: .45rem; flex-wrap: wrap;
}}
.cat-kicker {{ font-weight: 800; letter-spacing: .06em; font-size: .78rem; }}
.cat-kicker.c-kipo   {{ color: var(--cat-kipo); }}
.cat-kicker.c-aiip   {{ color: var(--cat-aiip); }}
.cat-kicker.c-aitech {{ color: var(--cat-aitech); }}
.news-title {{ margin: .1rem 0 .45rem; line-height: 1.35; }}
.news-title a {{
    font-family: var(--font-display); font-weight: 700;
    font-size: calc(var(--reader-size) * 1.18); color: var(--ink);
    text-decoration: none;
}}
.news-title a:hover {{ text-decoration: underline; text-underline-offset: 4px; }}
.news-summary {{
    font-size: var(--reader-size); color: var(--ink-2);
    line-height: 1.65; margin-bottom: .6rem;
    word-break: keep-all; overflow-wrap: anywhere;
}}
.tag-row {{ display: flex; gap: .35rem; flex-wrap: wrap; }}
.tag-pill {{
    background: var(--pill-bg); color: var(--pill-ink);
    border-radius: 999px; padding: .18rem .68rem;
    font-size: .74rem; font-weight: 600;
}}

/* 구분선을 얇은 신문 괘선처럼 */
hr {{ border-color: var(--hair) !important; margin: .8rem 0 !important; }}

/* 검색창·필터를 카드 톤에 맞춤 */
.stTextInput input {{ border-radius: 12px !important; font-size: 1rem !important; }}

/* 섹션 제목 */
.section-label {{
    font-size: .8rem; font-weight: 800; letter-spacing: .22em;
    color: var(--ink-3); text-transform: uppercase; margin: .4rem 0 .6rem;
}}
</style>
""", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════════
# 데이터 로드
# ════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=600, show_spinner="뉴스 데이터를 불러오는 중...")
def load_news() -> pd.DataFrame:
    """data/ 폴더의 모든 JSON 파일을 하나의 표로 통합"""
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
    # 정렬: 최신 날짜 우선, 같은 날짜 안에서는 특허청 → AI+IP → AI 기술 순
    cat_order = {c: i for i, c in enumerate(CATEGORIES)}
    df["_cat_rank"] = df["category"].map(cat_order).fillna(99)
    df = df.sort_values(["date_dt", "_cat_rank"], ascending=[False, True]).drop(columns="_cat_rank")
    return df.reset_index(drop=True)


df = load_news()
today = datetime.now(KST).date()

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
    st.info("아직 수집된 뉴스가 없습니다. 터미널에서 `python data_pipeline.py`를 실행하면 오늘 뉴스가 수집됩니다.")
    st.stop()

# 기간 필터 적용
if period == "오늘":
    view = df[df["date_dt"].dt.date >= today]
elif period == "최근 3일":
    view = df[df["date_dt"].dt.date >= today - timedelta(days=2)]
elif period == "최근 7일":
    view = df[df["date_dt"].dt.date >= today - timedelta(days=6)]
else:
    view = df
if view.empty:
    view = df  # 해당 기간에 기사가 없으면 전체 표시

# ════════════════════════════════════════════════════════════════════
# 통계 타일
# ════════════════════════════════════════════════════════════════════

cat_counts = view["category"].value_counts()
st.markdown(f"""
<div class="stat-row">
    <div class="stat-tile"><div class="label">수집 기사 ({period})</div><div class="value">{len(view):,}건</div></div>
    <div class="stat-tile c-kipo"><div class="label">특허청 보도자료</div><div class="value">{cat_counts.get("특허청", 0)}건</div></div>
    <div class="stat-tile c-aiip"><div class="label">AI + 지식재산</div><div class="value">{cat_counts.get("AI+IP", 0)}건</div></div>
    <div class="stat-tile c-aitech"><div class="label">AI 기술</div><div class="value">{cat_counts.get("AI 기술", 0)}건</div></div>
</div>
""", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════════
# 검색 & 필터
# ════════════════════════════════════════════════════════════════════

search = st.text_input(
    "통합 검색",
    placeholder="🔍  키워드 검색 — 제목·요약에서 찾습니다 (예: 상표, 챗GPT, 소송)",
    label_visibility="collapsed",
)

fcol1, fcol2 = st.columns(2)
with fcol1:
    all_cats = [c for c in CATEGORIES if c in view["category"].unique()] + \
               [c for c in view["category"].unique() if c not in CATEGORIES]
    sel_cats = st.multiselect("카테고리", all_cats, placeholder="카테고리 (전체)")
with fcol2:
    all_sources = sorted(view["source"].unique())
    sel_sources = st.multiselect("소스", all_sources, placeholder="소스/언론사 (전체)")

filtered = view
if search.strip():
    q = search.strip().lower()
    mask = (
        filtered["title"].str.lower().str.contains(q, regex=False)
        | filtered["summary"].str.lower().str.contains(q, regex=False)
        | filtered["keywords"].apply(lambda ks: any(q in k.lower() for k in ks))
    )
    filtered = filtered[mask]
if sel_cats:
    filtered = filtered[filtered["category"].isin(sel_cats)]
if sel_sources:
    filtered = filtered[filtered["source"].isin(sel_sources)]

# ════════════════════════════════════════════════════════════════════
# 탭: 뉴스 피드 / 트렌드
# ════════════════════════════════════════════════════════════════════

tab_feed, tab_trend = st.tabs(["📋 뉴스 피드", "📈 트렌드"])

CAT_CLASS = {"특허청": "c-kipo", "AI+IP": "c-aiip", "AI 기술": "c-aitech"}


def render_card(row) -> str:
    """기사 1건을 카드 HTML로 변환 (마크다운 코드블록 오인 방지를 위해 한 줄로 생성)"""
    title = html.escape(row["title"])
    link = html.escape(row["link"], quote=True)
    summary = html.escape(row["summary"])
    source = html.escape(str(row["source"]))
    cat = row["category"]
    cat_cls = CAT_CLASS.get(cat, "")
    date_str = row["date_dt"].strftime("%Y.%m.%d")
    show_summary = summary and summary != title
    tags = "".join(f'<span class="tag-pill">#{html.escape(k)}</span>' for k in row["keywords"][:5])
    parts = [
        '<div class="news-card">',
        f'<div class="news-meta"><span class="cat-kicker {cat_cls}">{html.escape(cat)}</span>'
        f'<span>·</span><span>{source}</span><span>·</span><span>{date_str}</span></div>',
        f'<div class="news-title"><a href="{link}" target="_blank" rel="noopener">{title}</a></div>',
    ]
    if show_summary:
        parts.append(f'<div class="news-summary">{summary}</div>')
    if tags:
        parts.append(f'<div class="tag-row">{tags}</div>')
    parts.append("</div>")
    return "".join(parts)


with tab_feed:
    n = len(filtered)
    st.markdown(f'<div class="section-label">Today’s Feed — {n}건</div>', unsafe_allow_html=True)
    if n == 0:
        st.warning("조건에 맞는 기사가 없습니다. 검색어나 필터를 조정해 보세요.")
    MAX_SHOW = 80
    for i, (_, row) in enumerate(filtered.head(MAX_SHOW).iterrows()):
        with st.container():
            st.markdown(render_card(row), unsafe_allow_html=True)
        if i < min(n, MAX_SHOW) - 1:
            st.divider()
    if n > MAX_SHOW:
        st.caption(f"상위 {MAX_SHOW}건만 표시 중입니다. 검색·필터로 좁혀 보세요. (전체 {n}건)")

with tab_trend:
    st.markdown('<div class="section-label">Trend — 누적 수집 데이터 기준</div>', unsafe_allow_html=True)

    # 1) 일자별 카테고리 수집량 (최근 14일)
    trend_df = df[df["date_dt"].dt.date >= today - timedelta(days=13)]
    daily = trend_df.groupby([trend_df["date_dt"].dt.strftime("%m/%d"), "category"]) \
                    .size().reset_index(name="count")
    daily.columns = ["날짜", "카테고리", "기사 수"]

    st.markdown("##### 일자별 수집 기사 (최근 14일)")
    chart1 = (
        alt.Chart(daily)
        .mark_bar(size=22)
        .encode(
            x=alt.X("날짜:O", title=None, axis=alt.Axis(labelAngle=0)),
            y=alt.Y("기사 수:Q", title=None),
            color=alt.Color(
                "카테고리:N",
                scale=alt.Scale(
                    domain=CATEGORIES,
                    range=[CAT_CHART_COLORS[c] for c in CATEGORIES],
                ),
                legend=alt.Legend(orient="top", title=None),
            ),
            tooltip=["날짜", "카테고리", "기사 수"],
        )
        .properties(height=260)
    )
    st.altair_chart(chart1, width="stretch")

    # 2) 핵심 키워드 빈도 (표시 기간 기준)
    st.markdown(f"##### 핵심 키워드 Top 12 ({period})")
    kw_series = view.explode("keywords")["keywords"].dropna()
    if not kw_series.empty:
        kw_top = kw_series.value_counts().head(12).reset_index()
        kw_top.columns = ["키워드", "빈도"]
        chart2 = (
            alt.Chart(kw_top)
            .mark_bar(size=18, cornerRadiusEnd=4, color="#0072B2")
            .encode(
                x=alt.X("빈도:Q", title=None),
                y=alt.Y("키워드:N", sort="-x", title=None),
                tooltip=["키워드", "빈도"],
            )
            .properties(height=320)
        )
        st.altair_chart(chart2, width="stretch")
    else:
        st.caption("키워드 데이터가 아직 없습니다.")

    # 3) 표로 보기 (접근성·검증용)
    with st.expander("📄 데이터 표로 보기"):
        st.dataframe(
            view[["date", "category", "source", "title", "link"]]
            .rename(columns={"date": "날짜", "category": "카테고리", "source": "소스", "title": "제목", "link": "링크"}),
            width="stretch",
            hide_index=True,
            column_config={"링크": st.column_config.LinkColumn("링크", display_text="원문 열기")},
        )

# ════════════════════════════════════════════════════════════════════
# 하단 정보
# ════════════════════════════════════════════════════════════════════

last_date = df["date_dt"].max().strftime("%Y.%m.%d")
st.markdown(
    f'<div style="text-align:center; color:var(--ink-3); font-size:.78rem; padding:1.5rem 0 .5rem;">'
    f'마지막 수집일 {last_date} · 매일 오전 7시 자동 업데이트 · 누적 {len(df):,}건</div>',
    unsafe_allow_html=True,
)
