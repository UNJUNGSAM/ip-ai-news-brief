# -*- coding: utf-8 -*-
"""
════════════════════════════════════════════════════════════════════
 IP·AI 뉴스 브리핑 — 임원 보고용 대시보드 (모듈 3)
════════════════════════════════════════════════════════════════════
 조간신문 스타일 피드 + 기사 팝업 + 로그인/스크랩 + 엑셀·PDF 내보내기
 - 내비게이션·카드는 순수 HTML 링크(쿼리 파라미터) 기반
 - 로그인: 쿠키(nb_auth) 기반 자동 로그인
 - 계정·스크랩 데이터: GitHub 저장소 store 브랜치(users.json/scraps.json)
   → main 브랜치가 아니므로 저장해도 앱이 재배포되지 않음
 실행: streamlit run app.py
════════════════════════════════════════════════════════════════════
"""

import base64
import hashlib
import hmac
import html
import io
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, unquote

import altair as alt
import pandas as pd
import requests
import streamlit as st
from streamlit.components.v1 import html as components_html

# 회사 PC 등 SSL 검사(사내 보안 프로그램) 환경 대응 — 클라우드에서는 무해
try:
    import truststore

    truststore.inject_into_ssl()
except Exception:
    pass

KST = timezone(timedelta(hours=9))
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CONFIG_PATH = BASE_DIR / "config" / "keywords.json"
FONT_PATH = BASE_DIR / "fonts" / "NanumGothic-Regular.ttf"

MOIP_CATEGORY = "지재처 보도자료"
DEFAULT_CONFIG = {
    "subscriptions": [
        {"name": "지재처 관련뉴스", "groups": [["지식재산처", "지재처", "특허청"]]},
        {"name": "AI·지식재산", "groups": [["AI", "인공지능"], ["지식재산", "특허", "디자인"]]},
        {"name": "AI 업계", "groups": [["오픈AI", "챗GPT", "앤스로픽", "클로드", "제미나이", "엔비디아", "생성형 AI"]]},
    ]
}

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
# 공통 헬퍼
# ════════════════════════════════════════════════════════════════════

def get_secret(name: str, default: str = "") -> str:
    try:
        return str(st.secrets.get(name, default))
    except Exception:
        return default


GH_REPO = get_secret("GITHUB_REPO", "UNJUNGSAM/ip-ai-news-brief")
AUTH_SECRET = get_secret("AUTH_SECRET", "ipai-news-brief-2026")


def gh_token() -> str:
    return get_secret("GITHUB_TOKEN")


def gh_headers() -> dict:
    return {"Authorization": f"Bearer {gh_token()}", "Accept": "application/vnd.github+json"}


# ── store 브랜치 읽기/쓰기 (계정·스크랩 영구 저장) ──────────────────

@st.cache_data(ttl=20, show_spinner=False)
def store_read(path: str) -> dict:
    if gh_token():
        try:
            r = requests.get(
                f"https://api.github.com/repos/{GH_REPO}/contents/{path}",
                params={"ref": "store"}, headers=gh_headers(), timeout=10,
            )
            if r.status_code == 200:
                return json.loads(base64.b64decode(r.json()["content"]).decode("utf-8"))
        except Exception:
            pass
        return {}
    # 토큰이 없으면 로컬 파일 폴백 (개발용)
    p = BASE_DIR / f"local_{path}"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def store_write(path: str, obj: dict) -> bool:
    text = json.dumps(obj, ensure_ascii=False, indent=2)
    ok = False
    if gh_token():
        try:
            api = f"https://api.github.com/repos/{GH_REPO}/contents/{path}"
            sha = None
            r = requests.get(api, params={"ref": "store"}, headers=gh_headers(), timeout=10)
            if r.status_code == 200:
                sha = r.json().get("sha")
            payload = {
                "message": f"chore: {path} 갱신 (대시보드)",
                "content": base64.b64encode(text.encode()).decode(),
                "branch": "store",
            }
            if sha:
                payload["sha"] = sha
            r2 = requests.put(api, headers=gh_headers(), json=payload, timeout=15)
            ok = r2.status_code in (200, 201)
        except Exception:
            ok = False
    else:
        try:
            (BASE_DIR / f"local_{path}").write_text(text, encoding="utf-8")
            ok = True
        except Exception:
            ok = False
    if ok:
        store_read.clear()
    return ok


# ── 로그인(쿠키) ────────────────────────────────────────────────────
# 회원가입 없음: Secrets의 ALLOWED_USERS(사번 목록)에 있는 사번만 로그인 가능
# 아이디 = 사번, 비밀번호 = 사번

