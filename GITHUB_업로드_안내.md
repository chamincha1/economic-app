# GitHub 업로드 순서

1. 현재 GitHub 저장소에서 **새 브랜치**를 만듭니다. 다른 팀원이 수정하는 파일을 덮어쓰지 않도록 합니다.
2. `MarketPulse_실제자료_반영_GitHub.zip`을 다운로드하고 **압축을 해제**합니다.
3. ZIP 안의 파일들을 저장소 최상위 경로에 올립니다. 별도의 중첩 프로젝트 폴더를 만들지 않습니다.
4. 기존 `README.md`, `app.py`, `stock_core.py`, `market_data.py`, `requirements.txt`, Colab 노트북은 새 것으로 교체합니다.
5. 새 파일 `kis_trade_volume.py`, `market_calendar.py`, `reference_data/` 및 테스트·안내 문서를 추가합니다.
6. `삭제_대상_목록.md`를 읽고 기존 `sample_data/`, `sample_outputs/`, 가상기업 CSV 및 가상 뉴스 CSV를 삭제합니다.
7. **기존 실제 시세 캐시는 출처 확인 전 삭제하지 않습니다.** 인증키·`.env`·`.streamlit/secrets.toml`은 절대로 업로드하지 않습니다.
8. GitHub Actions 테스트가 통과하는지 확인한 후 `main` 브랜치에 병합합니다.

ZIP 자체를 저장소에 커밋할 필요는 없습니다. 두 외부 프로젝트의 원본 ZIP도 통째로 저장소에 넣지 않습니다.

## 새로 추가한 자료

- `reference_data/holidays-krx.csv`: 원본 FDR 파일에서 실제 휴장일 참조 CSV를 추출한 것
- `reference_data/kis_stock_api_reference.csv`: KIS 원본 카탈로그에서 국내 주식 분석 관련 API 8건만 발췌
- `reference_data/SOURCE_PROVENANCE.json`: 위 두 파일의 원본 경로와 SHA-256, 건수
- `market_calendar.py`: 휴장일 참고 모듈
- `kis_trade_volume.py`: KIS 일별 매수/매도 체결량 변환·조회
- `tests/test_real_reference_and_trades.py`: 원본 해시·API 필드·조회 보호 테스트

## 추가 확인

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m streamlit run app.py
```

**조회 성립 조건:** FDR에서 실제 시세를 내려받거나 본인 KIS 키로 API 호출에 성공해야 실가격이 나타납니다. 압축파일에서 가격 숫자를 꺼내는 방식이 아닙니다.
