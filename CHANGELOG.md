# MARKET PULSE 변경 이력

## 2026-11-12 · 30종목 + Grok(xAI) LangChain 통합

- 6개 종목 → 30개 국내 주식 카탈로그(기본 3개, 한 번에 최대 6개 조회)
- 네이버 검색 API 실제 뉴스 제목·요약·출처 링크 저장 및 중복 처리
- LangChain의 **ChatXAI** (`langchain-xai`)로 Grok 뉴스 근거 분석 및 예측 결과 정성 설명
- `XAI_API_KEY`, `XAI_MODEL` 설정 지원. 과거 OpenAI 공급자 자동 연결 코드 제거
- 정량 ML 확률과 Grok 정성 분석 역할 분리, 미래 데이터 누출 방지
- 테스트 64개 통과(서버 API 실연결 제외)
- 기존 사이드바, 종목 아이콘, 시세 보드 UI, 통계 엔진, KIS 및 캐시 유지