def allowed_users() -> list[str]:
    raw = get_secret("ALLOWED_USERS", "")
    return [u.strip() for u in re.split(r"[,;\s]+", raw) if u.strip()]


def make_token(uid: str) -> str:
    sig = hmac.new(AUTH_SECRET.encode(), uid.encode(), hashlib.sha256).hexdigest()[:24]
    return f"{quote(uid)}:{sig}"


def verify_token(token: str) -> str | None:
    try:
        enc_uid, sig = token.rsplit(":", 1)
        uid = unquote(enc_uid)
        good = hmac.new(AUTH_SECRET.encode(), uid.encode(), hashlib.sha256).hexdigest()[:24]
        return uid if hmac.compare_digest(sig, good) else None
    except Exception:
        return None


def try_set_cookie(token: str):
    """자동 로그인용 쿠키 저장 시도 (차단돼도 무방 — 주소의 토큰이 로그인을 유지함)"""
    components_html(f"""<script>
    var c = "nb_auth={token}; path=/; max-age=31536000; SameSite=Lax";
    try {{ window.parent.document.cookie = c; }} catch(e) {{ try {{ document.cookie = c; }} catch(e2) {{}} }}
    </script>""", height=0)


def get_auth_qp() -> str:
    """주소에 붙은 유효한 로그인 토큰 (없으면 빈 문자열)"""
    try:
        t = st.query_params.get("auth", "")
        if t and verify_token(t):
            return t
    except Exception:
        pass
    return ""


def get_cookie_user() -> str | None:
    try:
        token = st.context.cookies.get("nb_auth", "")
    except Exception:
        token = ""
    return verify_token(token) if token else None


def get_current_user() -> str | None:
    # 1) 이 세션에서 로그인/로그아웃한 상태가 최우선 (""=명시적 로그아웃)
    if "auth_user" in st.session_state:
        uid = st.session_state.auth_user
        return uid if (uid and uid in allowed_users()) else None
    # 2) 주소의 로그인 토큰 → 3) 쿠키
    t = get_auth_qp()
    uid = verify_token(t) if t else None
    if not uid:
        uid = get_cookie_user()
    # 목록에서 제외된 사번은 자동으로 접근 차단
    if uid and uid in allowed_users():
        return uid
    return None


current_user = get_current_user()

# ── 구독 키워드 설정 ───────────────────────────────────────────────

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
    text = json.dumps(cfg, ensure_ascii=False, indent=2)
    try:
        CONFIG_PATH.parent.mkdir(exist_ok=True)
        CONFIG_PATH.write_text(text, encoding="utf-8")
    except Exception as e:
        return False, f"저장 실패: {e}"
    if not gh_token():
        return True, "임시 저장만 되었습니다. 영구 저장은 관리자가 Secrets에 GITHUB_TOKEN을 등록해야 합니다."
    try:
        api = f"https://api.github.com/repos/{GH_REPO}/contents/config/keywords.json"
        sha = None
        r = requests.get(api, headers=gh_headers(), timeout=15)
        if r.status_code == 200:
            sha = r.json().get("sha")
        payload = {
            "message": "chore: 구독 키워드 설정 변경 (대시보드에서 저장)",
            "content": base64.b64encode(text.encode()).decode(),
        }
        if sha:
            payload["sha"] = sha
        r2 = requests.put(api, headers=gh_headers(), json=payload, timeout=15)
        if r2.status_code in (200, 201):
            return True, "영구 저장 완료 — 다음 수집부터 새 키워드가 적용됩니다."
        return False, f"GitHub 저장 실패 (HTTP {r2.status_code})"
    except Exception as e:
        return False, f"GitHub 저장 실패: {e}"


def trigger_collect() -> tuple[bool, str]:
    """GitHub Actions 수집 워크플로우를 즉시 실행"""
    if not gh_token():
        return False, "관리자가 Secrets에 GITHUB_TOKEN을 등록해야 사용할 수 있습니다."
    try:
        r = requests.post(
            f"https://api.github.com/repos/{GH_REPO}/actions/workflows/daily_update.yml/dispatches",
            headers=gh_headers(), json={"ref": "main"}, timeout=15,
        )
        if r.status_code == 204:
            return True, "수집을 시작했습니다. 2~4분 뒤 자동으로 반영됩니다 (잠시 후 새로고침)."
        return False, f"실행 실패 (HTTP {r.status_code})"
    except Exception as e:
        return False, f"실행 실패: {e}"


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
# CSS
# ════════════════════════════════════════════════════════════════════

