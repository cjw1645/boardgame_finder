"""Server-side Kakao place/address lookup. Never forward chat history or API keys to the LLM."""
import json
import math
import os
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from dotenv import dotenv_values
from locations import LocationError


class PlaceChoices(LocationError):
    def __init__(self, places):
        self.places = places
        super().__init__('출발 장소를 골라 번호로 답해 주세요.\n\n' + '\n\n'.join(
            f"{i}. {p['label']}" for i, p in enumerate(places, 1)))


def settings():
    values = dotenv_values(Path(__file__).resolve().parents[1] / '.env')
    key = next((value.strip() for value in (
        os.getenv('KAKAO_REST_API_KEY'), os.getenv('KAKAO_API_KEY'),
        values.get('KAKAO_REST_API_KEY'), values.get('KAKAO_API_KEY'))
        if value and value.strip()), '')
    return (key,
            os.getenv('KAKAO_FREE_ONLY_CONFIRMED', values.get('KAKAO_FREE_ONLY_CONFIRMED') or '').lower() == 'true')


def fetch(kind, query, key):
    url = 'https://dapi.kakao.com/v2/local/search/' + kind + '.json?' + urlencode({'query': query, 'size': 5})
    req = Request(url, headers={'Authorization': 'KakaoAK ' + key})
    try:
        with urlopen(req, timeout=8) as response:
            data = json.load(response)
        documents = data.get('documents')
        if not isinstance(documents, list):
            raise ValueError('Invalid response')
        return documents
    except HTTPError as exc:
        messages = {401: '카카오 REST API 키를 확인해 주세요.',
                    403: '카카오맵 사용 설정과 REST API 권한을 확인해 주세요.',
                    429: '카카오 요청 한도에 도달했습니다. 추가 요청을 중단했습니다.'}
        raise LocationError(messages.get(exc.code, '카카오 장소 검색에 실패했습니다. 잠시 후 다시 시도해 주세요.')) from None
    except (OSError, URLError, ValueError, TypeError):
        raise LocationError('카카오 장소 검색에 연결하지 못했습니다. 기존 위치로 대신 검색하지 않았어요.') from None


def search_places(query):
    key, free = settings()
    if not key:
        raise LocationError('카카오 위치 검색을 사용하려면 프로젝트 .env에 KAKAO_REST_API_KEY를 설정해 주세요. 키는 채팅에 보내지 마세요.')
    if not free:
        raise LocationError('비용 0원 조건 확인이 필요합니다. 카카오 앱의 무료 쿼터 적용과 유료 API 미사용을 확인한 뒤 .env의 KAKAO_FREE_ONLY_CONFIRMED=true를 설정해 주세요.')
    if not query.strip() or len(query) > 150:
        raise LocationError('검색할 장소명이나 주소를 150자 이내로 알려주세요.')
    docs = fetch('keyword', query, key)
    if not docs:
        docs = fetch('address', query, key)
    places, seen = [], set()
    for doc in docs:
        try:
            lat, lon = float(doc['y']), float(doc['x'])
            if not math.isfinite(lat + lon) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
                continue
            address = doc.get('road_address_name') or doc.get('address_name') or ''
            name = doc.get('place_name') or address
            identity = (name, address, lat, lon)
            if not name or identity in seen:
                continue
            seen.add(identity)
            places.append(dict(label=f'{name} · {address}' if name != address else name,
                               lat=lat, lon=lon, basis='카카오 장소/주소 검색'))
        except (KeyError, ValueError, TypeError):
            continue
    if not places:
        raise LocationError('카카오에서 장소를 찾지 못했어요. 도시명과 역·건물명 또는 도로명 주소를 함께 알려주세요.')
    return places


def resolve_location(name, records=None):
    places = search_places(name)
    if len(places) > 1:
        raise PlaceChoices(places)
    return places[0]
