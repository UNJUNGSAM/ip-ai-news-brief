# -*- coding: utf-8 -*-
"""
════════════════════════════════════════════════════════════════════
 IP·AI 뉴스 브리핑 — 데이터 파이프라인 (모듈 1)
════════════════════════════════════════════════════════════════════
 역할  : ① 지식재산처(지재처) 보도자료 전량 수집
         ② config/keywords.json의 구독 키워드로 구글 뉴스 수집
         → 날짜별 JSON 파일(data/news_YYYYMMDD.json)로 저장
 실행  : python data_pipeline.py
 자동화: GitHub Actions가 매일 아침 7시(KST)에 자동 실행 (모듈 2)
════════════════════════════════════════════════════════════════════
"""

import base64
import json
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urljoin

import feedparser
import requests
from bs4 import BeautifulSoup

# ── 회사 PC 등 SSL 검사(사내 보안 프로그램) 환경 대응 ──────────────
try:
    import truststore

    truststore.inject_into_ssl()
except Exception:
    pass

# ════════════════════════════════════════════════════════════════════
# 기본 설정
# ════════════════════════════════════════════════════════════════════

KST = timezone(timedelta(hours=9))
TODAY = datetime.now(KST).date()

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CONFIG_PATH = BASE_DIR / "config" / "keywords.json"

# 구글 뉴스: 최근 몇 시간 이내 기사만 수집할지
LOOKBACK_HOURS = 48
# 원문 본문 수집을 시도할 최대 기사 수 (실행 시간 제한)
# 구글뉴스 중계링크는 봇 확인 페이지가 떠서 반드시 원문 복원이 필요 → 넉넉하게
MAX_ARTICLE_FETCH = 120

# 지식재산처(지재처) 보도자료 공식 RSS — 전량 수집 대상
MOIP_CATEGORY = "지재처 보도자료"
MOIP_RSS_URL = "https://www.moip.go.kr/ko/report/UXmlRssApp.do?menuCd=SCD0200618"
MOIP_BASE_URL = "https://www.moip.go.kr"

# 기본 구독 키워드 — 대시보드의 [설정]에서 자유롭게 수정·추가할 수 있습니다.
# (쉼표 안 = OR, 그룹 사이 = AND)
DEFAULT_CONFIG = {
    "subscriptions": [
        {
            "name": "지재처 관련뉴스",
            "groups": [["지식재산처", "지재처", "특허청"]],
        },
        {
            "name": "AI·지식재산",
            "groups": [["AI", "인공지능"], ["지식재산", "특허", "디자인"]],
        },
        {
            "name": "AI 업계",
            "groups": [["오픈AI", "챗GPT", "앤스로픽", "클로드", "제미나이", "엔비디아", "생성형 AI"]],
        },
    ]
}

# 기사에서 추출할 핵심 키워드 태그 후보
KEYWORD_TAGS = [
    "특허", "상표", "디자인", "실용신안", "저작권", "지식재산", "IP",
    "AI", "인공지능", "생성형", "챗GPT", "LLM", "오픈AI", "구글", "네이버",
    "심사", "출원", "등록", "소송", "분쟁", "침해", "라이선스",
    "WIPO", "국제", "미국", "중국", "유럽", "일본",
    "반도체", "바이오", "데이터", "표준", "스타트업", "중소기업",
]

REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) NewsBriefBot/1.0"}


# ════════════════════════════════════════════════════════════════════
# 구독 키워드 설정 로드
# ════════════════════════════════════════════════════════════════════

def load_keyword_config() -> dict:
    """config/keywords.json 로드 (없으면 기본값 생성)"""
    try:
        if CONFIG_PATH.exists():
            cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if cfg.get("subscriptions"):
                return cfg
    except Exception as e:
        print(f"  [경고] 키워드 설정 읽기 실패, 기본값 사용 ({e})")
    CONFIG_PATH.parent.mkdir(exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2), encoding="utf-8")
    return DEFAULT_CONFIG


def matches_groups(text: str, groups: list[list[str]]) -> bool:
    """구독 조건(그룹 사이 AND, 그룹 안 OR)이 기사 텍스트에서 실제로 성립하는지 검증.
    구글 뉴스는 관련기사 링크 등 페이지 부속 텍스트까지 검색해 엉뚱한 기사를
    끼워 넣는 경우가 있어, 제목·요약·본문에 키워드가 진짜 있는지 재확인한다."""
    low = (text or "").lower()
    return all(
        any(w.strip().lower() in low for w in g if w.strip())
        for g in groups if g
    )


