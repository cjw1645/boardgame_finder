import pandas as pd
import re
import os
from datetime import datetime
from thefuzz import process, fuzz
from sqlalchemy import create_engine

class BoardGameMapper:
    def __init__(self, df_master_bl):
        """
        보드라이프 마스터 DB 초기화 및 매핑 전처리
        - 결측치 처리 및 데이터 타입 강제 변환 수행
        """
        self.df_master = df_master_bl.copy()
        
        self.df_master['game_name_kr'] = self.df_master['game_name_kr'].fillna('')
        self.df_master['min_players'] = pd.to_numeric(self.df_master['min_players'], errors='coerce')
        
        self.df_master['norm_name'] = self.df_master['game_name_kr'].apply(self._normalize_text)
        self.master_choices = self.df_master['norm_name'].tolist()

    def _normalize_text(self, text):
        """
        텍스트 유사도 비교를 위한 문자열 정규화
        - 괄호 내 부제 제거, 특수문자 제거, 소문자 변환
        """
        if pd.isna(text) or not str(text).strip(): 
            return ""
        clean_text = re.sub(r'\[.*?\]|\(.*?\)', '', str(text))
        clean_text = re.sub(r'[^\w\s가-힣a-zA-Z0-9]', '', clean_text)
        return re.sub(r'\s+', '', clean_text).lower()

    def _has_expansion_keyword(self, text):
        """게임명 내 확장판/프로모 관련 키워드 포함 여부 확인"""
        keywords = ['확장', 'exp', 'expansion', 'ext', '프로모']
        return any(kw in str(text).lower() for kw in keywords)

    def map_games(self, df_source):
        """
        Fuzzy String Matching을 활용한 게임 메타데이터 매핑 알고리즘
        - Score 기반 매칭 판별 (임계치 85점)
        - 본판/확장판 교차 검증 및 최소 인원수 비교 가산점 적용
        """
        mapped_results = []
        df_source['norm_title'] = df_source['title_ko'].apply(self._normalize_text)

        for _, row in df_source.iterrows():
            source_id = row['game_id']
            source_name = row['norm_title']
            raw_source_name = str(row['title_ko'])
            source_min_p = row.get('min_players')
            
            # 소스 데이터의 확장판 여부 판별 (합본은 본판으로 취급)
            if "포함" in raw_source_name or "합본" in raw_source_name:
                source_is_exp = False 
            else:
                source_is_exp = self._has_expansion_keyword(source_name)

            if not self.master_choices:
                continue
                
            # Levenshtein distance 기반 상위 3개 후보군 추출
            best_matches = process.extract(source_name, self.master_choices, scorer=fuzz.token_sort_ratio, limit=3)
            
            final_match = None
            highest_score = 0

            # ⭐️ 반환값의 길이에 상관없이 안전하게 언패킹하도록 수정
            for match in best_matches:
                match_str = match[0]  # 첫 번째 요소: 문자열
                score = match[1]      # 두 번째 요소: 점수

                candidate = self.df_master[self.df_master['norm_name'] == match_str].iloc[0]
                master_is_exp = self._has_expansion_keyword(candidate['game_name_kr'])

                # [검증 1] 소스와 마스터 간 본판/확장판 속성이 불일치할 경우 페널티 부여
                if source_is_exp != master_is_exp:
                    score -= 30
                    
                # [검증 2] 매칭 점수가 100점이 아닐 경우, 최소 인원수가 일치하면 가산점 부여
                if score < 95 and pd.notna(source_min_p) and pd.notna(candidate['min_players']):
                    try:
                        if float(source_min_p) == float(candidate['min_players']):
                            score += 5
                    except ValueError:
                        pass 

                if score > highest_score:
                    highest_score = score
                    final_match = candidate

            # 최종 점수에 따른 Auto_Matched / Review_Needed(DLQ) 분류
            if highest_score >= 85:
                mapped_results.append({
                    "game_id": source_id, 
                    "BL_ID": final_match['BL_ID'], 
                    "matched_title": final_match['game_name_kr'],
                    "match_type": "Auto_Matched", 
                    "score": highest_score
                })
            else:
                mapped_results.append({
                    "game_id": source_id, 
                    "BL_ID": None, 
                    "matched_title": None,
                    "match_type": "Review_Needed", 
                    "score": highest_score
                })

        return pd.DataFrame(mapped_results)

