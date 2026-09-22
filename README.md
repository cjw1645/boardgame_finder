# 보드게임 파인더

**인원·취향·위치를 대화로 입력하면, 수집된 보유 목록을 근거로 게임과 보드게임 카페를 찾는 로컬 웹 서비스입니다.**

> 현재 제공 범위는 로컬 실행 가능한 서비스입니다. AWS 공개 배포, 실시간 대여 가능 여부, 계정별 대화 저장은 제공하지 않습니다. 실제 수집 데이터와 API 키는 저장소에 포함하지 않습니다.

## 제공 기능

- **AI 대화:** Ollama `qwen3:4b-instruct`가 조건을 추출하고 조회 결과를 근거로 한국어 답변을 생성합니다. 외부 유료 LLM 호출은 없습니다.
- **복수 추천:** “4명, 간단한 파티게임과 진득한 전략게임”을 각각 검색합니다. 전략 장르 분류와 복잡도를 확인해 단순 키워드 오분류를 줄였습니다.
- **카카오 위치 검색:** “잠실역에서 찾아줘”로 장소·주소를 검색하고 후보가 여러 곳이면 번호로 선택합니다. 이후 질문에도 선택한 위치를 유지합니다.
- **매장 식별:** 레드버튼/히어로 브랜드, 지점명, 직선거리, 수집일, 실제 조회 근거를 표시합니다.
- **조건 검색:** 모델 없이 게임 이름·인원·시간·반경·출처로 조회합니다. 기본적으로 최근 7일 수집 기록만 사용합니다.
- **데이터 검증:** 새 소스의 CSV를 검증하고 완전한 스냅샷을 원자적으로 전환합니다. 수집·검증 실패 시 이전 데이터가 유지됩니다.

## 빠른 시작 — Python 3.12

```powershell
git clone https://github.com/cjw1645/boardgame_finder.git
cd boardgame_finder
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-test.txt
.venv/Scripts/python -B scripts/create_demo.py
./scripts/start-local.ps1
```

접속: http://127.0.0.1:8501

`create_demo.py`는 **가상의 게임·매장**을 별도 `demo` 소스로 생성합니다. 실제 매장 재고가 아닙니다. 기존 메타데이터가 있으면 덮어쓰지 않습니다. 실제 서비스를 준비할 때 `data/active_demo.json`을 제거해 데모 소스를 비활성화하세요. 빈 데이터로 실행해도 화면과 설정 안내는 열립니다.

macOS/Linux에서는 `.venv/bin/python`을 사용하고 다음 명령으로 실행합니다.

```bash
.venv/bin/python -m streamlit run service_app/app.py --server.address=127.0.0.1 --server.port=8501 --browser.gatherUsageStats=false
```

### 로컬 AI 연결