def build_query(groups: list[list[str]]) -> str:
    """동의어 그룹 목록 → 구글 뉴스 검색식.
    [["AI","인공지능"], ["특허","디자인"]] → ("AI" OR "인공지능") ("특허" OR "디자인")
    (그룹 사이는 AND, 그룹 안은 OR)"""
    parts = []
    for group in groups:
        words = [w.strip() for w in group if w.strip()]
        if words:
            parts.append("(" + " OR ".join(f'"{w}"' for w in words) + ")")
    return " ".join(parts) + " when:2d"


# ════════════════════════════════════════════════════════════════════
# 공통 유틸
# ════════════════════════════════════════════════════════════════════

def http_get(url: str, timeout: int = 15) -> requests.Response | None:
    """URL 요청 (실패해도 None 반환, 절대 중단되지 않음)"""
    try:
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=timeout)
        resp.raise_for_status()
        return resp
    except Exception as e:
        print(f"  [경고] 요청 실패: {url[:80]} ({type(e).__name__})")
        return None


def clean_html(raw_html: str) -> str:
    """HTML 태그 제거 후 순수 텍스트만 추출"""
    try:
        soup = BeautifulSoup(raw_html or "", "html.parser")
        # 보도자료 상단의 제목 반복 테이블은 제거
        for table in soup.find_all("table"):
            table.decompose()
        text = soup.get_text(separator=" ", strip=True)
        return re.sub(r"\s+", " ", text).strip()
    except Exception:
        return re.sub(r"<[^>]+>", " ", raw_html or "").strip()


def first_sentences(text: str, n: int = 3, max_chars: int = 350) -> str:
    """텍스트에서 앞부분 n문장 추출 (한국어 '~다.' 기준)"""
    if not text:
        return ""
    sentences = re.split(r"(?<=[.!?다])\s+", text)
    picked = " ".join(sentences[:n]).strip()
    if len(picked) > max_chars:
        picked = picked[:max_chars].rstrip() + "…"
    return picked


def extract_keywords(text: str, max_tags: int = 5) -> list[str]:
    """제목+요약에서 핵심 키워드 태그 추출"""
    found = []
    for tag in KEYWORD_TAGS:
        if tag in text and tag not in found:
            found.append(tag)
        if len(found) >= max_tags:
            break
    return found


# ════════════════════════════════════════════════════════════════════
# AI 요약 (선택 기능) — API 키를 넣으면 자동으로 활성화됩니다
# ════════════════════════════════════════════════════════════════════

def ai_summarize(text: str) -> str | None:
    """
    AI 3줄 요약 함수 (템플릿).

    GitHub 저장소 → Settings → Secrets → OPENAI_API_KEY 등록 시 작동.
    키가 없으면 None을 반환하고 호출부에서 '앞 3문장 요약'으로 대체됩니다.
    """
    import os

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key or not text:
        return None

    try:
        # ── OpenAI API 호출 템플릿 ──────────────────────────────
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": "너는 지식재산·AI 분야 전문 뉴스 요약가다. 임원 보고용으로 핵심만 3줄로 요약해라. 각 줄은 '- '로 시작한다."},
                    {"role": "user", "content": text[:4000]},
                ],
                "temperature": 0.3,
                "max_tokens": 300,
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
        # ── (참고) Google Gemini API를 쓰려면 ──────────────────
        # 환경변수 GEMINI_API_KEY 등록 후 아래 형태로 교체:
        # resp = requests.post(
        #     f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}",
        #     json={"contents": [{"parts": [{"text": "다음 뉴스를 임원 보고용 3줄로 요약: " + text[:4000]}]}]},
        #     timeout=30,
        # )
        # return resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        print(f"  [경고] AI 요약 실패, 기본 요약으로 대체 ({type(e).__name__})")
        return None


# ════════════════════════════════════════════════════════════════════
# 수집기 1 — 지식재산처(지재처) 보도자료 : RSS 전량 수집
# ════════════════════════════════════════════════════════════════════

def fetch_moip_detail_date(url: str) -> str | None:
    """보도자료 상세 페이지에서 등록일(YYYY-MM-DD) 추출"""
    resp = http_get(url, timeout=10)
    if resp is None:
        return None
    m = re.search(r"20\d{2}-\d{2}-\d{2}", resp.text)
    return m.group() if m else None


