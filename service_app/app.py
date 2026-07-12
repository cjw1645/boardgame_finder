import streamlit as st
import pandas as pd
import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv, find_dotenv
from google import genai

load_dotenv(find_dotenv())
client = genai.Client()

st.set_page_config(page_title="보드게임 O2O 추천 AI", page_icon="🎲", layout="wide")

@st.cache_resource
def init_connection():
    db_user = os.environ.get("DW_DB_USER", "postgres")
    db_pass = os.environ.get("DW_DB_PASSWORD")
    db_name = os.environ.get("DW_DB_NAME", "boardgame_db")
    db_url = f"postgresql://{db_user}:{db_pass}@host.docker.internal:5432/{db_name}"
    return create_engine(db_url)

engine = init_connection()

# --- 사이드바: 사용자 위치 설정 (로컬 테스트용) ---
with st.sidebar:
    st.header("📍 내 위치 설정")
    st.write("로컬 환경이므로 테스트할 위치 좌표를 입력해주세요.")
    # 기본값: 강남역 부근 좌표 (아까 강남2호점 데이터가 있었으므로 테스트에 적합합니다)
    user_lat = st.number_input("위도 (Latitude)", value=37.4979, format="%.5f")
    user_lon = st.number_input("경도 (Longitude)", value=127.0276, format="%.5f")
    max_dist = st.slider("탐색 반경 (km)", min_value=1, max_value=20, value=5)

# --- 메인 화면 ---
st.title("🎲 AI 보드게임 추천 & 매장 안내 직원")
st.write("찾으시는 보드게임 스타일을 말씀해 주세요! 근처 매장의 재고까지 확인해 드립니다.")

if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("예: 4명이서 1시간 정도 할 수 있는 마피아 게임 추천해줘!"):
    
    with st.chat_message("user"):
        st.markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("assistant"):
        with st.spinner("가까운 매장 재고와 AI 데이터를 대조 중입니다... 🏃‍♂️"):
            try:
                query_vector = str([0.01] * 3072) 
                
                search_query = text("""
                    SELECT e.game_name, e.search_text, 
                           e.rating, 
                           st.store_id, st.branch_name, st.address,
                           ROUND((ST_DistanceSphere(st.geom, ST_MakePoint(:user_lon, :user_lat)) / 1000)::numeric, 1) as dist_km
                    FROM game_embeddings e
                    JOIN master_fact_inventory f ON e.bl_id = f."BL_ID"
                    JOIN master_dim_store st ON f.store_id = st.store_id
                    WHERE ST_DistanceSphere(st.geom, ST_MakePoint(:user_lon, :user_lat)) <= :max_dist_m
                    ORDER BY e.embedding <=> CAST(:vector AS vector)
                    LIMIT 3;
                """)
                
                with engine.connect() as conn:
                    result = conn.execute(search_query, {
                        "vector": query_vector,
                        "user_lat": user_lat,
                        "user_lon": user_lon,
                        "max_dist_m": max_dist * 1000
                    }).fetchall()

                if not result:
                    st.warning(f"반경 {max_dist}km 이내의 매장 중 조건에 맞는 게임 재고를 찾지 못했습니다.")
                else:
                    context = "다음은 DB에서 찾은 반경 내 추천 후보 게임과 매장 정보입니다:\n"
                    for row in result:
                        # ⭐️ 브랜드명 판단 및 매장 이름 예쁘게 포장하기
                        brand_name = "히어로 보드게임카페" if "hero" in row.store_id else "레드버튼"
                        display_store_name = f"{brand_name} {row.branch_name}" # 예: 레드버튼 강남2호점

                        context += f"- 게임명: **{row.game_name}** (평점: {row.rating}) / 정보: {row.search_text}\n"
                        context += f"  👉 보유 매장: **{display_store_name}** ({row.dist_km}km 거리, 주소: {row.address})\n\n"

                    fake_response = f"""
                    **[구글 서버 파업으로 인한 임시 AI 답변입니다]** 🤖\n
                    요청하신 조건에 맞는 게임을 찾아보았습니다. 아래 매장 정보를 확인해 주세요!\n\n{context}
                    """
                    
                    st.markdown(fake_response)
                    st.session_state.messages.append({"role": "assistant", "content": fake_response})
                
            except Exception as e:
                st.error(f"앗, 검색 중 오류가 발생했습니다: {e}")