sub_css_light = "\n".join(f".c-sub{i} {{ color: {c[1]}; }}" for i, c in enumerate(SUB_COLOR_SETS))
sub_css_dark = "\n".join(f".c-sub{i} {{ color: {c[2]}; }}" for i, c in enumerate(SUB_COLOR_SETS))

st.markdown(f"""
<style>
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css');
@import url('https://fonts.googleapis.com/css2?family=Noto+Serif+KR:wght@600;700;900&display=swap');

:root {{
    --font-body: 'Pretendard Variable', Pretendard, 'Malgun Gothic', sans-serif;
    --font-display: 'Noto Serif KR', 'Batang', serif;
    --reader-size: {st.session_state.reader_font}px;
    --page-bg: #f7f5f0; --card-bg: #ffffff;
    --ink: #191c22; --ink-2: #555d68; --ink-3: #9199a5;
    --rule: #191c22; --hair: #e3e0d8;
    --pill-bg: #f0ede6; --pill-ink: #6b7280;
    --accent: #0b57d0; --accent-soft: #eef3fd;
    --card-shadow: 0 1px 2px rgba(25,28,34,.05), 0 4px 14px rgba(25,28,34,.06);
    .c-moip {{ color: #075985; }}
    {sub_css_light}
}}
@media (prefers-color-scheme: dark) {{
    :root {{
        --page-bg: #15171c; --card-bg: #1e2128;
        --ink: #eceef2; --ink-2: #a8b0bc; --ink-3: #767e8a;
        --rule: #eceef2; --hair: #32363f;
        --pill-bg: #2a2e37; --pill-ink: #a8b0bc;
        --accent: #7c96ff; --accent-soft: #232a44;
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
iframe[height="0"] {{ display:none; }}

.masthead {{ text-align: center; padding: .2rem 0 .7rem; }}
.masthead .kicker {{ font-size: .75rem; letter-spacing: .35em; color: var(--ink-3); text-transform: uppercase; margin-bottom: .3rem; }}
.masthead h1 {{ font-family: var(--font-display); font-weight: 900; font-size: clamp(1.7rem, 4vw, 2.5rem); color: var(--ink); margin: 0; line-height: 1.15; }}
.masthead .dateline {{ font-size: .85rem; color: var(--ink-2); margin-top: .45rem; }}
.masthead-rule {{ border-top: 3px solid var(--rule); border-bottom: 1px solid var(--rule); height: 3px; margin: .3rem 0 1.1rem; }}

.rail {{ position: sticky; top: .8rem; }}
.rail .sec {{ font-size: .7rem; font-weight: 800; letter-spacing: .18em; color: var(--ink-3); text-transform: uppercase; margin: 1rem 0 .35rem .4rem; }}
.rail a {{ display: flex; justify-content: space-between; align-items: center; padding: .42rem .7rem; border-radius: 10px; margin-bottom: 2px; text-decoration: none; color: var(--ink-2); font-size: .92rem; font-weight: 600; }}
.rail a:hover {{ background: var(--accent-soft); color: var(--ink); }}
.rail a.on {{ background: var(--card-bg); color: var(--ink); box-shadow: var(--card-shadow); font-weight: 800; }}
.rail a .n {{ font-size: .74rem; color: var(--ink-3); font-weight: 600; }}
.rail .dot {{ display:inline-block; width:9px; height:9px; border-radius:50%; margin-right:.5rem; }}
.user-line {{ font-size:.83rem; color:var(--ink-2); padding:.2rem .4rem .4rem; font-weight:700; }}

.stat-row {{ display: flex; gap: .7rem; margin-bottom: 1rem; flex-wrap: wrap; }}
a.stat-tile {{ flex: 1 1 110px; background: var(--card-bg); border-radius: 14px; padding: .75rem 1rem; box-shadow: var(--card-shadow); border-top: 3px solid var(--hair); text-decoration:none; display:block; border-left:none; border-right:none; border-bottom:none; transition: transform .1s; }}
a.stat-tile:hover {{ transform: translateY(-2px); }}
.stat-tile .label {{ font-size: .75rem; color: var(--ink-3); font-weight: 600; }}
.stat-tile .value {{ font-family: var(--font-display); font-size: 1.55rem; font-weight: 700; color: var(--ink); }}

.feed .news-card {{ position: relative; background: var(--card-bg); border-radius: 15px; box-shadow: var(--card-shadow); margin-bottom: .65rem; border: 1px solid transparent; transition: border-color .12s; }}
.feed .news-card:hover {{ border-color: var(--accent); }}
.feed a.card-main {{ display: block; padding: 1rem 1.25rem .9rem; text-decoration: none; }}
.news-meta {{ font-size: .78rem; color: var(--ink-3); margin-bottom: .25rem; display: flex; align-items: center; gap: .45rem; flex-wrap: wrap; padding-right: 4.5rem; }}
.cat-kicker {{ font-weight: 800; letter-spacing: .05em; font-size: .77rem; }}
.news-title {{ font-family: var(--font-display); font-weight: 700; font-size: 1.08rem; color: var(--ink); line-height: 1.42; word-break: keep-all; }}
.tag-row {{ display: flex; gap: .3rem; flex-wrap: wrap; margin-top: .5rem; }}
.tag-pill {{ background: var(--pill-bg); color: var(--pill-ink); border-radius: 999px; padding: .14rem .6rem; font-size: .72rem; font-weight: 600; }}
a.scrap-btn {{ position: absolute; top: .85rem; right: .9rem; z-index: 2; font-size: .72rem; font-weight: 700; padding: .2rem .6rem; border-radius: 999px; text-decoration: none; color: var(--ink-3); border: 1px solid var(--hair); background: var(--card-bg); }}
a.scrap-btn:hover {{ color: var(--accent); border-color: var(--accent); }}
a.scrap-btn.on {{ background: var(--accent); color: #fff; border-color: var(--accent); }}

.reader-meta {{ display:flex; align-items:center; gap:.5rem; font-size:.82rem; color:var(--ink-3); margin-bottom:.5rem; flex-wrap:wrap; }}
.reader-chip {{ font-weight:800; font-size:.76rem; padding:.14rem .6rem; border-radius:999px; color:#fff; }}
.reader-title {{ font-family: var(--font-display); font-size:1.4rem; font-weight:800; color:var(--ink); line-height:1.35; margin:.1rem 0 .7rem; word-break:keep-all; }}
.reader-title a {{ color: var(--ink); text-decoration: none; }}
.reader-title a:hover {{ color: var(--accent); }}
.reader-summary {{ background: var(--accent-soft); border-radius: 12px; padding: .75rem 1rem; font-size: calc(var(--reader-size) * .93); color: var(--ink-2); line-height:1.6; margin-bottom: .9rem; word-break: keep-all; }}
.reader-body p {{ font-size: var(--reader-size); color: var(--ink-2); line-height: 1.78; margin-bottom: .85rem; word-break: keep-all; overflow-wrap: anywhere; }}
.open-btn {{ display:inline-block; background: var(--accent); color:#fff !important; font-weight:700; font-size:.92rem; padding:.55rem 1.15rem; border-radius:11px; text-decoration:none; }}
.open-btn:hover {{ filter: brightness(1.1); }}

.section-label {{ font-size:.78rem; font-weight:800; letter-spacing:.2em; color:var(--ink-3); text-transform:uppercase; margin:.3rem 0 .55rem .1rem; }}
.stTextInput input {{ border-radius: 12px !important; }}

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
# 스크랩
# ════════════════════════════════════════════════════════════════════

def load_scraps() -> dict:
    return store_read("scraps.json")


def user_scrap_list(uid: str) -> list[dict]:
    return load_scraps().get(uid, [])


def toggle_scrap(uid: str, row) -> bool:
    scraps = dict(load_scraps())
    lst = list(scraps.get(uid, []))
    ids = {x.get("id") for x in lst}
    if row["id"] in ids:
        lst = [x for x in lst if x.get("id") != row["id"]]
    else:
        lst.insert(0, {
            "id": row["id"], "title": row["title"], "link": row["link"],
            "category": row["category"], "date": str(row["date"]),
            "source": str(row["source"]), "summary": row["summary"],
            "keywords": list(row["keywords"]),
            "scrapped_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        })
    scraps[uid] = lst
    return store_write("scraps.json", scraps)


# ════════════════════════════════════════════════════════════════════
# URL 상태 + 스크랩 토글 처리
# ════════════════════════════════════════════════════════════════════

VIEWS = {"today": "오늘", "week": "최근 7일", "all": "전체 기사", "trend": "트렌드"}
qp = st.query_params
view = qp.get("view", "week")
if view not in VIEWS:
    view = "week"
sel_cat = qp.get("cat", "전체")
sel_src = qp.get("src", "전체")
sel_id = qp.get("sel", "")
scrap_id = qp.get("scrap", "")
for k in ("sel", "scrap"):
    if k in qp:
        try:
            del st.query_params[k]
        except Exception:
            pass

need_login_msg = ""
if scrap_id:
    if not current_user:
        need_login_msg = "스크랩 기능은 로그인 후 사용할 수 있습니다."
    else:
        hit = df[df["id"] == scrap_id]
        if not hit.empty:
            if not toggle_scrap(current_user, hit.iloc[0]):
                st.toast("스크랩 저장에 실패했습니다. 관리자 설정(GITHUB_TOKEN)을 확인하세요.")
        else:
            # 수집 데이터에서 사라진 옛 기사는 스크랩 목록에서 바로 제거
            scraps_all = dict(load_scraps())
            lst = [x for x in scraps_all.get(current_user, []) if x.get("id") != scrap_id]
            scraps_all[current_user] = lst
            store_write("scraps.json", scraps_all)

scrap_items = user_scrap_list(current_user) if current_user else []
scrap_ids = {x.get("id") for x in scrap_items}


AUTH_QP = get_auth_qp()


def make_url(**over) -> str:
    params = {"view": view, "cat": sel_cat, "src": sel_src}
    if AUTH_QP:
        params["auth"] = AUTH_QP  # 링크 이동 시에도 로그인 유지
    params.update(over)
    parts = []
    for k, v in params.items():
        v = str(v)
        if k not in ("view", "auth") and (not v or v == "전체"):
            continue
        parts.append(f"{k}={quote(v)}")
    return "?" + "&".join(parts)


def is_broken_link(link: str) -> bool:
    """열리지 않는(깨진) 링크인지 판정"""
    link = str(link or "")
    if not link:
        return True
    if "news.google.com/rss/articles" in link:      # 미복원 구글 중계링크
        return True
    if "image_popup" in link or "/tools/" in link:  # 이미지 팝업 등 오추출 링크
        return True
    if re.search(r"\?[A-Za-z_]+=?$", link):          # ?param / ?param= 로 끝(값 잘림)
        return True
    return False


def display_link(link: str, title: str) -> str:
    """깨진 링크는 항상 열리는 구글뉴스 검색 링크로 대체 (제목으로 원문 찾기)"""
    if is_broken_link(link):
        return f"https://news.google.com/search?q={quote(str(title))}&hl=ko&gl=KR&ceid=KR:ko"
    return str(link)


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
# 내보내기 헬퍼 (엑셀 / PDF)
# ════════════════════════════════════════════════════════════════════

EXPORT_COLS = {"date": "날짜", "category": "카테고리", "source": "소스",
               "title": "제목", "summary": "요약", "keywords": "키워드", "link": "링크"}


def items_to_frame(items: list[dict]) -> pd.DataFrame:
    x = pd.DataFrame(items)
    for c in EXPORT_COLS:
        if c not in x.columns:
            x[c] = ""
    return x


def to_excel_bytes(frame: pd.DataFrame) -> bytes:
    x = frame.copy()
    x["keywords"] = x["keywords"].map(lambda ks: ", ".join(ks) if isinstance(ks, list) else str(ks))
    x["link"] = [display_link(l, t) for l, t in zip(x["link"], x["title"])]
    x = x[list(EXPORT_COLS)].rename(columns=EXPORT_COLS)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        x.to_excel(w, index=False, sheet_name="기사")
        ws = w.sheets["기사"]
        widths = [11, 14, 14, 55, 70, 25, 45]
        for i, wd in enumerate(widths, start=1):
            ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = wd
    return buf.getvalue()


def to_pdf_bytes(items: list[dict], subtitle: str) -> bytes | None:
    try:
        from fpdf import FPDF
        pdf = FPDF(format="A4")
        pdf.set_auto_page_break(auto=True, margin=16)
        pdf.add_font("Nanum", "", str(FONT_PATH))
        pdf.add_page()
        pdf.set_font("Nanum", size=20)
        pdf.set_text_color(25, 28, 34)
        pdf.cell(0, 12, "IP·AI 뉴스 브리핑", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Nanum", size=10)
        pdf.set_text_color(120, 126, 138)
        pdf.cell(0, 7, f"{subtitle} · {datetime.now(KST):%Y-%m-%d %H:%M} 생성 · {len(items)}건",
                 new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3)
        for a in items:
            pdf.set_draw_color(210, 207, 198)
            pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
            pdf.ln(3)
            pdf.set_font("Nanum", size=8)
            pdf.set_text_color(130, 136, 148)
            pdf.multi_cell(0, 5, f"{a.get('category','')} · {a.get('source','')} · {a.get('date','')}",
                           new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Nanum", size=12)
            pdf.set_text_color(25, 28, 34)
            pdf.multi_cell(0, 6.5, str(a.get("title", "")), new_x="LMARGIN", new_y="NEXT")
            summ = str(a.get("summary", "") or "")
            if summ and summ != a.get("title"):
                pdf.set_font("Nanum", size=9.5)
                pdf.set_text_color(85, 93, 104)
                pdf.multi_cell(0, 5.5, summ[:400], new_x="LMARGIN", new_y="NEXT")
            link = display_link(a.get("link", ""), a.get("title", ""))
            if link:
                pdf.set_font("Nanum", size=7.5)
                pdf.set_text_color(11, 87, 208)
                pdf.multi_cell(0, 4.5, link, link=link, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(2.5)
        return bytes(pdf.output())
    except Exception:
        return None


# ════════════════════════════════════════════════════════════════════
# 다이얼로그
# ════════════════════════════════════════════════════════════════════

@st.dialog(" ", width="large")
def article_dialog(row):
    color = CAT_CHART.get(row["category"], "#666")
    title_esc = html.escape(row["title"])
    link_esc = html.escape(display_link(row["link"], row["title"]), quote=True)
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
<div style="margin:.9rem 0;"><a class="open-btn" href="{link_esc}" target="_blank" rel="noopener">원문 기사 열기</a></div>
""", unsafe_allow_html=True)

    if current_user:
        on = row["id"] in scrap_ids
        if st.button("스크랩 해제" if on else "이 기사 스크랩", key="dlg_scrap"):
            toggle_scrap(current_user, row)
            st.rerun()
    else:
        st.caption("스크랩하려면 로그인이 필요합니다.")


