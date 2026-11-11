# LangChain + Grok 뉴스 분석·예측 시나리오 설정

## 실제로 추가된 기능

1. `stock_catalog.py`: 30개 국내 주식 이름/코드/분류 목록. **가격 데이터는 포함하지 않음**.
2. `news_store.py`: 네이버 뉴스 API에서 실제 받은 기사 제목·요약·링크·공개시각·최초수집시각을 종목별로 저장. 시간 정보는 재조회 시 초기 기록을 보존.
3. `langchain_analysis.py`: **LangChain + ChatXAI**로 최대 12개 뉴스 제목·요약을 구조화하여 분석. 추가로 기존 시계열 예측 모델의 출력을 해석하는 정성 시나리오 기능.
4. `app.py`: 뉴스 조회, 기사 표, LangChain 기사 분석 버튼, AI 예측 화면의 시나리오 버튼, 30개 종목 선택 UI 통합.
5. `collect_real_data.py`: 기존 6개 기본 일괄 수집 외에 `--all-30` 옵션 추가. 호출 제한을 고려해 1초 간격으로 요청.

## 필요한 키와 라이브러리

기본 주가 데이터 조회(FinanceDataReader)에는 별도 로그인 키가 필요하지 않습니다. 네이버 뉴스 자동 조회에는 `NAVER_CLIENT_ID` 및 `NAVER_CLIENT_SECRET`이 필요합니다. LangChain 언어모델 분석에는 **별도의 xAI Grok API 이용권과 `XAI_API_KEY`**가 필요합니다. xAI 콘솔의 계정 이용 자격, 가격 및 사용량 한도를 확인하세요. 키가 없다면 뉴스 규칙 분류와 기존 가격 기반 확률 예측은 계속 사용할 수 있습니다.

프로젝트 폴더에서:

```powershell
python -m pip install -r requirements.txt
python -m pytest -q
python -m streamlit run app.py
```

Streamlit Cloud: 앱 관리 화면의 **Secrets**에 다음 키를 등록합니다. 로컬: 프로젝트의 `.streamlit/secrets.toml` 파일에 아래 구조로 직접 저장합니다. 인증값은 GitHub에 **절대로 커밋하지 마세요**.

```toml
NAVER_CLIENT_ID = "네이버_발급_ID"
NAVER_CLIENT_SECRET = "네이버_발급_SECRET"
XAI_API_KEY = "발급받은_API_KEY"
XAI_MODEL = "grok-4"
# 선택: DART_API_KEY, KIS_APP_KEY, KIS_APP_SECRET, KIS_ENV
```

`XAI_MODEL`은 선택값입니다. 모델이 계정에서 지원되지 않으면 제공되는 다른 호환 모델을 사용하세요. 이미 `secrets.toml`에 KIS나 DART 키가 있다면 지우지 말고 내용을 **병합**하세요.

참고: Streamlit Cloud에서는 시스템에 저장한 `data_cache`와 `news_cache`가 영구 보관된다고 보장하지 않습니다. 세션 외 장기 저장이 필요하면 별도의 영속적 저장소를 붙여야 합니다.

## 사용 순서

1. Streamlit 앱 실행 → 왼쪽 **분석 종목 (30개 중 최대 6개)** 선택. 최초 3개만 기본 조회합니다.
2. **뉴스·공시** 페이지 → **최신 실제 뉴스 가져오기** 클릭. 실제 네이버 뉴스 검색 API 응답을 확인합니다.
3. 같은 페이지 → **Grok으로 기사 근거 분석** 클릭. 기사 제목·검색 요약을 기반으로 긍정/부정/불확실 요인과 근거 기사 링크를 표시합니다.
4. **AI 예측** 페이지 → **1. 정량 모델 학습·검증 및 예측** 클릭. 기존 sklearn 로지스틱 회귀가 실제 과거 가격의 t+1 상승 여부를 분석하고 시간순 시험 구간 성능과 **미보정 확률**을 제시합니다.
5. 같은 페이지 → **Grok 시나리오 생성** 클릭. AI는 이미 계산된 확률을 **바꾸지 않고** 실제 뉴스·통계 결과를 바탕으로 상승/하락 시나리오를 서술합니다.
6. **백테스트** 페이지에서 기간별 검증을 확인합니다.

