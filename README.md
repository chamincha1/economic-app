# MARKET PULSE — 실제 자료 기반 국내 주식시장 분석

## 2026-11-11 · UI 통합 개선 (사이드바/아이콘/증권형 표)

이 ZIP에는 이전 사이드바 UI 개정과 새 **종목 구분 아이콘, 실제 주가 기반 스파크라인, 검색·정렬되는 증권 사이트형 시세표**가 하나로 통합되어 있습니다. 자세한 파일 교체 방법은 [`GITHUB_UI_교체안내.md`](GITHUB_UI_교체안내.md)를 보세요.

- 홈 대시보드와 국내 시세 보드에서 선택한 기업의 마지막 거래일 종가, 전일 대비, 등락률, 거래량 및 과거 주가 흐름을 확인할 수 있습니다.
- 왼쪽 메뉴에서 8개의 기능 화면으로 이동하고, 상세 분석 종목과 고급 탐지 기준을 선택합니다.
- `market_ui.py`는 실제 가격 DataFrame만 받아 화면용 HTML을 구성하며, 가격을 임의로 생성하지 않습니다.
- `assets/company_icons/*.png` 파일은 공식 로고가 아닌 식별용 자체 제작 아이콘입니다.
- `.streamlit/config.toml`은 밝은 UI를 설정하며, 비밀 API 키는 `secrets.toml`에 별도로 관리합니다.
- 이번 UI 개선만 따로 적용할 경우 **`app.py` 교체 + `market_ui.py`와 아이콘 폴더 및 테마 설정 추가**가 핵심입니다.


> **배포 상태 (2026-11-11):** 업로드된 `FinanceDataReader-master(1).zip` 및 `open-trading-api-main(1).zip`을 직접 조사하고, 실제로 존재하는 참고 데이터를 추출하고 정식 조회 API와 연결하도록 개정한 버전입니다. **가상 주가·가상 뉴스·임의 예측 결과 파일은 포함하지 않습니다.**

MARKET PULSE는 **실제 제공처에서 받아온** 국내 주식의 일별 OHLCV 데이터로 가격·거래량·기술적 지표·통계적 이상 변화를 분석하는 Python/Streamlit 웹앱입니다. 인증한 API에서 조회한 체결량, 뉴스, 공시 등을 별도로 표시할 수 있으며, 학습에 충분한 실제 가격 데이터가 있을 때 탐색적 방향 예측 모델을 계산할 수 있습니다.

**실시간 주문/매매, 보장된 가격 예측, 가상 수치를 실제 시세로 표시하는 기능은 없습니다.**

## 중요: 두 ZIP 파일에서 실제로 확인된 것

| 원본 ZIP | 들어 있는 실사용 자료 | 주가 이력 자체 포함 여부 |
|---|---|---|
| `FinanceDataReader-master(1).zip` | FinanceDataReader Python 소스 및 KRX 휴장일 `calendars/holidays-krx.csv`(620건), 다른 거래소 휴장일 참고 파일 | **없음** |
| `open-trading-api-main(1).zip` | 한국투자증권 Open API Python 예제, API 메타데이터 CSV(334건), API 요청 파라미터·응답 필드 정의 | **없음** |

**위 CSV는 주식의 가격 기록이 아닙니다.** `reference_data/holidays-krx.csv`에는 실제 휴장일이, `reference_data/kis_stock_api_reference.csv`에는 원본 API 목록에서 필터링한 실제 명세 8건이 들어 있습니다. 가격이나 주가의 미래값을 생성하여 채우지 않았습니다.

원본 파일의 정확한 내부 경로, SHA-256 원본 해시, 추출 행 수는 `reference_data/SOURCE_PROVENANCE.json`과 [압축파일 조사 결과](아카이브_실자료_검증결과.md)를 확인하세요. KRX 달력은 저장된 **참고 스냅샷**이며 거래소의 최신 공식 공고를 대체하지 않습니다.

## 실데이터 조회는 어떻게 되는가?

```text
[FinanceDataReader ZIP의 API 예제] ──┐
                                    ├─ 인터넷에서 실제 서버에 요청 ─┐
[KIS Open API ZIP의 인증/시세 예제] ───┘                             │
                                                                     ▼
                                                          응답 검증 / 표준 열 변환
                                                                     │
                                         ┌───────────────────────────┴─────────────────────────┐
                                         ▼                                                     ▼
                              data_cache/종목코드.csv                           data_cache/kis/종목코드_시장_adj.csv
                              + .meta.json                                    + .meta.json
                                         │                                                     │
                                         └───────────────────────────┬─────────────────────────┘
                                                                     ▼
                                                         실데이터 분석·차트·예측 실험
```