@st.dialog("로그인")
def login_dialog(msg: str = ""):
    if msg:
        st.info(msg)
    if not allowed_users():
        st.warning("관리자가 Streamlit Secrets에 ALLOWED_USERS(사번 목록)를 등록해야 로그인할 수 있습니다.")
    uid = st.text_input("사번", key="li_id")
    pw = st.text_input("비밀번호", type="password", key="li_pw",
                       help="비밀번호는 본인 사번과 동일합니다.")
    if st.button("로그인", type="primary", width="stretch", key="li_btn"):
        u = uid.strip()
        if u and u in allowed_users() and pw.strip() == u:
            st.session_state.auth_user = u
            st.query_params["auth"] = make_token(u)  # 주소에 로그인 토큰 유지
            st.rerun()
        else:
            st.error("사번 또는 비밀번호가 올바르지 않습니다.")


@st.dialog("설정", width="large")
def settings_dialog():
    fs = st.slider("본문 글자 크기", 13, 24, value=st.session_state.reader_font, key="reader_font_widget")
    st.session_state.reader_font = fs
    st.divider()
    st.markdown("##### 구독 키워드")
    if gh_token():
        st.caption("영구 저장 사용 가능 — 저장하면 모든 사용자에게 적용되고, 다음 수집부터 반영됩니다.")
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


