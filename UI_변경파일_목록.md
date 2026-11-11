# 이번 UI 통합 개정에서 바뀐 파일만 보기

### 실제 UI 필수 파일

- **`app.py`** — 기존 파일과 교체
- **`market_ui.py`** — 새 파일 추가
- **`assets/company_icons/005930.png`** — 삼성전자 식별 아이콘 추가
- **`assets/company_icons/000660.png`** — SK하이닉스 식별 아이콘 추가
- **`assets/company_icons/005380.png`** — 현대자동차 식별 아이콘 추가
- **`assets/company_icons/000270.png`** — 기아 식별 아이콘 추가
- **`assets/company_icons/035420.png`** — NAVER 식별 아이콘 추가
- **`assets/company_icons/035720.png`** — 카카오 식별 아이콘 추가
- **`.streamlit/config.toml`** — 밝은 테마 설정 추가

### 문서 및 테스트

- `tests/test_market_ui.py` — UI 로직 테스트 추가
- `README.md` — UI 설명 갱신
- `CHANGELOG.md` — 변경 기록 갱신
- `TEST_REPORT.md` — 테스트 결과 갱신
- `GITHUB_UI_교체안내.md` — GitHub 업로드/교체 사용법 추가

### 그대로 두는 파일

`stock_core.py`, `market_data.py`, `technical_indicators.py`, `news_analyzer.py`, `news_collector.py`, `disclosure_collector.py`, `prediction_model.py`, `backtesting.py`, `kis_market.py`, `config.py`, `collect_real_data.py`, `requirements.txt` 등 기존 분석 모듈.

**중요:** `data_cache/`에 수집한 실제 데이터와 `.streamlit/secrets.toml`에 설정한 개인 API 키는 삭제하거나 GitHub에 공개하지 마세요.
