# IP·AI 뉴스 브리핑

지식재산처(지재처)·AI 분야 뉴스를 매일 자동 수집하여 보여주는 임원 보고용 대시보드입니다.

## 주요 기능

- **자동 수집**: 매일 KST 09:30 / 17:00 (GitHub Actions) + 대시보드 [지금 수집] 버튼으로 즉시 실행
- **카테고리**: 지재처 보도자료(전량) · 지재처 관련뉴스 · AI·지식재산 · AI 업계 (키워드 편집 가능)
- **로그인**: 아이디/비밀번호 가입 후 쿠키 자동 로그인 — 로그인 사용자만 스크랩·키워드 설정·즉시 수집 가능
- **스크랩**: 기사마다 스크랩 버튼, 내 스크랩 모아보기 (GitHub store 브랜치에 영구 저장)
- **내보내기**: 현재 목록/전체/스크랩 → 엑셀(xlsx), PDF (한글 폰트 내장)
- **기사 팝업**: 카드 클릭 시 본문 팝업, 원문 링크는 언론사 원본 주소로 복원 저장

## 파일 구성

| 파일 | 역할 |
|---|---|
| `data_pipeline.py` | 뉴스 수집기 → `data/news_YYYYMMDD.json` |
| `config/keywords.json` | 구독 키워드 (쉼표=OR, 세미콜론=AND) |
| `.github/workflows/daily_update.yml` | 자동 수집 스케줄 |
| `app.py` | Streamlit 대시보드 |
| `tools_backfill.py` | 구글뉴스 링크 원문 복원 보수 도구 (1회성) |
| `store` 브랜치 | `users.json`(계정) · `scraps.json`(스크랩) — main과 분리되어 저장해도 재배포 안 됨 |

## 로컬 실행

```bash
pip install -r requirements.txt
python data_pipeline.py
streamlit run app.py
```

## 배포 (Streamlit Community Cloud)

1. share.streamlit.io → New app → 이 저장소 / `app.py` → Deploy
2. **App settings → Secrets** (필수 — 없으면 로그인·스크랩·키워드 영구저장·즉시수집 불가):

   ```toml
   GITHUB_TOKEN = "repo, workflow 권한이 있는 토큰"
   GITHUB_REPO = "UNJUNGSAM/ip-ai-news-brief"
   AUTH_SECRET = "아무_긴_임의_문자열"
   ```

3. 갤럭시탭/폰 브라우저에서 열고 "홈 화면에 추가"

## 기타

- AI 3줄 요약(선택): 저장소 Secrets에 `OPENAI_API_KEY` 등록 시 활성화
- PDF 폰트: 나눔고딕(오픈폰트라이선스, `fonts/`)