@st.dialog("내보내기", width="large")
def export_dialog(filtered_df: pd.DataFrame, list_label: str):
    stamp = datetime.now(KST).strftime("%Y%m%d")
    st.caption("기사 데이터를 엑셀 또는 PDF 파일로 내려받아 보고·분석에 활용하세요.")

    st.markdown("##### 엑셀 (xlsx)")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.download_button(
            f"현재 목록 ({len(filtered_df)}건)",
            data=to_excel_bytes(filtered_df), file_name=f"IPAI뉴스_{list_label}_{stamp}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch",
        )
    with c2:
        st.download_button(
            f"전체 기사 ({len(df)}건)",
            data=to_excel_bytes(df), file_name=f"IPAI뉴스_전체_{stamp}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch",
        )
    with c3:
        if current_user and scrap_items:
            st.download_button(
                f"내 스크랩 ({len(scrap_items)}건)",
                data=to_excel_bytes(items_to_frame(scrap_items)),
                file_name=f"IPAI뉴스_스크랩_{stamp}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                width="stretch",
            )
        else:
            st.button("내 스크랩 (없음)", disabled=True, width="stretch")

    st.markdown("##### PDF")
    p1, p2 = st.columns(2)
    with p1:
        pdf_cur = to_pdf_bytes(filtered_df.head(100).to_dict("records"), f"{list_label} 기사")
        if pdf_cur:
            st.download_button(
                f"현재 목록 PDF (최대 100건)", data=pdf_cur,
                file_name=f"IPAI뉴스_{list_label}_{stamp}.pdf", mime="application/pdf",
                width="stretch",
            )
    with p2:
        if current_user and scrap_items:
            pdf_scrap = to_pdf_bytes(scrap_items, "내 스크랩")
            if pdf_scrap:
                st.download_button(
                    f"내 스크랩 PDF ({len(scrap_items)}건)", data=pdf_scrap,
                    file_name=f"IPAI뉴스_스크랩_{stamp}.pdf", mime="application/pdf",
                    width="stretch",
                )
        else:
            st.button("내 스크랩 PDF (없음)", disabled=True, width="stretch")


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

