import pandas as pd
import re
import os
from datetime import datetime
from thefuzz import process, fuzz
from sqlalchemy import create_engine

class BoardGameMapper:
    def __init__(self, df_master_bl):
        """보드라이프 마스터 DB 초기화 및 정규화"""
        self.df_master = df_master_bl.copy()
        self.df_master['norm_name'] = self.df_master['한글이름'].apply(self._normalize_text)
        self.master_choices = self.df_master['norm_name'].tolist()

    def _normalize_text(self, text):
        """특수문자 및 공백 제거 (소문자화)"""
        if pd.isna(text): return ""
        clean_text = re.sub(r'\[.*?\]|\(.*?\)', '', str(text))
        clean_text = re.sub(r'[^\w\s가-힣a-zA-Z0-9]', '', clean_text)
        return re.sub(r'\s+', '', clean_text).lower()

    def _has_expansion_keyword(self, text):
        """확장판 키워드 감지"""
        keywords = ['확장', 'exp', 'expansion', 'ext', '프로모']
        return any(kw in str(text).lower() for kw in keywords)

    def map_games(self, df_source):
        """매핑 및 교차 검증 알고리즘 (Dead Letter Queue 분류 포함)"""
        mapped_results = []
        df_source['norm_title'] = df_source['title_ko'].apply(self._normalize_text)

        for _, row in df_source.iterrows():
            source_id = row['game_id']
            source_name = row['norm_title']
            raw_source_name = str(row['title_ko'])
            source_min_p = row.get('min_players')
            
            # 합본 처리 로직
            if "포함" in raw_source_name or "합본" in raw_source_name:
                source_is_exp = False 
            else:
                source_is_exp = self._has_expansion_keyword(source_name)

            if not self.master_choices:
                continue
                
            # Top 3 후보 추출
            best_matches = process.extract(source_name, self.master_choices, scorer=fuzz.token_sort_ratio, limit=3)
            
            final_match = None
            highest_score = 0

            for match_str, score, _ in best_matches:
                candidate = self.df_master[self.df_master['norm_name'] == match_str].iloc[0]
                master_is_exp = self._has_expansion_keyword(candidate['한글이름'])

                # [검증 1] 확장판 페널티 (-30점)
                if source_is_exp != master_is_exp:
                    score -= 30
                    
                # [검증 2] 인원수 교차 검증 가산점 (+5점)
                if score < 95 and pd.notna(source_min_p) and pd.notna(candidate['Min인원']):
                    if float(source_min_p) == float(candidate['Min인원']):
                        score += 5

                if score > highest_score:
                    highest_score = score
                    final_match = candidate

            # 결과 판별 (85점 기준)
            if highest_score >= 85:
                mapped_results.append({
                    "game_id": source_id, 
                    "BL_ID": final_match['BL_ID'], 
                    "matched_title": final_match['한글이름'],
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
    
    # ==========================================
    # 1. 소스 데이터 로드 (에러 방지 처리)
    # ==========================================
    try:
        # 실제 환경에서는 보드라이프 DB를 SQL이나 CSV에서 불러옵니다.
        df_bl_master = pd.read_csv("/tmp/master_boardlife.csv") 
        
        df_store_hero = pd.read_csv("/tmp/dim_store_hero.csv")
        df_game_hero = pd.read_csv("/tmp/dim_game_hero.csv")
        df_fact_hero = pd.read_csv("/tmp/fact_inventory_hero.csv")
        
        df_store_red = pd.read_csv("/tmp/dim_store_redbutton.csv")
        df_game_red = pd.read_csv("/tmp/dim_game_redbutton.csv")
        df_fact_red = pd.read_csv("/tmp/fact_inventory_redbutton.csv")
    except Exception as e:
        print(f"⚠️ 데이터 로드 실패. 선행 Task(추출)가 완료되었는지 확인하세요: {e}")
        return

    # ==========================================
    # 2. 게임 엔티티 매핑 (Hero & RedButton)
    # ==========================================
    mapper = BoardGameMapper(df_bl_master)
    
    print("🎯 히어로 보드게임 매핑 중...")
    hero_mapped = mapper.map_games(df_game_hero)
    print("🎯 레드버튼 보드게임 매핑 중...")
    red_mapped = mapper.map_games(df_game_red)
    
    # 매핑 결과 통합
    all_mapped = pd.concat([hero_mapped, red_mapped], ignore_index=True)
    
    # 원본 게임 메타데이터 조인 (리뷰용)
    all_source_games = pd.concat([df_game_hero, df_game_red], ignore_index=True)
    df_final_map = pd.merge(all_mapped, all_source_games[['game_id', 'title_ko', 'min_players']], on='game_id', how='left')

    # ==========================================
    # 3. 성공/실패(DLQ) 분리 및 처리
    # ==========================================
    df_success = df_final_map[df_final_map['match_type'] == 'Auto_Matched']
    df_failed = df_final_map[df_final_map['match_type'] == 'Review_Needed']

    print(f"\n📊 매핑 결과 요약:")
    print(f" - 자동 매핑 성공: {len(df_success)}건")
    print(f" - 수동 검토 필요: {len(df_failed)}건")

    if not df_failed.empty:
        today_str = datetime.now().strftime("%Y%m%d")
        fail_filepath = f"/tmp/unmapped_review_{today_str}.csv"
        # 보기 편하게 컬럼 순서 정렬
        df_failed = df_failed[['game_id', 'title_ko', 'min_players', 'score', 'match_type']]
        df_failed.to_csv(fail_filepath, index=False, encoding="utf-8-sig")
        print(f"📁 수동 검토용 DLQ 파일 생성 완료: {fail_filepath}")

    # ==========================================
    # 4. 재고 팩트 테이블(Fact Inventory) ID 교체
    # ==========================================
    # 매핑에 성공한 BL_ID 딕셔너리 생성
    valid_map_dict = dict(zip(df_success['game_id'], df_success['BL_ID']))
    
    master_fact = pd.concat([df_fact_hero, df_fact_red], ignore_index=True)
    # 원본 game_id를 보드라이프 BL_ID로 교체
    master_fact['BL_ID'] = master_fact['game_id'].map(valid_map_dict)
    
    # 매핑 실패해서 BL_ID가 NaN인 재고는 적재하지 않음 (고아 데이터 방지)
    master_fact = master_fact.dropna(subset=['BL_ID'])
    master_fact = master_fact[['store_id', 'BL_ID', 'collected_date']]

    # ==========================================
    # 5. 매장 정보 통합
    # ==========================================
    master_dim_store = pd.concat([df_store_hero, df_store_red], ignore_index=True)

    # ==========================================
    # 6. PostgreSQL DB 최종 적재
    # ==========================================
    print("🔌 PostgreSQL 적재 시작...")
    db_url = "postgresql://myuser:mypassword@localhost:5432/boardgame_db"
    engine = create_engine(db_url)
    
    # 1. 매장 테이블 적재
    master_dim_store.to_sql("master_dim_store", engine, if_exists="replace", index=False)
    # 2. ID 매핑 테이블 적재 (추후 트래킹용)
    df_success[['game_id', 'BL_ID', 'match_type']].to_sql("game_id_map", engine, if_exists="replace", index=False)
    # 3. 재고 팩트 테이블 적재
    master_fact.to_sql("master_fact_inventory", engine, if_exists="replace", index=False)
    
    print("✅ 데이터 대통합 및 적재 파이프라인 완벽 종료!")

if __name__ == "__main__":
    run_integration_and_load()