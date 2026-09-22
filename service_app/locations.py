"""Resolve chat locations from local station presets and collected public stores."""
import re
from statistics import median
from search import normalize

PRESETS = {'강남역': (37.4979, 127.0276), '홍대입구역': (37.5572, 126.9254),
           '건대입구역': (37.5404, 127.0692), '수원역': (37.2663, 126.9998),
           '부산 서면역': (35.1579, 129.0595)}
ALIASES = {'강남': '강남역', '홍대': '홍대입구역', '홍대입구': '홍대입구역', '건대': '건대입구역',
           '건대입구': '건대입구역', '서면': '부산 서면역', '서면역': '부산 서면역'}


class LocationError(ValueError):
    pass


def resolve_location(name, records):
    key = normalize(name)
    for alias, target in ALIASES.items():
        if key == normalize(alias):
            key = normalize(target)
    for label, (lat, lon) in PRESETS.items():
        if key == normalize(label):
            return dict(label=label, lat=lat, lon=lon, basis='역 위치')
    stores = {(r['source'], r['store_id']): r for r in records}.values()
    branch_key = key.removesuffix('역')
    matches = [r for r in stores if key in (normalize(r['branch_name']),
        normalize(r['branch_name'].removesuffix('점')), normalize(r['address']))
        or key == normalize(r['source'] + r['branch_name'])
        or branch_key == normalize(r['branch_name'].removesuffix('점'))]
    if len(matches) == 1:
        row = matches[0]
        return dict(label=f"{row['branch_name']} ({row['address']})", lat=row['latitude'],
                    lon=row['longitude'], basis='수집된 매장 위치')
    if len(matches) > 1:
        raise LocationError('같은 이름의 매장이 여러 곳입니다. 다음 주소 중 하나로 알려주세요: ' +
                            ' / '.join(sorted({r['address'] for r in matches})[:5]))
    # District lookup uses an explicitly labelled store centroid, never fabricated coordinates.
    area = [r for r in stores if key in [normalize(t) for t in r['address'].split()[:3]]
            or key == normalize(' '.join(r['address'].split()[:2]))]
    if area:
        cities = {r['address'].split()[0] for r in area}
        if len(cities) > 1:
            raise LocationError('여러 도시에 있는 지역명입니다. 매장명이나 전체 주소로 알려주세요.')
        return dict(label=name, lat=median(r['latitude'] for r in area),
                    lon=median(r['longitude'] for r in area), basis='해당 지역 수집 매장들의 중심')
    raise LocationError(f'“{name}”의 위치를 로컬 데이터에서 확인하지 못했어요. '
                        '강남역·홍대입구역·건대입구역·수원역·서면역 또는 매장명·매장 주소로 알려주세요.')


def location_in_text(text, extracted=''):
    # The model extracts a name only; coordinates always come from the local catalog.
    if extracted and normalize(extracted) in normalize(text):
        return extracted
    for label in sorted([*PRESETS, *ALIASES], key=len, reverse=True):
        if re.search(r'(?<![가-힣])' + re.escape(label) + r'(?:에서|으로|로|근처|\s|$)', text):
            return label
    match = re.search(r'([가-힣0-9]+역)(?:에서|으로|\s|근처|$)', text)
    return match[1] if match else ''
