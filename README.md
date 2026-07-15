# 📰 IP·AI 뉴스 브리핑

지식재산처(지재처)·AI·AI+IP 분야의 뉴스를 **매일 아침 자동 수집**하여
갤럭시탭에서 보기 좋은 3단 리더 화면으로 보여주는 임원 보고용 대시보드입니다.

## 구성

| 파일 | 역할 |
|---|---|
| `data_pipeline.py` | 수집기 — ① 지재처 보도자료 전량 ② 구독 키워드 구글 뉴스 → `data/news_YYYYMMDD.json` |
| `config/keywords.json` | 구독 키워드 설정 (대시보드 ⚙️ 설정에서 편집 가능) |
| `.github/workflows/daily_update.yml` | 매일 KST 07:00 GitHub Actions 자동 실행 + 자동 커밋 |
| `app.py` | Streamlit 3단 리더 (좌: 카테고리 / 중: 기사 목록 / 우: 본문) |

## 키워드 규칙

- 쉼표(,) = 같은 의미 묶음(OR) / 세미콜론(;) = 반드시 함께(AND)
- 기본값: `AI, 인공지능 ; 지식재산, 특허, 디자인`
  → (AI 또는 인공지능) 이면서 (지식재산·특허·디자인 중 하나 이상)
- 지재처 보도자료는 키워드와 무관하게 항상 전량 수집됩니다.

## 로컬 실행

```bash
pip install -r requirements.txt
python data_pipeline.py      # 뉴스 수집
streamlit run app.py         # 대시보드 실행
```

## 배포 (Streamlit Community Cloud)

1. https://share.streamlit.io 에서 GitHub 계정으로 로그인
2. **New app** → 이 저장소 선택 → Main file: `app.py` → **Deploy**
3. (중요) App settings → **Secrets** 에 아래 두 줄 입력 → 웹 화면의 ⚙️ 설정에서
   키워드를 저장하면 GitHub에 자동 커밋되어 다음날 수집부터 반영됩니다.

   ```toml
   GITHUB_TOKEN = "ghp_로_시작하는_새_토큰"
   GITHUB_REPO = "UNJUNGSAM/ip-ai-news-brief"
   ```

4. 생성된 URL을 갤럭시탭 브라우저로 열고 **"홈 화면에 추가"** 하면 앱처럼 사용됩니다.

## 기타

- **AI 3줄 요약(선택)**: 저장소 Settings → Secrets → `OPENAI_API_KEY` 등록 시 활성화
- **수동 수집**: GitHub → Actions 탭 → Daily News Update → Run workflow