# 로그인 상태인데 자동로그인 쿠키가 없으면 저장 시도 (차단돼도 주소 토큰으로 유지됨)
if current_user and get_cookie_user() != current_user:
    try_set_cookie(make_token(current_user))

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
        on = " on" if (view == k and sel_cat != "__scrap__") else ""
        nav.append(f'<a class="{on}" href="{make_url(view=k, cat="전체")}" target="_self">{label}</a>')
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
    if current_user:
        on = " on" if sel_cat == "__scrap__" else ""
        nav.append(f'<a class="{on}" href="{make_url(cat="__scrap__")}" target="_self">내 스크랩 <span class="n">{len(scrap_items)}</span></a>')
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

    if current_user:
        st.markdown(f'<div class="user-line">{html.escape(current_user)} 님</div>', unsafe_allow_html=True)
        if st.button("키워드 설정", width="stretch"):
            settings_dialog()
        if st.button("내보내기", width="stretch"):
            st.session_state._open_export = True
        if st.button("지금 수집", width="stretch"):
            ok, msg = trigger_collect()
            (st.success if ok else st.error)(msg)
        if st.button("로그아웃", width="stretch"):
            st.session_state.auth_user = ""
            try:
                del st.query_params["auth"]
            except Exception:
                pass
            st.rerun()
    else:
        if st.button("로그인", type="primary", width="stretch"):
            need_login_msg = need_login_msg or " "
        if st.button("내보내기", width="stretch"):
            st.session_state._open_export = True
        st.caption("사번으로 로그인하면 스크랩·키워드 설정·즉시 수집을 사용할 수 있습니다.")