- FinanceDataReader는 **과거 일별 가격**을 우선 NAVER, 오류 시 KRX 경로로 요청합니다. 조회 응답은 `Date, Open, High, Low, Close, Volume` 등으로 표준화합니다.
- KIS를 사용하는 경우 한국투자증권에서 발급받은 **정상적인 사용자 API 키**가 필요합니다. `inquire-daily-itemchartprice`는 날짜별 OHLCV, `inquire-price`는 요청 시점 REST 현재가 스냅샷을 제공합니다. API별 제공 지연·시장 기준은 별도로 확인해야 합니다.
- `inquire-daily-trade-volume`에서는 **매수 체결량과 매도 체결량**을 별도로 수집합니다. 일별 OHLCV의 `Volume`과 혼동하지 않습니다. 지원 시장은 조회 예제대로 `J`(KRX)와 `NX`(NXT)입니다.
- KIS용 캐시는 FDR와 분리합니다. 수정주가 여부와 시장 기준이 다를 수 있으므로 두 값을 하나로 섞지 않습니다.
- 실제 API 접속을 이 환경에서 수행한 것은 아닙니다. **ZIP 안의 API 코드·응답 명세와 오프라인 모의 응답 테스트까지 검증**했습니다.

## 현재 구현 기능

| 기능 | 상태 | 데이터 조건 |
|---|---|---|
| 국내 종목 일별 OHLCV 수집 | 연동 코드 구현 | FDR 설치 + 인터넷 + 제공처 응답 |
| KIS 일별 OHLCV | 연동 코드 구현 | 사용자 KIS API 키 + API 접근 |
| KIS REST 현재가 | 연동 코드 구현 | 사용자 KIS API 키 + 접근 허용 |
| **KIS 매수/매도 일별 체결량** | **새로 추가** | 사용자 KIS API 키 + API 접근 |
| KRX 휴장일 참고 | **실제 파일 포함** | 원본 ZIP의 620개 날짜 |
| 종목 검색/기업 비교/캔들차트 | 구현 | 실제 OHLCV 조회 성공 |
| 수익률·이동평균·변동성·RSI·MACD·급변 탐지 | 구현 | 충분한 일별 관측값 |
| NAVER 뉴스 검색 | 연동 코드 구현 | 별도 NAVER Client ID/Secret |
| OpenDART 공시 | 연동 코드 구현 | 별도 OpenDART API 키 |
| 가격 중심 AI 방향 모델 + 백테스트 | 탐색 연구용 구현 | 충분한 과거 가격 이력 |
| 뉴스 결합 모델 | 조건부 실험 | 뉴스 수집·확인 시각이 과거 기준으로 검증 가능한 경우만 |
| 실시간 WebSocket 체결 스트림 | 미구현 | 별도 개발 필요 |
| 거래 주문/자동매매 | **제공하지 않음** | 의도적으로 연결하지 않음 |

## 1. 가장 쉬운 Windows 실행

1. 이 ZIP을 풀어 **안에 있는 파일과 폴더를 GitHub 저장소의 최상위**로 옮깁니다. `FinanceDataReader-master.zip`이나 `open-trading-api-main.zip`을 앱에 직접 넣지 않습니다.
2. PC에 Python 3.11 또는 3.12 권장 버전을 설치합니다.
3. `실행하기_윈도우.bat`을 실행하거나, VSCode 터미널에서 다음 명령을 입력합니다.

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

4. 웹브라우저에서 `http://localhost:8501`에 접속합니다.
5. **국내 주식 실데이터**를 선택합니다. 기본 제공처는 FinanceDataReader입니다. 실제 데이터 요청에는 인터넷이 필요합니다.
6. KIS 계정/API 키가 있다면 제공처를 `KIS Open API (조회 전용)`으로 바꿀 수 있습니다. 키가 없어도 FDR 경로를 사용할 수 있습니다.

`python`이 실행되지 않으면 Windows에서 `py -3`, macOS/Linux에서 `python3` 명령을 확인하세요.

## 2. 실제 주가 수집 명령어

```powershell
# 기본 6개 기업 일괄 수집: 인터넷 연결이 있을 때만 실제 CSV 생성
python collect_real_data.py

# 일부 종목과 기간을 명시적으로 지정
python collect_real_data.py --start 2024-01-01 --end 2026-11-11 --only 005930 000660
```

