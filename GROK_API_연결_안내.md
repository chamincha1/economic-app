# MARKET PULSE — xAI Grok API 연결 안내

## 1. 연결 구조

- 종목 데이터: FinanceDataReader(기존 모듈) / 선택적으로 KIS API.
- 뉴스: NAVER 검색 API가 반환한 **제목·요약·링크**. 기사 원문 전체는 수집하지 않습니다.
- 뉴스 해설: `langchain-xai` 패키지의 `ChatXAI`를 사용한 **Grok**(xAI API).
- 숫자 상승 확률: 기존 scikit-learn 시계열 분류기. **Grok이 확률이나 목표주가를 새로 만들지 않습니다.**

## 2. 발급

xAI 공식 콘솔 https://console.x.ai/ 에서 계정 이용 자격과 키 발급 및 모델 사용 가능 여부를 확인합니다. 가격과 사용량 한도를 확인하세요. 발급받은 키는 이 대화나 GitHub에 절대 공개하지 않습니다. 이용 자격 제한이 있다면 이를 준수하세요.

## 3. Streamlit Cloud에서 키 등록하기

Cloud 콘솔의 **App settings → Secrets**에 아래 내용을 입력합니다. 이미 사용 중인 KIS/뉴스/DART 설정을 지우지 않고 병합하세요.

```toml
NAVER_CLIENT_ID = "네이버_발급_클라이언트_ID"
NAVER_CLIENT_SECRET = "네이버_발급_시크릿"
XAI_API_KEY = "xAI에서_발급받은_API_키"
XAI_MODEL = "grok-4"
# 선택적으로 KIS_APP_KEY, KIS_APP_SECRET, KIS_ENV, DART_API_KEY 사용 가능
```

`grok-4`는 기본 모델 문자열이며, 실제 사용 가능 모델은 **xAI 콘솔**에서 확인하고 `XAI_MODEL`을 변경합니다. 키가 없으면 Grok 분석 버튼이 비활성화되고 일반 가격 분석·통계 모델·뉴스 표시는 계속 사용할 수 있습니다.

로컬 Windows 환경은 프로젝트 루트에 `.streamlit/secrets.toml` 파일을 만들어 같은 형식으로 입력할 수 있습니다. 이 파일은 `.gitignore`에 포함되며 GitHub에 올리면 안 됩니다. `.env.example`은 사용법 예시이며, 별도의 자동 `.env` 로딩 기능은 없습니다.

## 4. 설치 및 실행

```powershell
python -m pip install -r requirements.txt
python -m pytest -q
python -m streamlit run app.py
```

## 5. 실제 화면 사용 순서

1. 왼쪽 **분석 종목 (30개 중 최대 6개)**에서 종목 선택.
2. **뉴스·공시** 화면에서 **최신 실제 뉴스 가져오기** 클릭 (네이버 API 인증 필요).
3. 화면의 실제 기사 목록과 링크 확인 → **Grok으로 기사 근거 분석** 클릭.
4. **AI 예측** 화면에서 먼저 기존 **정량 모델 학습·검증 및 예측** 실행.
5. **Grok 시나리오 생성** 버튼으로 뉴스와 정량 결과를 참고한 정성 설명 확인.
6. **백테스트**에서 수치 예측의 평가 결과 확인.

Grok의 분석은 사용자가 버튼을 눌렀을 때만 요청됩니다. 기사 제목과 검색 요약 등 입력 내용이 xAI 서버로 전송될 수 있으며 API 이용 요금이 발생할 수 있습니다.

## 6. 오류와 검증

| 증상 | 확인 사항 |
|---|---|
| Grok 버튼 비활성화 | `XAI_API_KEY` 미설정 또는 Secrets 등록 실수 |
| `langchain-xai` 없음 | `python -m pip install -r requirements.txt` 실행 |
| 401/403 | xAI API 키 유효성, 계정 권한 및 모델 접근 가능 여부 |
| 404/모델 없음 | `XAI_MODEL`이 계정에서 허용된 모델인지 확인 |
| 429 | API 호출 제한·크레딧·사용량 확인 |
| 기사 없음 | `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET` 및 뉴스 검색 결과 확인 |
| Grok 분석 없음 | 기사 데이터가 없거나 요청이 실패하면 가상 내용을 대체 출력하지 않습니다 |

### 확인 범위

- 오프라인: 30개 코드·뉴스 캐시·Grok SDK 초기화 모의 테스트·통계 예측·UI/데이터 모듈 테스트.
- **별도 사용자 검증 필요**: 실제 xAI API 응답, 뉴스 API 응답, KIS 시세, Windows Chrome UI 및 Streamlit Cloud 운영.

## 공식 참고

- [xAI 공식 콘솔](https://console.x.ai/)
- [xAI 공식 문서](https://docs.x.ai/overview)
- [LangChain ChatXAI](https://docs.langchain.com/oss/python/integrations/chat/xai)