# ── 필터 적용 ──────────────────────────────────────────
if sel_cat == "__scrap__" and current_user:
    sc = items_to_frame(scrap_items)
    if not sc.empty:
        sc["id"] = sc["id"] if "id" in sc.columns else ""
        sc["date_dt"] = pd.to_datetime(sc["date"], errors="coerce")
        sc = sc.dropna(subset=["date_dt"])
        if "content" not in sc.columns:
            sc["content"] = ""
        filtered = sc
    else:
        filtered = df.head(0)
    list_label = "내스크랩"
elif sel_cat != "전체" and sel_cat != "__scrap__":
    filtered = df_v[df_v["category"] == sel_cat]
    list_label = sel_cat
else:
    filtered = df_v
    list_label = VIEWS[view]
if sel_src != "전체" and sel_cat != "__scrap__":
    filtered = filtered[filtered["source"] == sel_src]

with feed_col:
    if view == "trend" and sel_cat != "__scrap__":
        st.markdown('<div class="section-label">Trend — 누적 수집 데이터</div>', unsafe_allow_html=True)
        st.markdown("##### 일자별 수집 기사 (최근 14일)")
        t = df[df["date_dt"].dt.date >= today - timedelta(days=13)]
        daily = t.groupby([t["date_dt"].dt.strftime("%m/%d"), "category"]).size().reset_index(name="count")
        daily.columns = ["날짜", "카테고리", "기사 수"]
        chart1 = (
            alt.Chart(daily).mark_bar(size=20)
            .encode(
                x=alt.X("날짜:O", title=None, axis=alt.Axis(labelAngle=0)),
                y=alt.Y("기사 수:Q", title=None),
                color=alt.Color("카테고리:N",
                                scale=alt.Scale(domain=ALL_CATEGORIES,
                                                range=[CAT_CHART[c] for c in ALL_CATEGORIES]),
                                legend=alt.Legend(orient="top", title=None)),
                tooltip=["날짜", "카테고리", "기사 수"],
            ).properties(height=280)
        )
        st.altair_chart(chart1, width="stretch")
        st.markdown("##### 핵심 키워드 Top 12 (최근 7일)")
        kws = df[df["date_dt"].dt.date >= today - timedelta(days=6)].explode("keywords")["keywords"].dropna()
        if not kws.empty:
            kt = kws.value_counts().head(12).reset_index()
            kt.columns = ["키워드", "빈도"]
            chart2 = (
                alt.Chart(kt).mark_bar(size=16, cornerRadiusEnd=4, color=MOIP_COLORS[0])
                .encode(x=alt.X("빈도:Q", title=None), y=alt.Y("키워드:N", sort="-x", title=None),
                        tooltip=["키워드", "빈도"]).properties(height=300)
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
        # 통계 타일 (터치하면 해당 카테고리로 필터)
        cat_counts = df_v["category"].value_counts()
        tiles = [
            f'<a class="stat-tile" href="{make_url(cat="전체")}" target="_self">'
            f'<div class="label">수집 기사 ({VIEWS[view]})</div><div class="value">{len(df_v):,}</div></a>'
        ]
        for c in ALL_CATEGORIES:
            tiles.append(
                f'<a class="stat-tile" href="{make_url(cat=c)}" target="_self" style="border-top-color:{CAT_CHART.get(c, "#999")}">'
                f'<div class="label">{html.escape(c)}</div><div class="value">{cat_counts.get(c, 0)}</div></a>'
            )
        st.markdown(f'<div class="stat-row">{"".join(tiles)}</div>', unsafe_allow_html=True)

        q = st.text_input("검색", placeholder="검색 — 제목·요약·본문에서 찾습니다",
                          label_visibility="collapsed", key="search_q")
        if q.strip() and not filtered.empty:
            qq = q.strip().lower()
            filtered = filtered[
                filtered["title"].str.lower().str.contains(qq, regex=False)
                | filtered["summary"].str.lower().str.contains(qq, regex=False)
                | filtered["content"].str.lower().str.contains(qq, regex=False)
            ]

        n = len(filtered)
        head_txt = "내 스크랩" if sel_cat == "__scrap__" else f"기사 {n}건 · 카드를 누르면 본문이 열립니다"
        if sel_cat == "__scrap__":
            head_txt = f"내 스크랩 {n}건"
        st.markdown(f'<div class="section-label">{head_txt}</div>', unsafe_allow_html=True)
        if n == 0:
            st.warning("표시할 기사가 없습니다." if sel_cat == "__scrap__" else "조건에 맞는 기사가 없습니다.")

        MAX_SHOW = 80
        cards = ['<div class="feed">']
        for _, r in filtered.head(MAX_SHOW).iterrows():
            cat_cls = CAT_CSS_CLASS.get(r["category"], "")
            tags = "".join(f'<span class="tag-pill">#{html.escape(k)}</span>' for k in (r["keywords"] or [])[:5])
            tags_html = f'<div class="tag-row">{tags}</div>' if tags else ""
            scrapped = r["id"] in scrap_ids
            scrap_cls = " on" if scrapped else ""
            scrap_txt = "스크랩됨" if scrapped else "스크랩"
            cards.append(
                f'<div class="news-card">'
                f'<a class="scrap-btn{scrap_cls}" href="{make_url(scrap=r["id"])}" target="_self">{scrap_txt}</a>'
                f'<a class="card-main" href="{make_url(sel=r["id"])}" target="_self">'
                f'<div class="news-meta"><span class="cat-kicker {cat_cls}">{html.escape(r["category"])}</span>'
                f'<span>·</span><span>{html.escape(str(r["source"]))}</span><span>·</span><span>{human_date(r["date_dt"])}</span></div>'
                f'<div class="news-title">{html.escape(r["title"])}</div>'
                f'{tags_html}</a></div>'
            )
        cards.append("</div>")
        st.markdown("".join(cards), unsafe_allow_html=True)
        if n > MAX_SHOW:
            st.caption(f"상위 {MAX_SHOW}건 표시 중 (전체 {n}건) — 검색·필터로 좁혀 보세요.")

    st.markdown(
        f'<div style="text-align:center; color:var(--ink-3); font-size:.75rem; padding:1.2rem 0 .4rem;">'
        f'매일 09:30 · 17:00 자동 수집 · 누적 {len(df):,}건 · 마지막 수집 {df["date_dt"].max().strftime("%Y.%m.%d")}</div>',
        unsafe_allow_html=True,
    )

# ── 다이얼로그 열기 (한 실행에 하나만) ─────────────────
if sel_id:
    hit = df[df["id"] == sel_id]
    if hit.empty and scrap_items:
        sc = items_to_frame(scrap_items)
        sc["date_dt"] = pd.to_datetime(sc["date"], errors="coerce")
        sc["content"] = sc.get("content", "")
        hit = sc[sc["id"] == sel_id]
    if not hit.empty:
        article_dialog(hit.iloc[0])
elif st.session_state.pop("_open_export", False):
    export_dialog(filtered if isinstance(filtered, pd.DataFrame) else df, str(list_label))
elif need_login_msg:
    login_dialog(need_login_msg.strip())
