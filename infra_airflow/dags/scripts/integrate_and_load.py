import pandas as pd
import re
import os
from datetime import datetime
from thefuzz import process, fuzz
from sqlalchemy import create_engine, text

class BoardGameMapper:
    def __init__(self, df_master_bl, df_manual_map=None, cache_dict=None):
        self.df_master = df_master_bl.copy()
        
        self.df_master['game_name_kr'] = self.df_master['game_name_kr'].fillna('')
        self.df_master['min_players'] = pd.to_numeric(self.df_master['min_players'], errors='coerce')
        
        self.df_master['norm_name'] = self.df_master['game_name_kr'].apply(self._normalize_text)
        self.master_choices = self.df_master['norm_name'].tolist()

        self.manual_dict = {}
        if df_manual_map is not None and not df_manual_map.empty:
            valid_manual = df_manual_map.dropna(subset=['BL_ID'])
            self.manual_dict = dict(zip(valid_manual['game_id'], valid_manual['BL_ID']))
            
        self.cache_dict = cache_dict if cache_dict is not None else {}

    def _normalize_text(self, text):
        if pd.isna(text) or not str(text).strip(): 
            return ""
        clean_text = re.sub(r'\[.*?\]|\(.*?\)', '', str(text))
        clean_text = re.sub(r'[^\w\s가-힣a-zA-Z0-9]', '', clean_text)
        return re.sub(r'\s+', '', clean_text).lower()

    def _has_expansion_keyword(self, text):
        keywords = ['확장', 'exp', 'expansion', 'ext', '프로모']
        return any(kw in str(text).lower() for kw in keywords)

    def map_games(self, df_source):
        mapped_results = []
        df_source['norm_title'] = df_source['title_ko'].apply(self._normalize_text)

        for _, row in df_source.iterrows():
            source_id = row['game_id']
            source_name = row['norm_title']
            raw_source_name = str(row['title_ko'])
            source_min_p = row.get('min_players')

            if source_id in self.manual_dict:
                bl_id = self.manual_dict[source_id]
                matched_row = self.df_master[self.df_master['BL_ID'] == bl_id]
                matched_title = matched_row.iloc[0]['game_name_kr'] if not matched_row.empty else "수동 매핑됨"

                mapped_results.append({
                    "game_id": source_id,
                    "BL_ID": bl_id,
                    "matched_title": matched_title,
                    "match_type": "Manual_Matched",
                    "score": 100 
                })
                continue 

            if source_id in self.cache_dict:
                cached_data = self.cache_dict[source_id]
                mapped_results.append({
                    "game_id": source_id,
                    "BL_ID": cached_data['BL_ID'],
                    "matched_title": cached_data.get('matched_title', '기억에서 불러옴'),
                    "match_type": "Cached_Matched",
                    "score": cached_data.get('score', 100)
                })
                continue

            if "포함" in raw_source_name or "합본" in raw_source_name:
                source_is_exp = False 
            else:
                source_is_exp = self._has_expansion_keyword(source_name)

            if not self.master_choices:
                continue
                
            best_matches = process.extract(source_name, self.master_choices, scorer=fuzz.token_sort_ratio, limit=3)
            
            final_match = None
            highest_score = 0

            for match in best_matches:
                match_str = match[0]
                score = match[1]
                candidate = self.df_master[self.df_master['norm_name'] == match_str].iloc[0]
                master_is_exp = self._has_expansion_keyword(candidate['game_name_kr'])

                if source_is_exp != master_is_exp:
                    score -= 30
                    
                if score < 95 and pd.notna(source_min_p) and pd.notna(candidate['min_players']):
                    try:
                        if float(source_min_p) == float(candidate['min_players']):
                            score += 5
                    except ValueError:
                        pass 

                if score > highest_score:
                    highest_score = score
                    final_match = candidate

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
    print("🔄 데이터 대통합 및 DB 적재 파이프라인 시작 (초고속 캐싱 로직 탑재)...")
    
    dw_user = os.environ.get("DW_DB_USER", "postgres")
    dw_password = os.environ.get("DW_DB_PASSWORD")
    db_url = f"postgresql://{dw_user}:{dw_password}@host.docker.internal:5432/boardgame_db"
    engine = create_engine(db_url)

    cache_dict = {}
    try:
        query = text("SELECT * FROM game_id_map WHERE match_type IN ('Auto_Matched', 'Manual_Matched', 'Cached_Matched')")
        with engine.connect() as conn:
            df_history = pd.read_sql(query, conn)
            
            for _, row in df_history.iterrows():
                cache_dict[row['game_id']] = row.to_dict()
                
        print(f"🧠 성공적인 기억 장착! 과거 {len(cache_dict)}건의 매핑 데이터를 0.1초 만에 스킵합니다.")
    except Exception as e:
        print("🌱 과거 매핑 기록(DB 테이블)이 없습니다. 꼼꼼한 최초 전체 매핑을 1회 진행합니다.")

    try:
        df_bl_master = pd.read_csv("/opt/airflow/data/master_boardlife.csv") 
        df_store_hero = pd.read_csv("/opt/airflow/data/dim_store_hero.csv")
        df_game_hero = pd.read_csv("/opt/airflow/data/dim_game_hero.csv")
        df_fact_hero = pd.read_csv("/opt/airflow/data/fact_inventory_hero.csv")
        df_store_red = pd.read_csv("/opt/airflow/data/dim_store_redbutton.csv")
        df_game_red = pd.read_csv("/opt/airflow/data/dim_game_redbutton.csv")
        df_fact_red = pd.read_csv("/opt/airflow/data/fact_inventory_redbutton.csv")
    except Exception as e:
        print(f"⚠️ 데이터 로드 실패: {e}")
        return

    manual_map_path = "/opt/airflow/data/manual_mapping_master.csv"
    df_manual_map = pd.DataFrame()
    if os.path.exists(manual_map_path):
        df_manual_map = pd.read_csv(manual_map_path)

    mapper = BoardGameMapper(df_bl_master, df_manual_map, cache_dict)
    
    print("🎯 히어로/레드버튼 보드게임 매핑 중...")
    hero_mapped = mapper.map_games(df_game_hero)
    red_mapped = mapper.map_games(df_game_red)
    
    all_mapped = pd.concat([hero_mapped, red_mapped], ignore_index=True)
    all_source_games = pd.concat([df_game_hero, df_game_red], ignore_index=True)
    df_final_map = pd.merge(all_mapped, all_source_games[['game_id', 'title_ko', 'min_players']], on='game_id', how='left')

    df_success = df_final_map[df_final_map['match_type'].isin(['Auto_Matched', 'Manual_Matched', 'Cached_Matched'])]
    df_failed = df_final_map[df_final_map['match_type'] == 'Review_Needed']

    print(f"\n📊 매핑 결과 요약:")
    print(f" - 전체 성공: {len(df_success)}건 (캐시통과: {len(df_success[df_success['match_type']=='Cached_Matched'])}, 신규자동: {len(df_success[df_success['match_type']=='Auto_Matched'])}, 수동: {len(df_success[df_success['match_type']=='Manual_Matched'])})")
    
    if not df_failed.empty:
        today_str = datetime.now().strftime("%Y%m%d")
        fail_filepath = f"/opt/airflow/data/unmapped_review_{today_str}.csv"
        df_failed[['game_id', 'title_ko', 'min_players', 'score', 'match_type']].to_csv(fail_filepath, index=False, encoding="utf-8-sig")

    valid_map_dict = dict(zip(df_success['game_id'], df_success['BL_ID']))
    
    master_fact = pd.concat([df_fact_hero, df_fact_red], ignore_index=True)
    master_fact['BL_ID'] = master_fact['game_id'].map(valid_map_dict)
    master_fact = master_fact.dropna(subset=['BL_ID'])
    master_fact = master_fact[['store_id', 'BL_ID', 'collected_date']]

    master_dim_store = pd.concat([df_store_hero, df_store_red], ignore_index=True)

    print("🔌 PostgreSQL 적재 시작...")
    try:
        master_dim_store.to_sql("master_dim_store", engine, if_exists="replace", index=False)
        df_success[['game_id', 'BL_ID', 'match_type', 'score', 'matched_title']].to_sql("game_id_map", engine, if_exists="replace", index=False)
        master_fact.to_sql("master_fact_inventory", engine, if_exists="replace", index=False)

        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
            conn.execute(text("ALTER TABLE master_dim_store ADD COLUMN IF NOT EXISTS geom GEOMETRY(Point, 4326);"))
            conn.execute(text("""
                UPDATE master_dim_store 
                SET geom = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)
                WHERE longitude IS NOT NULL AND latitude IS NOT NULL;
            """))
            
        print("✅ 초고속 데이터 대통합 파이프라인 및 공간 좌표(Geometry) 매핑 완료!")
    except Exception as e:
        raise Exception(f"DB 적재 실패: {e}")

if __name__ == "__main__":
    run_integration_and_load()