[Ollama](https://ollama.com/)를 설치·실행한 뒤:

```text
ollama pull qwen3:4b-instruct
```

약 2.5GB 모델 저장 공간과 추론용 메모리가 필요합니다. 응답 속도는 PC 사양에 따라 달라집니다. 앱은 `127.0.0.1:11434`에만 요청하며 모델이 없으면 안내합니다. LLM 문장은 틀릴 수 있으므로 함께 표시되는 조회 근거를 확인하세요. 최근 대화는 브라우저 세션 메모리에만 보관됩니다.

### 카카오 연결 (선택)

`.env.example`을 참고해 `.env`를 직접 작성합니다. 기존 `.env`는 덮어쓰지 마세요.

```dotenv
KAKAO_REST_API_KEY=발급받은_REST_API_키
KAKAO_FREE_ONLY_CONFIRMED=false
```

기존 `KAKAO_API_KEY` 이름도 지원합니다. 무료 쿼터 적용 및 유료 API 미사용을 확인한 경우에만 두 번째 값을 `true`로 변경합니다. 이 설정이 카카오 계정 과금 정책을 자동 확인하거나 변경하지는 않습니다. 키는 서버에서만 사용하고 Git·답변·모델 요청에 포함하지 않습니다. 카카오에는 채팅에서 추출한 장소명/주소만 전달됩니다. [자세한 설정](docs/kakao-location.md)

## 실제 데이터 준비

```powershell
# 공개 레드버튼 목록 순차 수집 → 검증 → 새 스냅샷 반영
.venv/Scripts/python -B -X utf8 scripts/refresh_redbutton.py

# 다른 매장의 동일 CSV 계약을 검증해 추가
.venv/Scripts/python -B scripts/import_source.py --source partner --directory C:/path/to/csv

# 출처별 데이터 수·수집일·메타데이터 연결 상태 확인
.venv/Scripts/python -B -X utf8 scripts/check_data.py
```

수집기는 외부 사이트 구조와 이용 정책의 영향을 받습니다. 과도한 호출을 피하고 공개 운영·재배포 전에 출처 이용 조건을 확인하세요. 실제 원본 데이터는 업로드하지 않았습니다. 히어로는 CSV 입력을 지원하며 이 배포본에 자동 수집기를 포함하지 않았습니다.

장르별 추천에는 별도의 `master_boardlife.csv` 메타데이터가 필요합니다. 파일이 없으면 정확히 분류할 수 있는 후보가 부족할 수 있으며, 모델이 임의로 채우지 않습니다. BGG 통계는 선택 보강 자료입니다. [CSV 계약과 메타데이터 필드](docs/data-sources.md)

## 구조와 추천 기준

```text
채팅 → 로컬 LLM 조건 추출 → 장소 변경 시 카카오 검색/후보 선택
     → CSV 검색 및 장르·시간·복잡도 검증 → 로컬 LLM 설명 + 실제 근거 표시
```

| 경로 | 역할 |
|---|---|
| `service_app/app.py`, `chat_ui.py` | Streamlit 화면·세션·후속 대화 |
| `local_llm.py` | 구조화된 조건 추출·근거 기반 답변 |
| `search.py`, `intent.py`, `recommendations.py` | 필터·분류·추천 정렬 |
| `kakao_location.py` | 키워드/주소 검색·오류·다중 후보 |
| `snapshots.py` | CSV 검증·원자적 스냅샷 게시 |
| `scripts/` | 수집·데모·데이터 검사·로컬 실행 |
| `tests/` | 외부 자격 증명 없이 실행하는 회귀 테스트 |

가벼운 추천은 복잡도 2/5 이하, 진득한 추천은 2.5/5 이상을 사용합니다. 시간이 명시되지 않으면 각각 최대 45분·180분을 적용하고 표시합니다. 명시된 인원·시간은 규칙 파서로 보정합니다. 추천 시간은 매장 정보와 연결된 게임 메타데이터 중 긴 값이며 설명 시간은 별도입니다. 동일 게임의 여러 매장을 중복 추천하지 않고 본판이 필요한 확장을 제외합니다. 평점 정렬은 최신 인기 순위를 뜻하지 않습니다.

검색은 규칙 기반입니다. 모델 재학습·벡터 검색을 구현한 것으로 주장하지 않습니다. 현재 근거와 명확하게 일치하는 추천을 우선합니다.

## 검증

```powershell
.venv/Scripts/python -B -X utf8 -m unittest discover -s tests -v
```

GitHub Actions는 실제 API 호출·개인 데이터 없이 검색, 화면, 카카오 오류/후보 선택, 복수 추천, 스냅샷 실패 복구를 검증합니다. 실제 Ollama와 준비된 데이터의 추천 확인은 `scripts/verify_chat.py`로 별도 수행할 수 있습니다.

## 공개 운영 전 남은 조건

- 현재는 단일 사용자 로컬 서비스이며 공개 서비스용 인증, 사용자별 저장소, 요청 제한과 모니터링은 미구현입니다.
- 현재 보유 목록은 수집 시점의 정보이며 대여 가능 여부·영업 여부·보행 경로 거리를 보장하지 않습니다.
- 데이터 갱신은 명령으로 실행합니다. 자동 스케줄러가 없습니다.
- 호스팅·모델 서버·카카오 무료 쿼터 정책을 검토해야 합니다. 영구 무료 운영을 보장하지 않습니다.
- 과거 Airflow/PostgreSQL/Gemini 실험, 캐시 바이너리, 미검증 AWS 배포 파일은 현재 서비스 트리에서 제외했습니다. 이전 Git 이력에는 남아 있습니다.
