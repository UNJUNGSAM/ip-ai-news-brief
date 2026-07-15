# 📰 IP·AI 뉴스 브리핑

지식재산(지식재산처/구 특허청)·AI·AI+IP 분야의 뉴스를 **매일 아침 자동 수집·요약**하여
갤럭시탭에서 보기 좋게 보여주는 임원 보고용 대시보드입니다.

## 구성

| 파일 | 역할 |
|---|---|
| `data_pipeline.py` | 뉴스 수집기 — 지식재산처 보도자료 RSS + 구글 뉴스 검색 RSS를 수집해 `data/news_YYYYMMDD.json` 저장 |
| `.github/workflows/daily_update.yml` | 매일 KST 07:00에 GitHub 서버가 수집기를 자동 실행 후 커밋 |
| `app.py` | Streamlit 대시보드 (뉴스 피드 + 트렌드 차트) |

## 로컬 실행

```bash
pip install -r requirements.txt
python data_pipeline.py      # 오늘 뉴스 수집
streamlit run app.py         # 대시보드 실행
```

## 배포 (Streamlit Community Cloud)

1. https://share.streamlit.io 에서 GitHub 계정으로 로그인
2. **New app** → 이 저장소 선택 → Main file: `app.py` → **Deploy**
3. 생성된 URL을 갤럭시탭 브라우저로 열고 **"홈 화면에 추가"** 하면 앱처럼 사용 가능

GitHub Actions가 매일 아침 데이터를 커밋하면 Streamlit Cloud가 자동으로 최신 뉴스를 반영합니다.

## 설정 변경

- **수집 키워드 변경**: `data_pipeline.py` 상단의 `GOOGLE_NEWS_QUERIES` 수정
- **AI 3줄 요약 활성화(선택)**: 저장소 Settings → Secrets and variables → Actions →
  `OPENAI_API_KEY` 등록 (없으면 기사 앞 3문장 요약으로 자동 대체)
- **수동 수집 실행**: GitHub 저장소 → Actions 탭 → Daily News Update → Run workflow
