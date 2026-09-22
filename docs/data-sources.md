# 데이터 소스 계약

기존 hero/redbutton 외에 어떤 이름이든 동일한 파일 3개를 만들면 자동 검색됩니다. 예: `dim_store_partner.csv`, `dim_game_partner.csv`, `fact_inventory_partner.csv`. 새 소스 이름은 영문 소문자와 밑줄을 권장합니다. ID는 다른 소스와 겹치지 않도록 `partner_` 접두사를 사용하세요.

| 파일 | 필수 열 |
|---|---|
| dim_store_SOURCE.csv | store_id,branch_name,address,latitude,longitude |
| dim_game_SOURCE.csv | game_id,title_ko,min_players,max_players,playtime_min |
| fact_inventory_SOURCE.csv | store_id,game_id,collected_date |

UTF-8 CSV를 사용합니다. 쉼표가 든 텍스트는 CSV 표준 큰따옴표로 감쌉니다. 날짜는 `YYYY-MM-DD`, 좌표는 WGS84 십진수입니다. 인원·시간을 모르면 비워두세요. 조건 검색 시 알 수 없는 값은 제외합니다. 수집일을 오늘로 임의 변경하지 마세요. 보유 목록은 수량·대여 가능 여부를 의미하지 않습니다.

예시(가상 데이터, 실제 매장 정보로 바꾸어 사용):

```csv
store_id,branch_name,address,latitude,longitude
partner_demo,테스트 매장,가상 주소,37.4979,127.0276
```
```csv
game_id,title_ko,min_players,max_players,playtime_min
partner_game,테스트 게임,2,4,30
```
```csv
store_id,game_id,collected_date
partner_demo,partner_game,2026-01-01
```

파일을 서비스 정지 상태에서 함께 배치하고 `python scripts/check_data.py`로 누락·건수·출처·날짜를 확인하세요. 게임별 보유 기록 중복은 최신 수집일 하나로 줄입니다. 서로 다른 실제 게임을 같은 이름으로 임의 합치지 않습니다.

## 안전한 신규 소스 반영

직접 파일을 교체하는 대신 아래 명령을 권장합니다.

```powershell
.venv/Scripts/python -B -X utf8 scripts/import_source.py --source partner --directory C:/path/to/csv
```

디렉터리의 `dim_store_partner.csv`, `dim_game_partner.csv`, `fact_inventory_partner.csv`를 검사합니다. 중복 ID·보유 기록, 고아 참조, 미래 날짜, 잘못된 좌표, 뒤집힌 인원 범위가 있으면 반영하지 않습니다. 검증 성공 시 별도 세대 폴더를 만든 뒤 활성 포인터 하나를 원자적으로 교체합니다. 기존 스냅샷은 남겨 두므로 장애 시 복구할 수 있습니다. 화면의 ‘데이터 다시 읽기’로 바로 확인할 수 있습니다.

## 보드라이프와 BGG 메타데이터

선택 파일 `master_boardlife.csv`는 `game_name_kr,bgg_id,game_name_en,categories,themes,mechanisms`를 사용합니다. 유일한 정규화 이름 일치만 메타데이터를 연결합니다. fuzzy 매핑 결과를 검증 없이 추천에 사용하지 않습니다.

`master_bgg_stats.csv`는 `bgg_id,bgg_rating,bgg_weight,bgg_updated_at` 열입니다. BGG 평점은 매장 재고의 근거가 아니라 게임 메타데이터입니다. 기존 BGG 파일은 그대로 활용할 수 있습니다.


메타데이터 수집 자동화는 이 서비스 배포본에 포함하지 않습니다. 적법하게 확보한 메타데이터를 위 계약으로 별도 준비하세요. 장르 추천은 categories, themes, mechanisms, weight, rating, max_time, url 열을 함께 사용합니다. 메타데이터가 없으면 장르를 추측하지 않고 후보 부족으로 안내합니다.
