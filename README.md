# IP·AI 뉴스 브리핑

지식재산처(지재처)·AI 분야 뉴스를 매일 자동 수집하여 보여주는 임원 보고용 대시보드입니다.

## 주요 기능

- **자동 수집**: 매일 KST 09:30 / 17:00 (GitHub Actions) + 대시보드 [지금 수집] 버튼으로 즉시 실행
- **카테고리**: 지재처 보도자료(전량) · 지재처 관련뉴스 · AI·지식재산 · AI 업계 (키워드 편집 가능)
- **로그인 없음**: 링크만 있으면 누구나 보기·스크랩·내보내기·AI 사용. 관리 기능(키워드 설정·지금 수집)만 관리자 암호(ADMIN_PIN)로 보호
- **스크랩**: 기사마다 스크랩 버튼 → 팀 공용 스크랩(모두가 함께 보는 목록, GitHub store 브랜치에 저장)
- **내보내기**: 현재 목록/전체/스크랩 → 엑셀(xlsx), PDF (한글 폰트 내장)
- **기사 팝업**: 카드 클릭 시 본문 팝업, 원문 링크는 언론사 원본 주소로 복원 저장

## 파일 구성

| 파일 | 역할 |
|---|---|
| `data_pipeline.py` | 뉴스 수집기 → `data/news_YYYYMMDD.json` |
| `config/keywords.json` | 구독 키워드 (쉼표=OR, 세미콜론=AND) |
| `.github/workflows/daily_update.yml` | 자동 수집 스케줄 |
| `.github/workflows/keep_alive.yml` | 앱 깨어있기 — KST 07/11/15/19시에 방문해 잠자기 방지 |
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
   ADMIN_PIN = "관리자 암호 (키워드 설정·지금 수집 보호용, 예: 4823)"
   GEMINI_API_KEY = "AI 요약·브리핑용 Gemini API 키"
   # 모델(선택) — 미지정 시 아래 기본값. 실제 존재하는 정확한 모델 ID를 넣으세요.
   GEMINI_SUMMARY_MODEL = "gemini-3.1-flash-lite"   # 기사 요약(빠름, 사고수준 low)
   GEMINI_BRIEF_MODEL = "gemini-3.5-flash"          # 트렌드 브리핑(사고수준 low)
   ```
   - `ADMIN_PIN`을 비워두면 관리 기능도 누구나 쓸 수 있습니다(신뢰 팀이면 생략 가능).
   - AI 요약/브리핑은 사고수준(thinking) low로 호출하며, 지원하지 않는 모델이면 자동으로 빼고 재시도합니다.

3. 갤럭시탭/폰 브라우저에서 열고 "홈 화면에 추가" — 로그인 없이 바로 열립니다

## AI 3줄 요약 (선택)

- Streamlit Secrets에 `GEMINI_API_KEY`(Google AI Studio 키)를 넣으면 활성화됩니다.
- 기사 팝업에서 [AI 3줄 요약 생성] 버튼을 누른 사람만 그때그때 생성 → 비용 최소화.
- 한 번 생성한 요약은 `store` 브랜치(`ai_summaries.json`)에 저장되어 다음부터 재사용(무료).
- 모델 변경: `GEMINI_MODEL = "gemini-2.0-flash"` (기본값). 본문이 없는 기사는 요약 불가.

## 기타

- PDF 폰트: 나눔고딕(오픈폰트라이선스, `fonts/`)
