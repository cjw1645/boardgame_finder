import streamlit as st
from search import store_label
from local_llm import MODEL, available, plan, respond, LocalModelError
from recommendations import recommend
from locations import location_in_text, LocationError
from kakao_location import resolve_location, PlaceChoices, settings


@st.cache_data(ttl=10)
def model_ready():
    return available()


def render_chat(records, options):
    st.subheader('AI와 보드게임 고르기')
    st.caption('대화는 이 PC의 로컬 LLM으로 처리합니다. 장소 변경 시 추출한 장소명·주소만 카카오로 전송합니다.')
    key_ready, free_ready = settings()
    if not key_ready:
        st.caption('카카오 키 설정 필요: .env의 KAKAO_REST_API_KEY 또는 KAKAO_API_KEY에 REST API 키를 넣어 주세요.')
    elif not free_ready:
        st.caption('카카오 키 확인됨 · 무료 쿼터 적용 및 유료 API 미사용 확인이 남아 있습니다. 확인 후 .env에 KAKAO_FREE_ONLY_CONFIRMED=true를 추가해 주세요.')
    else:
        st.caption('카카오 위치 검색 준비됨')
    if 'conversation' not in st.session_state:
        st.session_state.conversation = []
    if st.button('새 대화 시작'):
        st.session_state.conversation = []
        st.session_state.pop('last_plan', None)
        st.session_state.pop('chat_location', None)
        st.session_state.pop('place_choices', None)
    sidebar_position = (options['lat'], options['lon'])
    if st.session_state.get('sidebar_position') != sidebar_position:
        st.session_state.pop('chat_location', None)
    st.session_state.sidebar_position = sidebar_position
    location_status = st.empty()
    def show_location():
        place = st.session_state.get('chat_location')
        location_status.caption(f"대화 출발 위치: {place['label']} · {place['basis']}" if place else '대화 출발 위치: 왼쪽에서 선택한 위치 · “홍대에서 찾아줘”처럼 채팅으로 변경할 수 있어요.')
    show_location()
    ready = model_ready()
    if ready:
        st.caption(f'로컬 모델 연결됨 · {MODEL}')
    else:
        st.warning(f'로컬 모델 준비 중 또는 연결 안 됨. Ollama에서 {MODEL}을 설치·실행해 주세요. 조건 검색 탭은 계속 사용할 수 있습니다.')
    with st.container():
        prompt = st.chat_input('예: 홍대에서 4명, 간단한 파티게임과 진득한 전략게임 추천해줘', max_chars=1000, key='game_chat')
    if prompt:
        if not ready:
            st.error('LLM이 연결되지 않아 메시지를 보내지 않았습니다. 모델 연결 후 다시 입력해 주세요.')
        else:
            history = [{'role': m['role'], 'content': m['content']} for m in st.session_state.conversation[-8:]]
            history.append({'role': 'user', 'content': prompt})
            with st.spinner('로컬 AI가 대화와 매장 데이터를 확인하고 있어요…'):
                try:
                    previous = st.session_state.get('last_plan', {})
                    choices = st.session_state.get('place_choices', [])
                    selection = prompt.strip().removesuffix('번').strip()
                    if choices and selection.isdigit():
                        index = int(selection) - 1
                        if not 0 <= index < len(choices):
                            raise LocationError(f'1~{len(choices)}번 중에서 선택해 주세요.')
                        st.session_state.chat_location = choices[index]
                        st.session_state.pop('place_choices', None)
                        conditions = previous
                        place_name = ''
                        show_location()
                    else:
                        conditions = plan(history, {**options, 'previous': previous,
                            'players': previous.get('players', options['players'])})
                        place_name = location_in_text(prompt, conditions.get('location', ''))
                    if place_name:
                        place = resolve_location(place_name, records)
                        st.session_state.chat_location = place
                        st.session_state.pop('place_choices', None)
                        show_location()
                    place = st.session_state.get('chat_location', {})
                    params = {**options, 'players': conditions['players']}
                    if place:
                        params.update(lat=place['lat'], lon=place['lon'])
                    requests = conditions.get('requests') or [{'query': conditions['query'], 'style': 'any', 'minutes': conditions['minutes']}]
                    groups, parts, results = [], [], []
                    for request in requests:
                        matches = recommend(records, request, params)
                        label = {'light': '가볍게 즐길 ', 'deep': '진득하게 즐길 ', 'any': ''}[request['style']] + (request['query'] or '추천 게임')
                        groups.append(dict(label=label, results=matches, minutes=request['minutes']))
                        results.extend(matches)
                        # Separate prompts prevent one genre's evidence leaking into another.
                        scoped = [{'role': 'user', 'content': f"{conditions['players']}명이 즐길 {label}만 추천해줘"}]
                        parts.append('### ' + label + '\n' + respond(scoped, matches,
                            {'players': conditions['players'], **request, 'location': place.get('label', '사이드바 위치')}))
                    answer = '\n\n'.join(parts)
                    st.session_state.last_plan = conditions
                    st.session_state.conversation.extend([
                        {'role': 'user', 'content': prompt},
                        {'role': 'assistant', 'content': answer, 'results': results, 'conditions': conditions,
                         'groups': groups, 'location': place.get('label', '사이드바 위치')}])
                    st.session_state.conversation = st.session_state.conversation[-20:]
                except LocationError as exc:
                    if isinstance(exc, PlaceChoices):
                        st.session_state.place_choices = exc.places
                    st.session_state.conversation.extend([{'role': 'user', 'content': prompt},
                        {'role': 'assistant', 'content': str(exc)}])
                    # Preserve the requested genres while the user clarifies a place.
                    st.session_state.last_plan = locals().get('conditions', previous)
                except (LocalModelError, ValueError) as exc:
                    st.error(str(exc))
    if not st.session_state.conversation:
        st.info('장소·인원·취향을 함께 말씀해 주세요. “홍대에서 찾아줘”, “그럼 두 명이면?”처럼 이어서 바꿀 수 있습니다. 시간 미지정 시 가벼운 게임은 최대 45분, 진득한 게임은 최대 180분으로 조회합니다.')
    for message in st.session_state.conversation:
        with st.chat_message(message['role']):
            st.markdown(message['content'])
            if 'conditions' in message:
                c = message['conditions']
                st.caption(f"조회 조건: {c['players']}명 · 출발 {message.get('location', '사이드바 위치')}")
                for group in message.get('groups', []):
                    st.caption(f"{group['label']}: 최대 {group['minutes']}분 · 서로 다른 게임 {len(group['results'])}개")
                    for row in group['results']:
                        st.write(f"{row['title_ko']} → {store_label(row)} · {row['distance_km']:.1f}km")
                    if not group['results']:
                        st.info(f"{group['label']} 조건을 확인할 수 있는 후보가 없습니다. 다른 장르로 채우지 않았어요.")
                with st.expander('실제 조회 근거 보기'):
                    for row in message['results']:
                        st.write(f"{row['title_ko']} — {store_label(row)} · {row['distance_km']:.1f}km")
                        st.caption(f"{row['min_players']}~{row['max_players']}명 · {row['playtime_min']}분 · 수집일 {row['collected_date']}")
                        st.caption(' / '.join(row['reasons']))
                        if row.get('metadata_url'):
                            st.link_button('장르·진행 방식 출처', row['metadata_url'])