수집이 실패하면 **원본 ZIP 안에 주가가 들어 있다는 이유로 복구할 수는 없습니다.** 과거 성공한 캐시가 있으면 해당 캐시와 조회 실패 상태를 함께 표시합니다. 캐시도 없다면 오류를 출력하며 가상의 시세를 생성하지 않습니다.

### 저장 폴더

- `data_cache/005930.csv` 및 `005930.meta.json`: FDR 조회 기준 일별 종가·거래량 등
- `data_cache/kis/005930_J_adj.csv`: KIS 수정주가 조회 기준 OHLCV
- `data_cache/kis_trade_volume/005930_J.csv`: KIS 실제 매수·매도 체결량 기록
- `reference_data/holidays-krx.csv`: **원본 ZIP에서 추출한 실제 휴장일 참고 데이터**
- `reference_data/kis_stock_api_reference.csv`: **원본 ZIP에서 추출한 API 목록 일부**

**가격은 원본 ZIP에서 추출한 값이 아니라 각 API를 통해 새로 조회했을 때만 생성됩니다.** 데이터 출처·최종 거래일·수집 시각·실시간 여부를 별도 메타데이터에 기록합니다.

## 3. 한국투자증권(KIS) API 연결

이 프로그램은 KIS의 읽기 전용 시세 API를 호출합니다. **실전 주문·계좌 조회·출금 기능은 포함하지 않았습니다.**

1. 한국투자증권 Developers에서 해당 API를 사용할 자격과 앱 키를 확인합니다.
2. Windows 사용자 환경변수 또는 로컬 `.streamlit/secrets.toml`에 다음 항목을 설정합니다. **비밀키를 GitHub에 올리지 마세요.**

```toml
KIS_APP_KEY = "본인의 실제 발급 키"
KIS_APP_SECRET = "본인의 실제 발급 비밀키"
KIS_ENV = "prod"
```

3. 앱 왼쪽에서 KIS 제공처를 선택합니다.
4. 종목 상세 페이지의 `KIS 조회 시점 가격 확인`, `일별 매수·매도 체결량 조회` 버튼을 사용합니다.
5. 결과의 `retrieved_at`과 `last_trade_date`를 확인합니다.

`KIS_ENV=prod`는 실전 환경의 **시세 조회 API** 사용을 뜻할 뿐 주문 기능을 활성화하지 않습니다. `KIS_ENV=vps`는 모의 환경이며 제공 데이터 범위가 실전과 다를 수 있습니다.

원본 ZIP에서 사용한 기능 규격:

| KIS 원본 함수명 | API 경로 | TR-ID | 저장 열 |
|---|---|---|---|
| `inquire_daily_itemchartprice` | `/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice` | `FHKST03010100` | `Date,Open,High,Low,Close,Volume` |
| `inquire_price` | `/uapi/domestic-stock/v1/quotations/inquire-price` | `FHKST01010100` | 현재가, 전일 종가, 누적 거래량, 누적 거래대금 |
| `inquire_daily_trade_volume` | `/uapi/domestic-stock/v1/quotations/inquire-daily-trade-volume` | `FHKST03010800` | `Date,BuyExecutedVolume,SellExecutedVolume` |

API 요청·응답은 제공처 개정과 계정 권한의 영향을 받습니다. 다른 경로나 주문용 TR-ID는 호출하지 않도록 조회 API를 제한했습니다.

## 4. 직접 확보한 실제 CSV·KIS JSON을 가져오는 방법

실제 데이터 CSV 또는 KIS API `output2` JSON을 별도로 받은 경우, 표준화 스크립트를 사용할 수 있습니다.

```powershell
# 먼저 검증만 하고 저장하지 않기
python import_real_data.py --input "실제_주가.csv" --code 005930 --source "원본 데이터를 확보한 출처" --dry-run

# 실제 검증 통과 데이터를 저장하기
python import_real_data.py --input "실제_주가.csv" --code 005930 --source "원본 데이터를 확보한 출처"

# KIS output2 JSON 형식
python import_real_data.py --input "kis_output2.json" --code 005930 --format kis --source "KIS 직접 조회 기록"
```

이 명령어의 입력 파일은 **사용자가 실제로 확보한 가격 레코드**여야 합니다. 두 라이브러리 소스 ZIP을 `--input`으로 넣을 수는 없습니다. `--source` 설명을 적었다고 해서 실제 시세의 진위가 자동 인증되는 것은 아니며, 이러한 수동 수입 데이터는 `source_verified: false`로 저장됩니다.

현재 변환기는 `Date,Close,Volume`을 필수 열로 요구하며 `Open,High,Low`와 기타 거래정보는 있는 경우 추가 저장합니다. 다음과 같은 **열 이름만** 정의합니다. 실제 가격 숫자는 임의 생성하지 않습니다.