## 설계상 중요한 한계

- 네이버 검색 API는 기사 **원문 전체를 제공하지 않습니다**. 여기서 LangChain이 읽는 것은 공식 API가 반환한 **제목·설명(검색 요약)**입니다. AI가 원문을 읽었다고 표시하지 않습니다. 원문을 보고 싶으면 링크로 이동해야 합니다.
- LangChain은 숫자 주가·상승 확률을 창작하는 서비스가 아닙니다. 예측값은 **가격/거래량/기술적 지표를 사용한 통계 모델**에서 계산됩니다. LangChain은 기사와 통계 입력값의 해석을 맡습니다. 분석 결과는 투자 지시나 가격 예언이 아닙니다.
- 새로 검색한 과거 기사의 `first_seen_at`은 **이번 수집 시각**입니다. 과거 뉴스로 소급해 백테스트 정확도를 만들어 내지 않습니다.
- API 키가 없거나 응답이 실패하면 오류를 표시하며 가상 기사나 가짜 확률을 자동 생성하지 않습니다.
- LangChain API 사용은 선택 동작이고, 각 버튼을 누른 경우에만 외부 모델 호출이 발생합니다. 모델 제공자의 요금과 데이터 처리 정책을 확인한 뒤 사용하세요.

## 자주 발생하는 오류

| 화면 메시지 | 확인할 것 |
|---|---|
| `NAVER_CLIENT_ID`/`NAVER_CLIENT_SECRET` 미설정 | 네이버 개발자센터 발급 키를 Streamlit Secrets에 등록 |
| `XAI_API_KEY`가 없어 버튼 비활성화 | xAI Grok API 이용 자격과 별도 키 설정 확인 |
| `langchain-xai` 미설치 | `python -m pip install -r requirements.txt` |
| 모델을 찾을 수 없다는 오류 | 계정에서 사용 가능한 `XAI_MODEL`을 지정했는지 확인 |
| API 429 | 호출 제한/사용량 확인, 연속 호출 자제 |
| 예측에 뉴스가 포함되지 않음 | 실제 당시 수집 시각·평가용 과거 뉴스 기록의 부족 때문일 수 있음 |
| 가격/뉴스 자료 없음 | 외부 제공처의 응답, 네트워크 및 데이터 기준일 확인 |

## 공식 참고 자료

- 네이버 뉴스 검색 API: https://developers.naver.com/docs/serviceapi/search/news/news.md
- LangChain `ChatXAI`: https://docs.langchain.com/oss/python/integrations/chat/xai
- LangChain 구조화 출력: https://docs.langchain.com/oss/python/integrations/chat/xai
- FinanceDataReader: https://github.com/FinanceData/FinanceDataReader


## Grok(xAI) 연결 확인

- API 키 발급: https://console.x.ai/ (이용 자격과 제공 모델은 계정 설정에서 확인)
- 제공자 공식 문서: https://docs.x.ai/overview
- LangChain Python 통합: https://docs.langchain.com/oss/python/integrations/chat/xai
- SDK: `from langchain_xai import ChatXAI` / `XAI_API_KEY`.
- `XAI_MODEL` 기본값은 `grok-4`입니다. 해당 모델을 사용할 수 없는 경우 실제 계정에서 지원되는 모델 이름을 설정하세요.
- Grok API로 전송되는 내용은 **선택된 뉴스 검색 제목/요약과 예측 메타데이터**입니다. 비밀키, 투자계좌 정보, 사용자 개인정보를 보내지 마세요.
- 새로운 뉴스 요약 또는 정성 시나리오는 버튼 클릭시에만 API로 요청되며 요금이 발생할 수 있습니다.
- GitHub 저장소에는 예시 설정만, 실제 키는 `.streamlit/secrets.toml` 혹은 Cloud Secrets에 저장해야 합니다.
