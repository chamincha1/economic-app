# MARKET PULSE — Grok 30종목 통합판 테스트 기록

## 이 환경에서 실행한 자동 검증

`python -m pytest -q` → **64개 테스트 통과**.

포함 항목: 기존 통계·수익률·급변 탐지, FinanceDataReader/KIS 모의 응답, 실제 뉴스 메타데이터 정제와 캐시, 국내 30개 종목 코드 목록, HTML 시세 카드·아이콘, LangChain 뉴스 근거 번호 검증, 수치 예측 확률 보존, `XAI_API_KEY` 누락 시 중지, 모의 ChatXAI 모델 초기화 확인.

Python 소스에 대해 `python -m py_compile` 구문 검사도 수행했습니다.

## 검증하지 않은 범위

이 실행 환경에는 실제 `XAI_API_KEY`와 `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`, KIS 키가 없으므로 **외부 서비스 인증 성공 및 실제 Grok 응답은 검증하지 않았습니다.** 실제 Windows/Chrome UI 렌더링과 Streamlit Community Cloud 배포도 별도의 최종 확인이 필요합니다.

가상 가격/뉴스 CSV는 패키지에 포함하지 않습니다. 테스트 코드의 모의 레코드는 서비스 화면의 실제 자료가 아닙니다.
