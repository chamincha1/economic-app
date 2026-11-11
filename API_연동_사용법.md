# 실제 데이터 연결 안내

## 무엇을 준비하나요?

**최소 구성:** Python + 인터넷 + `finance-datareader` 라이브러리. 별도 KIS 키가 없어도 NAVER/KRX 제공처가 응답하면 일별 가격을 가져올 수 있습니다.

**한국투자증권 API 사용:** 본인에게 발급된 KIS 앱키와 앱시크릿이 필요합니다. 키가 없으면 KIS 조회 버튼을 사용할 수 없습니다. API 약관 및 이용 권한을 확인하세요.

## 가장 쉬운 실제 데이터 수집

프로젝트 폴더에서:

```powershell
python -m pip install -r requirements.txt
python collect_real_data.py --start 2024-01-01 --end 2026-11-11 --only 005930 000660
python -m streamlit run app.py
```

실행 시 API 호출 결과는 `data_cache/005930.csv` 등으로 저장됩니다. 파일이 만들어지지 않으면 프로그램의 오류 메시지를 확인합니다. **원본 두 ZIP에 없는 시세를 자동으로 채우지 않습니다.**

## KIS API 설정

`KIS_APP_KEY`, `KIS_APP_SECRET`, `KIS_ENV`를 시스템 환경변수 또는 `.streamlit/secrets.toml`에 저장합니다.

```toml
KIS_APP_KEY = "실제 발급된 앱키"
KIS_APP_SECRET = "실제 발급된 앱시크릿"
KIS_ENV = "prod"
```

**실제 키 값은 Github, 이 채팅, 공유 폴더에 제출하지 마세요.** 키가 없는 경우 FDR 모드를 계속 사용하세요.

## 수집 데이터의 차이

| 기능 | API 제공처 | 저장 방식 |
|---|---|---|
| 과거 일별 시세 | FinanceDataReader를 통한 NAVER/KRX | `data_cache/<종목코드>.csv` |
| KIS 일별 OHLCV | `inquire-daily-itemchartprice` | `data_cache/kis/<종목코드>_J_adj.csv` |
| KIS 일별 매수/매도 체결량 | `inquire-daily-trade-volume` | `data_cache/kis_trade_volume/<종목코드>_J.csv` |
| KIS 조회 시점 현재가 | `inquire-price` | 버튼 호출 시 표시, 기본 영구 저장 안 함 |
| 뉴스/공시 | 별도 NAVER/OpenDART 인증키 | API 수집 성공한 항목만 표시 |

KIS 시세와 FDR 시세는 가격 조정 방식과 시장 기준이 다를 수 있어 캐시를 공유하지 않습니다.

## 직접 받은 CSV/JSON 변환

```powershell
python import_real_data.py --input "공급자가_제공한_주가.csv" --code 005930 --source "공급자명" --dry-run
python import_real_data.py --input "공급자가_제공한_주가.csv" --code 005930 --source "공급자명"
```

열은 `Date`, `Close`, `Volume`이 필수이고 `Open`, `High`, `Low`는 선택입니다. 실제 가격 수치는 공급자 데이터를 그대로 사용해야 합니다. 예시 숫자를 입력해 실제 시세로 등록하지 마세요.

## 오류가 나타날 때

- `KIS_APP_KEY/KIS_APP_SECRET이 없습니다`: FDR 모드 사용 또는 공식 키 발급
- `온라인 및 이전 캐시 조회 실패`: 네트워크, 제공처 접근, 조회 날짜 확인
- `필수 열`: API 데이터가 시세용 CSV인지 확인 (`data.csv` API 카탈로그는 시세용 아님)
- `분석 자료 부족`: 날짜 범위를 넓혀 적어도 비교 기준보다 많은 실제 거래일 확보
- `이전 저장 데이터`: API 조회 실패 때문에 캐시로 전환된 것. 최신 시세로 표시하지 않음
- `403/429 등 API 오류`: 인증/이용 권한/호출 한도 확인. 키를 로그에 출력하지 마세요.

## 주가 데이터가 들어오기 전에는?

앱은 예측값과 임의 가격을 표시하지 않습니다. `reference_data`에는 실제 원본에서 추출한 휴장일·API 메타데이터만 있기 때문입니다. 데이터가 없는 경우 오류가 정상적인 동작입니다.
