import os
from pathlib import Path
from urllib.parse import quote
import streamlit as st
from search import load_catalog, search, parse_query
from snapshots import revision
from chat_ui import render_chat

st.set_page_config(page_title='보드게임 파인더', page_icon='🎲', layout='wide')
st.title('🎲 오늘, 어떤 보드게임 할까요?')
st.write('인원과 시간을 골라 가까운 매장의 보유 게임을 찾아보세요.')
st.caption('공개 보유 목록의 수집 시점 기준입니다. 현재 대여 가능 여부와 영업 여부는 매장에 확인해 주세요.')

@st.cache_data(ttl=300)
def catalog(path, version):
    return load_catalog(path)

data_path = os.getenv('DATA_DIR', str(Path(__file__).resolve().parents[1] / 'data'))
try:
    records, warnings = catalog(data_path, revision(data_path))
except (OSError, ValueError, KeyError):
    st.error('데이터 파일을 읽지 못했습니다. 운영자가 스냅샷과 CSV 형식을 확인해야 합니다.')
    records, warnings = [], []
if not records:
    st.info('매장 데이터가 없습니다. 운영자가 data 폴더에 매장·게임·보유 목록 CSV를 추가하면 검색할 수 있습니다.')
with st.sidebar:
    st.header('📍 검색 조건')
    locations = {'강남역': (37.4979, 127.0276), '홍대입구역': (37.5572, 126.9254),
                 '건대입구역': (37.5404, 127.0692), '수원역': (37.2663, 126.9998),
                 '부산 서면역': (35.1579, 129.0595), '직접 좌표 입력': (37.4979, 127.0276)}
    location = st.selectbox('출발 위치', list(locations))
    lat, lon = locations[location]
    if location == '직접 좌표 입력':
        lat = st.number_input('위도', min_value=-90.0, max_value=90.0, value=lat, format='%.5f')
        lon = st.number_input('경도', min_value=-180.0, max_value=180.0, value=lon, format='%.5f')
    radius = st.slider('반경 (km)', 1, 30, 5)
    players = st.number_input('인원', min_value=1, max_value=100, value=4)
    minutes = st.slider('최대 플레이 시간 (분)', 10, 240, 60, step=10)
    sources = st.multiselect('매장 데이터 출처', sorted({r['source'] for r in records}), default=sorted({r['source'] for r in records}))
    old = st.checkbox('오래된 보유 목록도 포함', value=False)
    st.caption('기본 검색은 최근 7일 이내에 수집된 목록만 사용합니다.')
    if st.button('데이터 다시 읽기'):
        catalog.clear()
        st.rerun()
chat_tab, search_tab = st.tabs(['AI 대화', '조건 검색'])
with chat_tab:
    render_chat(records, dict(lat=lat, lon=lon, radius=radius, players=players, minutes=minutes, sources=sources, max_age_days=None if old else 7))
with search_tab:
    with st.expander('수집 데이터 현황'):
        for source in sorted({r['source'] for r in records}):
            subset = [r for r in records if r['source'] == source]
            latest = max(r.get('collected_date', '') for r in subset)
            st.write(f"{source} · {len({r['store_id'] for r in subset})}개 매장 · {len(subset):,}건 · 마지막 수집 {latest}")
    query = st.text_input('게임 이름이나 취향', placeholder='예: 4명이서 1시간 동안 할 수 있는 마피아 게임 추천해줘', max_chars=300)
    with st.expander('이렇게 검색할 수 있어요'):
        st.write('네 명이서 한 시간 마피아 추천해줘 / 초보자용 협력 게임 / 마피아 말고 추리 / 다빈치코드')
        st.caption('지원하는 취향: 마피아·추리·협력·전략·파티·블러핑·입문 난이도. 질문에 적은 인원과 시간이 왼쪽 조건보다 우선합니다.')
    ip, im = parse_query(query)
    st.caption(f'적용 조건: {ip if ip is not None else players}명 · 최대 {im if im is not None else minutes}분 · {radius}km · API 호출 비용 없음')
    try:
        results = search(records, query, lat=lat, lon=lon, radius=radius, players=players, minutes=minutes, sources=sources, max_age_days=None if old else 7)
    except ValueError as exc:
        st.warning(str(exc))
        st.stop()
    st.subheader(f'검색 결과 {len(results)}건')
    st.caption('키워드 관련도, 가까운 거리, BGG 평점 순으로 최대 30건을 표시합니다. 자연어 이해 범위는 인원·시간과 일부 취향 키워드입니다.')
    if old:
        st.warning('과거 보유 목록을 포함한 결과입니다. 방문 전 매장에 확인해 주세요.')
    if not results:
        st.info('조건에 맞는 최근 보유 목록이 없습니다. 검색어나 반경을 조정하거나 오래된 보유 목록을 포함해 보세요.')
    for row in results:
        with st.container(border=True):
            st.subheader(row['title_ko'])
            brand = {'hero': '히어로', 'redbutton': '레드버튼'}.get(row['source'], row['source'])
            st.write(f"{brand} {row['branch_name']} · {row['distance_km']:.1f}km")
            st.write(f"{row.get('min_players', '?')}~{row.get('max_players', '?')}명 · {row.get('playtime_min', '?')}분")
            st.caption('추천 근거: ' + ' / '.join(row['reasons']))
            st.text(row.get('address', ''))
            st.caption(f"보유 출처: {row['source']} · 수집일: {row.get('collected_date', '알 수 없음')}")
            if row['bgg_rating'] is not None:
                st.caption(f"BoardGameGeek 평점 {row['bgg_rating']:.2f}/10 · 난이도 {row['bgg_weight']} · 수집일 {row['bgg_updated_at']}")
                if row['bgg_id'].isdigit():
                    st.link_button('BGG 게임 정보', f"https://boardgamegeek.com/boardgame/{row['bgg_id']}")
            st.link_button('지도에서 매장 찾기', 'https://map.kakao.com/?q=' + quote(f"{brand} {row['branch_name']} {row.get('address', '')}"))
            source_url = {'redbutton': 'https://redbutton.co.kr/', 'hero': 'https://funhero.co.kr'}.get(row['source'])
            if source_url:
                st.link_button('매장 공식 사이트', source_url)
    if warnings:
        with st.expander('데이터 상태'):
            for warning in warnings:
                st.caption(warning)