```text
Date,Open,High,Low,Close,Volume
```

한국어 열 이름, UTF-8·CP949, KIS의 `stck_bsop_date`, `stck_clpr`, `acml_vol` 등은 지원하는 규칙에 따라 변환합니다. 미래 날짜·잘못된 가격·결측값이 있으면 검증하거나 오류로 처리합니다.

## 5. 시세와 매수·매도 체결량을 왜 분리하나요?

- `Volume`: 특정 거래일에 실제 체결된 주식 수량을 나타내는 일별 OHLCV 거래량
- `BuyExecutedVolume`, `SellExecutedVolume`: KIS의 **종목별일별매수매도체결량 API 응답 필드**를 각각 매핑한 값
- `Turnover`: 해당 출처가 별도 제공한 거래대금이 있을 때만 거래대금으로 사용
- `KIS REST 현재가`: 조회 버튼을 누른 시점의 응답이며 실시간 WebSocket 스트림이 아님

시장구분, 누적 범위, 매수·매도 체결량 정의 등은 공급자 API 설명을 먼저 확인해야 합니다. 두 체결량 컬럼을 임의로 곱하거나 OHLCV 가격과 단순 합쳐 **공식 수급 지표**라고 해석하지 않습니다.

## 6. 데이터 품질과 AI 예측 검증

- 급변 판단의 비교 기준은 오늘을 제외한 **직전 N거래일**입니다.
- AI 예측의 타깃은 다음 거래일 종가의 상승 여부이며, 학습/검증/시험 구간을 시간 순서대로 분리합니다.
- 실데이터가 부족하면 예측을 수행하지 않습니다. 임의로 만들어 낸 실적이나 뉴스로 대체하지 않습니다.
- NAVER 기사 검색 API와 OpenDART API는 위 두 ZIP에 들어 있지 않습니다. 각 서비스의 정식 인증키를 **별도 준비**해야 합니다.
- 과거 기사를 오늘 처음 수집한 경우, 그 뉴스를 과거 시점에 미리 알고 있었던 것처럼 사용하지 않습니다. 뉴스 최초 수집 시점이 기록되어야 합니다.
- 뉴스 감성은 규칙 기반 분석이며, 뉴스 점수는 가격 상승 확률이나 인과관계 증거가 아닙니다.
- 가격 조정 방식, 권리락, 상장일, 거래정지, 거래소별 시장 가격 기준을 구분해야 합니다.
- 예측 확률은 미보정 탐색 지표입니다. 매매 권유 또는 수익 보장이 아닙니다.

## 7. 파일 구성

```text
MarketPulse_KR/
├── app.py                             # 7개 탭: 실데이터 중심, 가상 데이터 메뉴 없음
├── stock_core.py                      # 통계 엔진 및 단위 테스트 보조용 함수
├── market_data.py                     # NAVER → KRX 일별 데이터 수집
├── kis_market.py                      # KIS 일별 OHLCV, 현재가, 체결량 저장
├── kis_trade_volume.py                # KIS 실제 매수·매도 체결량 응답 정규화
├── market_calendar.py                 # 원본 KRX 휴장일 읽기
├── technical_indicators.py            # RSI, MACD, 이동평균 등
├── feature_engineering.py             # 예측 피처
├── prediction_model.py                # 시계열 모델 실험
├── backtesting.py                     # 백테스트
├── news_collector.py                  # 별도 NAVER 뉴스 API 연동
├── news_analyzer.py                   # 뉴스 감성 규칙
├── disclosure_collector.py            # 별도 OpenDART API 연동
├── import_real_data.py                # 실제 CSV·KIS JSON 변환
├── collect_real_data.py              # 실제 시세 일괄 수집
├── config.py                          # 설정
├── reference_data/
│   ├── holidays-krx.csv               # 원본 ZIP에서 실제로 추출
│   ├── kis_stock_api_reference.csv    # 원본 ZIP 명세 중 8건 추출
│   └── SOURCE_PROVENANCE.json         # 원본 파일 해시·경로·건수
├── data_cache/                        # API 성공 시 생성되는 실제 시세 캐시
├── news_cache/                        # 뉴스 API 메타데이터 저장 위치
├── tests/                             # 가상 테스트 응답은 테스트 코드에만 존재
├── .github/workflows/ci.yml          # GitHub 자동 테스트
├── MARKET_PULSE_Colab.ipynb          # 실제 FDR 조회만 실행하는 노트북
├── requirements.txt
├── 실행하기_윈도우.bat
├── 실제주가_수집하기_윈도우.bat
├── run_mac_linux.sh
├── .env.example
├── .gitignore
├── README.md
├── 아카이브_실자료_검증결과.md
├── API_연동_사용법.md
├── 삭제_대상_목록.md
└── GITHUB_업로드_안내.md
```

