# 변경 기록

## 2026-11-11 — 사용자가 제공한 원본 소스 ZIP 기반 실자료 전환

- `FinanceDataReader-master(1).zip`에서 KRX 휴장일 CSV **620건**을 원본 바이트로 추출하여 `reference_data/`에 저장
- `open-trading-api-main(1).zip`의 KIS API 카탈로그 **334건 중 국내 주식 관련 8건** 선별
- 실제 API 명세에 맞춰 KIS `inquire-daily-trade-volume` 요청 및 매수/매도 체결량 변환/캐시 추가
- `app.py` 가상 데이터 모드 및 가상 뉴스 파일 사용 로직 제거
- `sample_data/`·`sample_outputs/` 제거 (실제 시장 자료 없음)
- Colab을 실 FDR 가격 수집 기반으로 재작성; 다운로드 실패 시 예시로 대체하지 않음
- 원본 데이터 계보와 해시를 `SOURCE_PROVENANCE.json`에 기록
- GitHub 업로드 방법 및 이전 시연 데이터 삭제 명단 추가
- 48개 오프라인 자동 테스트 통과 (API 온라인 연결·Windows GUI 실제 실행은 미검증)
