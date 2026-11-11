# MARKET PULSE UI 통합 검증 (2026-11-11)

- **전체 53개 pytest 자동 테스트 통과**: 기존 분석/실데이터 모듈 48개 + 새 UI 컴포넌트 5개.
- **Python 코드 컴파일 검사 통과**.
- UI 표준 자료형 기반 로직 테스트: 수집 데이터만 표시, 정렬, 누락 입력, HTML 이스케이프, 미니차트 및 로컬 식별 아이콘 경로.
- **제한:** Streamlit 브라우저 UI 실제 구동과 외부 API 인증은 이 환경에서 직접 검증하지 못했습니다. 따라서 화면 픽셀 단위 검증 완료로 표시하지 않습니다.

---

# MARKET PULSE 실데이터 전환판 검증 보고서

**검증 대상:** 코드·모의 HTTP 응답·원본 ZIP 추출 참고 CSV·날짜 처리·예측 엔진

- `python -m pytest -q`: **48개 통과**
- `python -m py_compile`: 주요 Python 코드 문법 검사 통과
- `reference_data/holidays-krx.csv`: FDR 원본 해시 검증 및 620개 고유 날짜 확인
- `reference_data/kis_stock_api_reference.csv`: 8개 API 기록 확인
- KIS 매수/매도 체결량 컬럼: `shnu_cnqn_smtn`, `seln_cnqn_smtn` 변환 확인
- KIS 조회 엔드포인트 제한: 주문 API 경로 차단 테스트 통과
- 실패 시 이전 캐시를 `cached`로 표시하도록 확인
- 사용자 화면용 `sample_data`, `sample_outputs`는 제거

**미검증:** 한국투자증권 사용자의 API 키로 실제 호출/실거래 체결량 수신, FinanceDataReader 원격 데이터 다운로드, Windows Streamlit 브라우저 동작, 새로운 모델의 실거래 데이터 예측 성능. 제공 ZIP 자체에는 실제 주식 가격 시계열이 없습니다.