## 8. 가상·임시 데이터 삭제 목록

**이 버전에는 아래 가상 자료를 포함하지 않습니다.** 기존 GitHub 저장소에서 아래 경로가 보이면, 소스에 연결된 진짜 실거래 데이터가 아닌지 확인한 뒤 삭제할 수 있습니다.

- `sample_data/가상기업 A.csv`, `B.csv`, `C.csv`, `D.csv`
- `sample_data/가상뉴스_시연.csv`
- `sample_outputs/가상데이터_market_pulse_anomalies.csv`
- `sample_outputs/가상데이터_market_pulse_comparison.csv`
- `sample_outputs/가상데이터_market_pulse_model_scores.csv`
- `sample_outputs/가상데이터_market_pulse_predictions.csv`
- 루트에 있던 `가상기업 A.csv` ~ `가상기업 D.csv` 중 실제로 시연용으로 생성한 파일

**중요:** `data_cache/` 아래의 기존 파일이 실제로 수집한 자료라면 삭제하지 마세요. `market_pulse_*.csv`와 같이 출처를 알 수 없는 결과 파일은 삭제 전에 `데이터상태`, `원출처`, `last_trade_date` 등의 열과 생성 목적을 확인해야 합니다. 자세한 명단은 [삭제 대상 목록](삭제_대상_목록.md)에 정리했습니다.

## 9. Google Colab

`MARKET_PULSE_Colab.ipynb`는 새로 구성했습니다. 가상기업·가상 뉴스 예시를 생성하지 않고 **실제 FinanceDataReader 온라인 수집에 성공해야** 다음 셀을 진행합니다. 인터넷이 막히면 오류를 반환합니다. 이전 Colab의 가상 분석 결과를 실데이터로 둔갑시키지 않습니다.

## 10. 테스트와 미검증 범위

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m compileall -q .
```

현재 패키지 코드의 자동 테스트는 **48개 통과**(오프라인 모의 응답 포함)로 확인했습니다. `reference_data/holidays-krx.csv`는 원본 SHA-256과 일치하는지 검사합니다. 한국투자증권 API 요청 경로 및 시장 구분, 응답 필드, 캐시 교체·실패 처리도 테스트합니다.

**아직 실제로 검증하지 않은 부분:** 사용자 PC의 Windows 브라우저 실행, FDR 온라인 가격 조회 성공, KIS 본인 키를 이용한 정상 응답, 뉴스·공시 API 실접속, 실제 시장을 대상으로 한 예측 성능. 외부 API 제공처가 데이터를 반환해야만 가격 시계열 파일이 생성됩니다.

## 11. GitHub 정리·문제 해결

- 기존 README, 코드, 노트북은 이 패키지 버전으로 교체합니다.
- 업로드 전 **기존 가상 데이터 파일**은 `삭제_대상_목록.md`를 참고해 검토합니다.
- **민감한 API 키·토큰·계좌 비밀번호·환경변수 파일은 커밋 금지**입니다.
- API 소스 ZIP 전체나 `.git/` 폴더는 GitHub 저장소에 중복 업로드하지 마세요. 필요한 기능만 새 모듈로 연결했습니다.
- 브라우저가 열리지 않으면 `http://localhost:8501` 접속 및 터미널 오류를 확인합니다.
- `FinanceDataReader`가 설치되지 않았거나 외부 연결이 실패하면 실제 데이터 수집이 안 됩니다. 이전 캐시가 없다면 사용자 입력 또는 CSV 없이 분석할 수 없습니다.

추가 안내: [API 사용법](API_연동_사용법.md) · [원본 압축파일 조사](아카이브_실자료_검증결과.md) · [삭제 대상](삭제_대상_목록.md) · [GitHub 업로드](GITHUB_업로드_안내.md)

---

**출처:** 사용자가 제공한 FinanceDataReader 및 한국투자증권 Open Trading API 소스 ZIP. 추출한 캘린더와 API 목록의 출처·원본 파일 해시는 `reference_data/SOURCE_PROVENANCE.json`에 기록했습니다. API 키/인터넷이 없어도 이 참고 자료는 확인할 수 있으나, **실제 주가 이력 자체는 다운로드되지 않은 상태입니다.**
