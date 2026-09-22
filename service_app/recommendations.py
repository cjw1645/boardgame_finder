"""Grounded genre recommendations; category is distinct from theme/mechanism."""
from search import search, normalize, number


def recommend(records, request, options):
    query, style = request['query'], request.get('style', 'any')
    genre = query if query in ('파티', '전략') else None
    params = {**options, 'minutes': request['minutes'], 'limit': len(records)}
    timed_records = [{**r, 'playtime_min': max(number(r.get('playtime_min')) or 0,
                      number(r.get('metadata_max_time')) or 0) or None} for r in records]
    candidates = search(timed_records, '' if genre else query, **params)
    filtered = []
    for row in candidates:
        category = normalize(row.get('categories', ''))
        weight = number(row.get('recommendation_weight'))
        if genre and normalize(genre + '게임') not in category:
            continue
        if '본판이 필요한 확장' in row.get('themes', ''):
            continue
        # Tradition is not a quality judgement; omit these from general café suggestions.
        if genre and any(t in row['title_ko'] for t in ('윷놀이', '장기', '체스', '바둑')):
            continue
        if style == 'light' and (weight is None or weight > 2):
            continue
        if style == 'deep' and (weight is None or weight < 2.5):
            continue
        why = list(row['reasons'])
        if genre:
            why.append(f'보드라이프 분류: {row["categories"]}')
        if row.get('metadata_max_time'):
            why.append('시간은 매장과 게임 메타데이터 중 긴 값 기준; 설명 시간 별도')
        if weight is not None:
            why.append(f'복잡도 {weight:.2f}/5')
        if row.get('mechanisms'):
            why.append('진행 방식: ' + row['mechanisms'])
        filtered.append({**row, 'reasons': why})
    # Quality within the requested area, then distance. Keep only one store per game.
    filtered.sort(key=lambda r: (-(r.get('recommendation_rating') or 0), r['distance_km'], r['title_ko']))
    result, seen = [], set()
    for row in filtered:
        identity = row.get('bgg_id') or normalize(row['title_ko'])
        if identity not in seen:
            seen.add(identity)
            result.append(row)
        if len(result) == 3:
            break
    return result
