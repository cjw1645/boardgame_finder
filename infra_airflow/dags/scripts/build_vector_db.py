import os
import time
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv, find_dotenv
from google import genai

load_dotenv(find_dotenv())
client = genai.Client()

def build_filtered_vector_db():
    print("🚀 매장 보유 보드게임 한정 임베딩 파이프라인 시작...")
    
    db_user = os.environ.get("DW_DB_USER", "postgres")
    db_pass = os.environ.get("DW_DB_PASSWORD")
    db_name = os.environ.get("DW_DB_NAME", "boardgame_db")
    db_url = f"postgresql://{db_user}:{db_pass}@localhost:5432/{db_name}"
    engine = create_engine(db_url)

    # 1. 로컬에 있는 CSV 직접 읽어오기 (상대 경로 자동 계산)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_dir, "../../..")) 
    csv_path = os.path.join(project_root, "data", "master_boardlife.csv")
    
    print(f"📂 CSV 파일 읽는 중: {csv_path}")
    df_bl = pd.read_csv(csv_path)
    # 컬럼명 대소문자 맞추기
    df_bl = df_bl.rename(columns={'BL_ID': 'bl_id'})

    # 2. DB에서 팩트 테이블(재고) 데이터만 가져오기
    with engine.connect() as conn:
        df_fact = pd.read_sql('SELECT DISTINCT "BL_ID" as bl_id FROM master_fact_inventory', conn)

    # 3. Pandas로 교집합(재고 있는 게임) 병합 및 데이터 정제
    df_target = pd.merge(df_bl, df_fact, on='bl_id', how='inner')
    df_target['rating'] = pd.to_numeric(df_target['rating'], errors='coerce').fillna(0)
    df_target['weight'] = pd.to_numeric(df_target['weight'], errors='coerce').fillna(0)

    # 4. DB에 평점/난이도까지 포함된 업그레이드 벡터 테이블 생성
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        conn.execute(text("DROP TABLE IF EXISTS game_embeddings;")) # 깔끔하게 덮어쓰기 위해 드랍
        conn.execute(text("""
            CREATE TABLE game_embeddings (
                bl_id VARCHAR(50) PRIMARY KEY,
                game_name VARCHAR(255),
                rating NUMERIC,
                weight NUMERIC,
                search_text TEXT,
                embedding VECTOR(3072)
            );
        """))
        conn.commit()

    print(f"🎯 임베딩 타겟 보드게임: 총 {len(df_target)}건")

    # 5. API 호출 및 DB 적재
    success_count = 0
    for index, row in df_target.iterrows():
        try:
            bl_id = row['bl_id']
            game_name = row['game_name_kr']
            rating = row['rating']
            weight = row['weight']
            search_text = f"게임명: {game_name}, 카테고리: {row['categories']}, 메커니즘: {row['mechanisms']}, 난이도: {weight}"

            # 임베딩 생성
            result = client.models.embed_content(
                model="gemini-embedding-001",
                contents=search_text
            )
            vector_data = result.embeddings[0].values

            # DB 저장 (begin() 사용으로 자동 커밋)
            with engine.begin() as conn:
                conn.execute(text("""
                    INSERT INTO game_embeddings (bl_id, game_name, rating, weight, search_text, embedding)
                    VALUES (:bl_id, :game_name, :rating, :weight, :search_text, CAST(:embedding AS vector))
                """), {
                    "bl_id": bl_id,
                    "game_name": game_name,
                    "rating": rating,
                    "weight": weight,
                    "search_text": search_text,
                    "embedding": str(vector_data)
                })

            success_count += 1
            if success_count % 10 == 0:
                print(f"✅ {success_count}개 임베딩 완료...")
            
            # API 과부하 방지 딜레이
            time.sleep(1)

        except Exception as e:
            print(f"⚠️ {game_name} 임베딩 중 에러 (API 한도 등): {e}")
            break

    print(f"🎉 총 {success_count}건 임베딩 적재 완료!")

if __name__ == "__main__":
    build_filtered_vector_db()