def run_integration_and_load():
    print("🔄 데이터 대통합 및 DB 적재 파이프라인 시작...")
    
    # 1. 소스 데이터 로드
    try:
        df_bl_master = pd.read_csv("/opt/airflow/data/master_boardlife.csv") 
        
        df_store_hero = pd.read_csv("/opt/airflow/data/dim_store_hero.csv")
        df_game_hero = pd.read_csv("/opt/airflow/data/dim_game_hero.csv")
        df_fact_hero = pd.read_csv("/opt/airflow/data/fact_inventory_hero.csv")
        
        df_store_red = pd.read_csv("/opt/airflow/data/dim_store_redbutton.csv")
        df_game_red = pd.read_csv("/opt/airflow/data/dim_game_redbutton.csv")
        df_fact_red = pd.read_csv("/opt/airflow/data/fact_inventory_redbutton.csv")
    except Exception as e:
        print(f"⚠️ 데이터 로드 실패. 선행 Task가 정상적으로 완료되었는지 확인하세요: {e}")
        return

    # 2. 매장별 보드게임 엔티티 매핑 수행
    mapper = BoardGameMapper(df_bl_master)
    
    print("🎯 히어로 보드게임 매핑 중...")
    hero_mapped = mapper.map_games(df_game_hero)
    print("🎯 레드버튼 보드게임 매핑 중...")
    red_mapped = mapper.map_games(df_game_red)
    
    all_mapped = pd.concat([hero_mapped, red_mapped], ignore_index=True)
    all_source_games = pd.concat([df_game_hero, df_game_red], ignore_index=True)
    df_final_map = pd.merge(all_mapped, all_source_games[['game_id', 'title_ko', 'min_players']], on='game_id', how='left')

    # 3. 매핑 결과 분리 및 수동 검토용(DLQ) 데이터 저장
    df_success = df_final_map[df_final_map['match_type'] == 'Auto_Matched']
    df_failed = df_final_map[df_final_map['match_type'] == 'Review_Needed']

    print(f"\n📊 매핑 결과 요약:")
    print(f" - 자동 매핑 성공: {len(df_success)}건")
    print(f" - 수동 검토 필요: {len(df_failed)}건")

    if not df_failed.empty:
        today_str = datetime.now().strftime("%Y%m%d")
        fail_filepath = f"/opt/airflow/data/unmapped_review_{today_str}.csv"
        df_failed = df_failed[['game_id', 'title_ko', 'min_players', 'score', 'match_type']]
        df_failed.to_csv(fail_filepath, index=False, encoding="utf-8-sig")
        print(f"📁 수동 검토용 DLQ 파일 생성 완료: {fail_filepath}")

    # 4. 재고 팩트 테이블(Fact Inventory) 식별자 교체 및 고아 데이터 제거
    valid_map_dict = dict(zip(df_success['game_id'], df_success['BL_ID']))
    
    master_fact = pd.concat([df_fact_hero, df_fact_red], ignore_index=True)
    master_fact['BL_ID'] = master_fact['game_id'].map(valid_map_dict)
    master_fact = master_fact.dropna(subset=['BL_ID'])
    master_fact = master_fact[['store_id', 'BL_ID', 'collected_date']]

    # 5. 매장 차원 테이블 통합
    master_dim_store = pd.concat([df_store_hero, df_store_red], ignore_index=True)

    # 6. PostgreSQL DB 최종 적재
    print("🔌 PostgreSQL 적재 시작...")
    
    dw_user = os.environ.get("DW_DB_USER", "myuser")
    dw_password = os.environ.get("DW_DB_PASSWORD", "mypassword")
    db_url = f"postgresql://{dw_user}:{dw_password}@host.docker.internal:5432/boardgame_db"
    
    try:
        engine = create_engine(db_url)
        master_dim_store.to_sql("master_dim_store", engine, if_exists="replace", index=False)
        df_success[['game_id', 'BL_ID', 'match_type']].to_sql("game_id_map", engine, if_exists="replace", index=False)
        master_fact.to_sql("master_fact_inventory", engine, if_exists="replace", index=False)
        
        print("✅ 데이터 대통합 및 적재 파이프라인 완료")
    except Exception as e:
        print(f"❌ DB 적재 실패: {e}")

if __name__ == "__main__":
    run_integration_and_load()