def collect_moip(known_links: set, known_titles: set) -> list[dict]:
    """지재처 보도자료 RSS 전량 수집 (이미 수집된 것은 건너뜀)"""
    print(f"\n[1/2] 지식재산처(지재처) 보도자료 수집 중... (전량, 신규분만)")
    articles = []
    resp = http_get(MOIP_RSS_URL)
    if resp is None:
        return articles

    feed = feedparser.parse(resp.content)
    entries = feed.entries
    print(f"  RSS 항목 {len(entries)}건 확인")

    new_count = 0
    for i, entry in enumerate(entries):
        try:
            title = (entry.get("title") or "").strip()
            link = urljoin(MOIP_BASE_URL, entry.get("link") or "")
            title_key = re.sub(r"\s+", "", title)
            if not title or link in known_links or title_key in known_titles:
                continue

            # 상세 페이지에서 등록일 확인 (실패 시 오늘 날짜)
            pub_date = fetch_moip_detail_date(link) or str(TODAY)
            time.sleep(0.1)  # 서버 부담 방지

            body = clean_html(entry.get("summary", ""))
            content = body[:6000]
            summary = ai_summarize(body) or first_sentences(body, 3)

            articles.append({
                "title": title,
                "link": link,
                "category": MOIP_CATEGORY,
                "date": pub_date,
                "summary": summary,
                "content": content,
                "source": "지식재산처",
                "keywords": extract_keywords(title + " " + summary),
            })
            known_links.add(link)
            known_titles.add(title_key)
            new_count += 1
            if new_count % 25 == 0:
                print(f"  ... {new_count}건 수집 (전체 {len(entries)}건 중 {i + 1}번째 확인)")
        except Exception as e:
            print(f"  [경고] 항목 처리 실패 ({type(e).__name__}: {e})")
            continue
    print(f"  신규 {new_count}건 수집 완료")
    return articles


# ════════════════════════════════════════════════════════════════════
# 수집기 2 — 구글 뉴스 RSS (구독 키워드 검색)
# ════════════════════════════════════════════════════════════════════

