# MARKET PULSE — Google AI Studio 실행 오류 복구

## 1. 근본 원인
업로드된 `economic-app.zip`에는 기존 Python/Streamlit 앱(`app.py`)과 다수의 Python 모듈이 존재했으나, `package.json`은 Vite 개발 서버만 지정했고 **Vite용 `index.html` 및 웹 프런트엔드 진입 파일이 없었습니다.** `package.json`의 의존성 목록도 사실상 비어 있었으며 JavaScript 웹앱으로 실행 가능한 구조가 아니었습니다.

따라서 원본 ZIP만으로는 Google AI Studio의 JavaScript 웹 미리보기에 기존 Python Streamlit 앱을 직접 표시할 수 없습니다. 단순히 npm 패키지 설치만 성공한다고 기존 Python 앱이 Vite에서 실행되지는 않습니다.

## 2. 수정한 부분
- `package.json`: 외부 npm 의존성이 **0개**인 Node.js 기반 웹서버로 교체. npm 설치 실패 위험 최소화
- `server.mjs`: Node 기본 HTTP 서버, `PORT` 환경 변수 지원, 0.0.0.0 바인딩, `/api/health` 상태 확인, 허용한 정적 파일만 서빙. Python 소스 및 비밀키 파일 웹 노출 차단
- `index.html`, `styles.css`, `src/app.js`, `src/analytics.js`: 반응형 신규 웹 미리보기 제작
- `assets/catalog.json`: 업로드된 실제 Python `stock_catalog.py`로부터 국내 기업 30개 종목 목록 생성
- `assets/favicon.svg`: 간결한 차트/펄스 탭 아이콘
- `scripts/build.mjs`: 외부 의존성 없는 정적 프런트엔드 빌드
- `tests_web/*.test.mjs`: CSV 파서, 출처, 테스트 계산, 서버 동작 및 민감 파일 접근 차단 검사
- `.gitignore`: `.env.local`, `.streamlit/secrets.toml`, `dist`, `node_modules` 제외
- `vite.config.ts`, `tsconfig.json`: 더 이상 사용하지 않아 제외

### 의도적으로 보존한 부분
기존 `app.py`, `market_data.py`, `prediction_model.py`, `langchain_analysis.py`, `news_collector.py`, `requirements.txt`, 테스트 및 원본 데이터를 그대로 보존했습니다. Python 프로젝트가 JavaScript 미리보기와 **별개로 실행**되도록 유지했습니다.

## 3. 실제 실행 방법 — Google AI Studio 웹 미리보기
이 ZIP을 Google AI Studio에 프로젝트로 가져오거나 로컬 Node.js 20 이상에서 실행:

```bash
npm install
npm run dev
```

기본 주소 `http://localhost:3000` 또는 AI Studio에서 제공하는 미리보기 페이지로 접속합니다. 네트워크 설정에 따라 다른 포트를 사용하는 환경에서는 `PORT` 환경 변수를 통해 포트를 지정할 수 있습니다.

빌드 및 테스트:
```bash
npm test
npm run build
```

이 구성은 외부 npm 라이브러리가 없으므로 해당 프로젝트 자체의 의존성 설치가 필요하지 않습니다.

## 4. 웹 화면에서 실제 작동하는 기능
- 30개 기업명·종목코드·업종 검색
- 사용자 CSV 여러 개 업로드 (`Date, Close`, 선택적 `Volume` 및 `Open, High, Low`)
- 업로드된 실제 종가 기반 현재 표시가 아닌 **마지막 거래일 종가**, 등락률, 20일 평균, 20일 변동성, 최근 252거래일 최고/최저
- 업로드된 실제 데이터로 SVG 주가 차트, 가격 급변 Z점수 탐지
- 뉴스 URL 입력 및 직접 붙여 넣은 기사 제목/본문의 **규칙 기반 키워드 분석** (AI 모델 분석으로 표시하지 않음)
- 파일을 가져오지 않았을 때 주가 수치나 분석 결과를 임의로 생성하지 않음

## 5. 중요한 한계
- **Google AI Studio의 이 웹 미리보기는 Python Streamlit 런타임이 아닙니다.** 업로드된 Python 기반 뉴스 자동 수집, 시장 가격 수집, sklearn 학습·백테스트와 외부 AI API 기능은 미리보기에서 직접 실행되지 않습니다. 해당 기능을 웹에서 동일하게 구현하려면 API 백엔드 구성과 별도 배포가 필요합니다.
- 뉴스 URL만 입력해 기사 본문을 자동 크롤링하거나 Groq/Grok API에 요청하는 기능은 **이 미리보기에서 구현되지 않았습니다**. 웹 화면에서는 직접 붙여 넣은 기사 텍스트를 규칙 기반으로 분석합니다.
- CSV는 브라우저 안에서만 처리되고 새로고침 시 업로드 상태가 초기화됩니다.
- 기사 링크 및 업로드된 데이터의 출처와 진위를 사용자가 확인해야 합니다.
- 실제 Google AI Studio의 호스팅 환경에서 설치/미리보기 성공 여부는 외부 플랫폼 권한이 없어 직접 확인할 수 없습니다. 로컬 Node.js로 서버·빌드 테스트를 실행해 검증합니다.

## 6. 원래 MARKET PULSE Python 앱 실행법
Python 3.12 기반 PC 환경에서:
```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```
기존 Python 프로젝트는 변경하지 않았습니다. API 키는 `.streamlit/secrets.toml` 등 비공개 설정에만 저장하고 ZIP이나 GitHub에 포함시키지 마세요.

## 7. 프로젝트 구성 구분
- 웹 미리보기: `package.json` → `server.mjs` → `index.html` → `src/`
- 원본 전체 기능: `app.py` 및 다수의 Python 파일, `requirements.txt`

웹 미리보기와 Python 전체 분석기는 서로 다른 런타임을 사용합니다.
