"""Deterministic, API-free inventory search with explicit provenance."""
import csv
import math
import re
from collections import defaultdict
from datetime import date
from pathlib import Path
from snapshots import source_directories
from intent import preferences, PREFERENCES, is_easy


def read_csv(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def normalize(value):
    return re.sub(r'[^\w]', '', str(value)).lower()


def store_label(row):
    brand = {'redbutton': '레드버튼', 'hero': '히어로'}.get(row.get('source'), row.get('source', ''))
    branch = row.get('branch_name', '')
    return branch if brand and branch.startswith(brand) else f'{brand} {branch}'.strip()


def distance(lat, lon, other_lat, other_lon):
    a, b = math.radians(lat), math.radians(other_lat)
    h = math.sin((b-a)/2)**2 + math.cos(a)*math.cos(b)*math.sin(math.radians(other_lon-lon)/2)**2
    return 6371.0088 * 2 * math.asin(math.sqrt(min(1, max(0, h))))


def parse_query(query):
    query = expand_numbers(query)
    players = re.search(r'(\d+)\s*(?:명|인)', query)
    hours = re.search(r'(\d+)\s*시간', query)
    minutes = re.search(r'(\d+)\s*분', query)
    duration = (int(hours[1])*60 if hours else 0) + (int(minutes[1]) if minutes else 0)
    if hours and re.search(r'시간\s*반', query):
        duration += 30
    return (int(players[1]) if players else None, duration if hours or minutes else None)


def expand_numbers(query):
    for word, value in {'한': 1, '두': 2, '세': 3, '네': 4, '다섯': 5, '여섯': 6, '일곱': 7, '여덟': 8}.items():
        query = re.sub(rf'(?<![가-힣]){word}\s*(?=명|시간)', str(value), query)
    return query


def query_terms(query):
    # Remove structured constraints before tokenizing so title digits survive.
    query = expand_numbers(query.lower())
    query = re.sub(r'\d+\s*(?:명이서|명|인용|인|시간\s*반|시간|분)(?:이서|정도|안에|이내에|이내)?', ' ', query)
    ignored = {'정도', '동안', '할', '수', '있는', '게임', '보드게임', '추천',
               '추천해줘', '추천해주세요', '안에', '이내', '이내에', '좀', '하고', '싶어', '좋은', '재미있는'}
    return [term for term in re.findall(r'[가-힣a-z0-9]+', query) if term not in ignored]


def load_catalog(data_dir):
    data_dir = Path(data_dir)
    masters = defaultdict(list)
    master_path = data_dir / 'master_boardlife.csv'
    if master_path.exists():
        for row in read_csv(master_path):
            masters[normalize(row['game_name_kr'])].append(row)
    stats_path = data_dir / 'master_bgg_stats.csv'
    stats = {str(row['bgg_id']).removesuffix('.0'): row for row in read_csv(stats_path)} if stats_path.exists() else {}
    records, warnings = [], []
    for source, source_dir in sorted(source_directories(data_dir).items()):
        fact_path = source_dir / f'fact_inventory_{source}.csv'
        try:
            games = {r['game_id']: r for r in read_csv(source_dir / f'dim_game_{source}.csv')}
            stores = {r['store_id']: r for r in read_csv(source_dir / f'dim_store_{source}.csv')}
            seen = set()
            for fact in sorted(read_csv(fact_path), key=lambda r: r.get('collected_date', ''), reverse=True):
                key = (fact['store_id'], fact['game_id'])
                if key in seen:
                    continue
                seen.add(key)
                game, store = games.get(key[1]), stores.get(key[0])
                if not game or not store:
                    warnings.append(f'{source}: 연결되지 않은 보유 기록 제외')
                    continue
                lat, lon = number(store.get('latitude')), number(store.get('longitude'))
                if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    warnings.append(f'{source}: 좌표가 없는 매장 제외')
                    continue
                candidates = masters.get(normalize(game['title_ko']), [])
                master = candidates[0] if len(candidates) == 1 else {}
                bgg_id = str(master.get('bgg_id', '')).removesuffix('.0')
                bgg = stats.get(bgg_id, {})
                records.append({**game, **store, **fact, 'source': source,
                    'latitude': lat, 'longitude': lon,
                    'metadata': ' '.join(master.get(k, '') for k in ('game_name_en', 'categories', 'themes', 'mechanisms')),
                    'bgg_id': bgg_id, 'bgg_rating': number(bgg.get('bgg_rating')),
                    'bgg_weight': number(bgg.get('bgg_weight')), 'bgg_updated_at': bgg.get('bgg_updated_at', ''),
                    'metadata_matched': bool(master)})
                records[-1].update(categories=master.get('categories', ''), themes=master.get('themes', ''),
                    metadata_max_time=number(master.get('max_time')),
                    mechanisms=master.get('mechanisms', ''), metadata_url=master.get('url', ''),
                    recommendation_weight=number(bgg.get('bgg_weight')) or number(master.get('weight')),
                    recommendation_rating=number(bgg.get('bgg_rating')) or number(master.get('rating')))
        except (OSError, KeyError, csv.Error) as exc:
            warnings.append(f'{source}: CSV 형식 또는 파일 확인 필요 ({type(exc).__name__})')
    return records, sorted(set(warnings))


def search(records, query='', *, lat=37.4979, lon=127.0276, radius=5,
           players=None, minutes=None, max_age_days=7, sources=None, today=None, limit=30):
    if not (-90 <= lat <= 90 and -180 <= lon <= 180 and 0 < radius <= 100):
        raise ValueError('위치 또는 반경이 올바르지 않습니다.')
    inferred_players, inferred_minutes = parse_query(query)
    players = inferred_players if inferred_players is not None else players
    minutes = inferred_minutes if inferred_minutes is not None else minutes
    if players is not None and not 1 <= players <= 100:
        raise ValueError('인원은 1~100명으로 입력해 주세요.')
    if minutes is not None and not 1 <= minutes <= 1440:
        raise ValueError('시간은 1~1440분으로 입력해 주세요.')
    today = today or date.today()
    cleaned, easy, excluded = preferences(query)
    terms = query_terms(cleaned)
    synonyms = PREFERENCES
    results = []
    for row in records:
        if sources is not None and row['source'] not in sources:
            continue
        km = distance(lat, lon, row['latitude'], row['longitude'])
        if km > radius:
            continue
        lo, hi, duration = (number(row.get(k)) for k in ('min_players', 'max_players', 'playtime_min'))
        if players is not None and (lo is None or hi is None or not lo <= players <= hi):
            continue
        if minutes is not None and (duration is None or duration > minutes):
            continue
        try:
            age = (today - date.fromisoformat(row['collected_date'][:10])).days
        except (ValueError, KeyError):
            age = None
        if age is not None and age < 0:
            age = None
        if max_age_days is not None and (age is None or age > max_age_days):
            continue
        haystack = normalize(f"{row['title_ko']} {row['metadata']} {row.get('difficulty', '')}")
        if easy and not is_easy(row):
            continue
        if any(any(normalize(word) in haystack for word in PREFERENCES[term]) for term in excluded):
            continue
        title_match = bool(terms) and normalize(' '.join(terms)) in normalize(row['title_ko'])
        matches = [any(normalize(word) in haystack for word in synonyms.get(term, [term])) for term in terms]
        for index, term in enumerate(terms):
            if term == '전략':
                matches[index] = '전략게임' in normalize(row.get('categories', ''))
                title_match = False
        if terms and not (title_match or all(matches)):
            continue
        score = sum(matches) + (5 if title_match else 0)
        reasons = [f'{players}명 플레이 가능'] if players else []
        if minutes:
            reasons.append(f'{duration:g}분 · {minutes}분 이내')
        if easy:
            reasons.append('매장 난이도: 입문/쉬움')
        reasons.extend(f'{term} 정보 일치' for term, matched in zip(terms, matches) if matched)
        results.append({**row, 'distance_km': km, 'age_days': age, 'score': score, 'reasons': reasons})
    return sorted(results, key=lambda r: (-r['score'], r['distance_km'], -(r['bgg_rating'] or 0), r['title_ko']))[:limit]