def resolve_gnews_link(link: str) -> str | None:
    """구글 뉴스 중계 링크에서 원문 기사 URL 복원 시도 (실패해도 무방)"""
    m = re.search(r"articles/([^?/]+)", link)
    if not m:
        return None
    art_id = m.group(1)

    # 방법 1) 구형 링크: base64 안에 원문 URL이 그대로 들어 있음
    try:
        decoded = base64.urlsafe_b64decode(art_id + "===")
        m2 = re.search(rb"https?://[^\x00-\x20\x80-\xff]+", decoded)
        if m2:
            url = m2.group().decode("ascii", errors="ignore").rstrip("\\\"'")
            if len(url) > 12:
                return url
    except Exception:
        pass

    # 방법 2) 신형 링크(2024~): 기사 페이지의 서명값으로 구글 내부 API 조회
    try:
        resp = http_get(link, timeout=12)
        if resp is None:
            return None
        m_ts = re.search(r'data-n-a-ts="([^"]+)"', resp.text)
        m_sg = re.search(r'data-n-a-sg="([^"]+)"', resp.text)
        if not (m_ts and m_sg):
            return None
        payload = (
            '[[["Fbv4je","[\\"garturlreq\\",[[\\"X\\",\\"X\\",[\\"X\\",\\"X\\"],'
            "null,null,1,1,\\\"US:en\\\",null,1,null,null,null,null,null,0,1],"
            '\\"X\\",\\"X\\",1,[1,1,1],1,1,null,0,0,null,0],'
            f'\\"{art_id}\\",{m_ts.group(1)},\\"{m_sg.group(1)}\\"]",null,"generic"]]]'
        )
        api = requests.post(
            "https://news.google.com/_/DotsSplashUi/data/batchexecute",
            data={"f.req": payload},
            headers={**REQUEST_HEADERS, "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
            timeout=12,
        )
        # 구글 응답은 URL의 특수문자를 유니코드 이스케이프로 보낸다
        # (예: '=' → '=', '&' → '&'). 게다가 백슬래시가 이중으로
        # escape되어 있어, 종료 지점(\") 전까지 통째로 잡은 뒤 이스케이프를
        # 해제해야 뒤쪽(?idxno=12345)이 잘리지 않는다.
        tail = api.text.split("garturlres")[-1]
        m_url = re.search(r'https?://.+?(?=\\",|"\])', tail)
        if not m_url:
            return None
        raw = m_url.group()
        raw = raw.replace("\\\\", "\\")  # 이중 백슬래시 → 단일
        raw = re.sub(r"\\u([0-9a-fA-F]{4})", lambda mm: chr(int(mm.group(1), 16)), raw)
        raw = raw.replace("\\/", "/")
        return raw
    except Exception:
        return None


# 오류/안내 페이지가 본문으로 잘못 수집되는 것을 막는 문구 목록
ERROR_PAGE_SIGNS = [
    "페이지를 찾을 수 없", "요청하신 페이지", "존재하지 않는 페이지",
    "잘못된 접근", "삭제되었거나", "삭제되어 사용할 수 없", "이용에 불편을",
    "점검 중입니다", "주소가 잘못", "찾으시는 페이지", "변경 또는 삭제",
]

# 본문이 아닌 사이트 메뉴/광고/저작권 문단을 걸러내는 문구 목록
JUNK_PARAGRAPH_SIGNS = [
    "즐겨찾기", "시작페이지", "회원가입", "로그인", "무단전재", "무단 전재",
    "재배포 금지", "구독하기", "구독신청", "네이버 뉴스스탠드", "저작권자 ©",
    "패밀리사이트", "저작권보호", "개인정보취급방침", "개인정보처리방침",
    "광고안내", "기사제보", "정기간행물", "등록번호", "청소년보호책임자",
    "발행·편집인", "All rights reserved", "Copyright", "ⓒ",
]

# 언론사 본문 영역 선택자 (위에서부터 우선 적용 — 없으면 페이지 전체 <p>)
CONTENT_SELECTORS = [
    "#article-view-content-div",   # ndsoft 계열 (특허뉴스 등 다수 전문지·지역지)
    "#articleBody", "#article-body", "#newsct_article", "#articeBody",
    "[itemprop='articleBody']", ".article_body", ".article-body",
    ".news_end", ".article_txt", ".view_con", "article",
]


def fetch_article_body(url: str) -> str:
    """기사 원문 페이지에서 본문 텍스트 추출 (실패 시 빈 문자열)"""
    resp = http_get(url, timeout=8)
    if resp is None:
        return ""
    try:
        soup = BeautifulSoup(resp.text, "html.parser")
        for bad in soup.find_all(["script", "style", "nav", "footer", "header", "aside"]):
            bad.decompose()

        # 1) 본문 영역을 정확히 찾을 수 있으면 그 안에서만 추출
        container = None
        for sel in CONTENT_SELECTORS:
            try:
                container = soup.select_one(sel)
            except Exception:
                container = None
            if container is not None:
                break
        scope = container if container is not None else soup

        paragraphs = [p.get_text(strip=True) for p in scope.find_all("p")]
        if not paragraphs and container is not None:
            paragraphs = [container.get_text(" ", strip=True)]
        clean_paras = [
            p for p in paragraphs
            if len(p) > 30 and not any(sign in p for sign in JUNK_PARAGRAPH_SIGNS)
        ]
        body = re.sub(r"\s+", " ", " ".join(clean_paras)).strip()
        if len(body) < 80 or any(sign in body[:250] for sign in ERROR_PAGE_SIGNS):
            return ""  # 오류 페이지이거나 본문 추출 실패
        return body[:3000]
    except Exception:
        return ""


def collect_google_news(subscriptions: list[dict], known_links: set, known_titles: set) -> list[dict]:
    """구독 키워드별 구글 뉴스 RSS 수집"""
    print("\n[2/2] 구글 뉴스 수집 중... (구독 키워드)")
    articles = []
    cutoff_utc = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
    fetch_budget = MAX_ARTICLE_FETCH

    for sub in subscriptions:
        name = sub.get("name", "구독")
        query = build_query(sub.get("groups", []))
        if query.strip() == "when:2d":
            continue
        url = f"https://news.google.com/rss/search?q={quote(query)}&hl=ko&gl=KR&ceid=KR:ko"
        print(f"  구독 [{name}] 검색식: {query}")
        resp = http_get(url)
        if resp is None:
            continue
        feed = feedparser.parse(resp.content)

        for entry in feed.entries[:30]:
            try:
                raw_title = (entry.get("title") or "").strip()
                # 구글 뉴스 제목은 "기사제목 - 언론사" 형식
                source_name = ""
                title = raw_title
                if " - " in raw_title:
                    title, source_name = raw_title.rsplit(" - ", 1)
                if hasattr(entry, "source") and getattr(entry.source, "title", ""):
                    source_name = entry.source.title

                # 최근 기사만
                pub = entry.get("published_parsed")
                if pub:
                    pub_dt = datetime(*pub[:6], tzinfo=timezone.utc)
                    if pub_dt < cutoff_utc:
                        continue
                    pub_date = str(pub_dt.astimezone(KST).date())
                else:
                    pub_date = str(TODAY)

                link = entry.get("link") or ""
                title_key = re.sub(r"\s+", "", title)
                if not title or link in known_links or title_key in known_titles:
                    continue

                # 원문 URL 복원 후 본문 수집 시도 (실패하면 제목으로 대체)
                summary, content, real_url = "", "", None
                if fetch_budget > 0:
                    fetch_budget -= 1
                    real_url = resolve_gnews_link(link)
                    if real_url:
                        content = fetch_article_body(real_url)
                        summary = ai_summarize(content) or first_sentences(content, 3)
                if len(summary) < 40:
                    summary = clean_html(entry.get("summary", ""))
                    if len(summary) < 10 or summary.startswith(title[:20]):
                        summary = title

                # 2차 검증: 기사 텍스트에 구독 키워드가 실제로 있는지 확인
                if not matches_groups(f"{title} {summary} {content}", sub.get("groups", [])):
                    print(f"  - 제외(키워드 불일치): {title[:40]}")
                    continue

                # 원문 복원 실패 시 구글 검색 링크로 대체 (봇 확인 페이지 방지)
                if real_url:
                    final_link = real_url
                elif "news.google.com" in link:
                    final_link = f"https://news.google.com/search?q={quote(title)}&hl=ko&gl=KR&ceid=KR:ko"
                else:
                    final_link = link

                articles.append({
                    "title": title,
                    "link": final_link,
                    "category": name,
                    "date": pub_date,
                    "summary": summary,
                    "content": content,
                    "source": source_name or "구글 뉴스",
                    "keywords": extract_keywords(title + " " + summary),
                })
                known_titles.add(title_key)
                known_links.add(link)
                print(f"  + [{source_name}] {title[:45]}")
            except Exception as e:
                print(f"  [경고] 항목 처리 실패 ({type(e).__name__}: {e})")
                continue
    return articles


# ════════════════════════════════════════════════════════════════════
# 저장 및 메인
# ════════════════════════════════════════════════════════════════════

def load_known_articles() -> tuple[set, set]:
    """기존 수집 데이터에서 (링크, 제목) 집합을 만들어 중복 수집 방지"""
    known_links, known_titles = set(), set()
    for f in sorted(DATA_DIR.glob("news_*.json")):
        try:
            for item in json.loads(f.read_text(encoding="utf-8")):
                known_links.add(item.get("link", ""))
                known_titles.add(re.sub(r"\s+", "", item.get("title", "")))
        except Exception as e:
            print(f"  [경고] 기존 파일 읽기 실패: {f.name} ({e})")
    return known_links, known_titles


def save_articles(articles: list[dict]) -> Path:
    """오늘 날짜 파일에 저장 (같은 날 재실행 시 병합)"""
    DATA_DIR.mkdir(exist_ok=True)
    out_path = DATA_DIR / f"news_{TODAY.strftime('%Y%m%d')}.json"

    existing = []
    if out_path.exists():
        try:
            existing = json.loads(out_path.read_text(encoding="utf-8"))
        except Exception:
            existing = []

    existing_links = {a.get("link") for a in existing}
    merged = existing + [a for a in articles if a["link"] not in existing_links]
    out_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def main():
    print("=" * 60)
    print(f" IP·AI 뉴스 브리핑 파이프라인 — {datetime.now(KST):%Y-%m-%d %H:%M} (KST)")
    print("=" * 60)

    config = load_keyword_config()
    subs = config.get("subscriptions", [])
    print(f"구독 키워드 {len(subs)}건: {', '.join(s.get('name', '?') for s in subs)}")

    DATA_DIR.mkdir(exist_ok=True)
    known_links, known_titles = load_known_articles()
    print(f"기존 수집 기사: {len(known_links)}건 (중복 제외 처리)")

    collected = []
    collected += collect_moip(known_links, known_titles)
    collected += collect_google_news(subs, known_links, known_titles)

    out_path = save_articles(collected)
    print("\n" + "=" * 60)
    print(f" 수집 완료: 신규 {len(collected)}건 → {out_path.name}")
    by_cat = {}
    for a in collected:
        by_cat[a["category"]] = by_cat.get(a["category"], 0) + 1
    for cat, n in by_cat.items():
        print(f"   - {cat}: {n}건")
    print("=" * 60)


if __name__ == "__main__":
    main()
