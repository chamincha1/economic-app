# MARKET PULSE — GitHub 업로드 안내

이 폴더가 GitHub 저장소의 **최상위 폴더(root)** 내용입니다. `MarketPulse_GitHub_업로드용` 폴더 자체를 기존 저장소 안에 중첩해 넣지 마세요.

## 기존 GitHub 저장소(사진)에 업로드하는 방법

1. 아래의 ZIP 파일을 PC에 다운로드하여 압축을 해제합니다.
2. GitHub 저장소의 **Code** 페이지를 열고 `Add file` → `Upload files`를 선택합니다.
3. 압축을 푼 폴더 안의 파일과 하위 폴더를 업로드 영역으로 끌어 놓습니다. 폴더 업로드가 작동하지 않으면 **GitHub Desktop**으로 로컬 폴더를 저장소에 복사한 뒤 Commit/Push하세요.
4. 기존 `README.md`, `requirements.txt`, `stock_core.py`처럼 이름이 같은 파일은 **교체**합니다. 기존 파일을 백업할 필요가 있다면 먼저 별도 브랜치를 만드세요.
5. `Commit changes`로 변경사항을 저장합니다.
6. 기존 저장소에 남아 있는 과거 버전(특히 한글명 `.py`와 기존 실행 스크립트)은 필요 없는 것이 확실하다면 제거하세요. **다른 팀원의 작업 파일은 확인 없이 삭제하지 마세요.**
7. GitHub Actions의 `.github/workflows/ci.yml`이 저장소에 올라갔는지 확인합니다. 자동 테스트가 실행될 수 있습니다.

## 사진 속 기존 파일과 새 파일 관계

| 사진 속 파일 | 새 버전에서 사용할 파일 | 권장 처리 |
|---|---|---|
| `앱.py` (브라우저 자동번역일 수도 있음) | `app.py` | 실제 GitHub 파일명을 확인해 새 코드와 중복 실행 파일 방지 |
| `시장 데이터.py` | `market_data.py` | 이전 파일명/호출 관계 확인 후 새 모듈 사용 |
| `실제 데이터를 수집합니다.py` | `collect_real_data.py` | 이전 스크립트 확인 후 교체 |
| `stock_core.py` | `stock_core.py` | 덮어쓰기 |
| `README.md` | `README.md` | 덮어쓰기 |
| `MARKET_PULSE_Colab.ipynb` | 동일 파일명 | 덮어쓰기 |
| `requirements.txt` | 동일 파일명 | 덮어쓰기 |
| `테스트/` | `tests/` | 별도 폴더 추가; 이전 테스트 보존 여부 결정 |

**주의:** 화면에는 브라우저 자동 번역된 파일명이 보일 수 있습니다. 기존 파일의 실제 이름을 먼저 확인하세요. 저장소 안에 `app.py`와 `앱.py`가 동시에 있으면 어느 것을 실행해야 할지 혼란스러울 수 있습니다.

## 필요한 최소 명령

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

자동 테스트:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

`data_cache/`, `news_cache/`, `models/`, `reports/` 폴더의 `.gitkeep`만 업로드하고, 실데이터나 비밀키는 업로드하지 마세요.

**API 키:** `.env.example`은 예시 파일이며 실제 키가 포함된 `.env`는 절대 GitHub에 올리지 않습니다.

## 점검 범위

- 코드 자체의 오프라인 테스트는 33개 통과했습니다.
- 외부 시세/뉴스/공시 제공처의 실제 통신 및 Windows 화면 실행은 이 업로드 안내만으로 검증되지 않습니다.
- 이 프로젝트는 교육·연구용이며 예측 결과는 투자 조언이 아닙니다.
