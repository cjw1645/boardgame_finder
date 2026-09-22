"""Validate and publish complete source generations with one atomic pointer."""
import csv
import json
import math
import os
import re
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

FIELDS = {
    'dim_store': {'store_id', 'branch_name', 'address', 'latitude', 'longitude'},
    'dim_game': {'game_id', 'title_ko', 'min_players', 'max_players', 'playtime_min'},
    'fact_inventory': {'store_id', 'game_id', 'collected_date'},
}


def validate(tables):
    for kind, fields in FIELDS.items():
        rows = tables.get(kind, [])
        if not rows or any(not fields.issubset(row) for row in rows):
            raise ValueError(f'{kind}: empty data or missing columns')
    stores, games = tables['dim_store'], tables['dim_game']
    for rows, key in ((stores, 'store_id'), (games, 'game_id')):
        ids = [str(r[key]).strip() for r in rows]
        if any(not value for value in ids) or len(ids) != len(set(ids)):
            raise ValueError(f'{key}: empty or duplicate IDs')
    for row in stores:
        lat, lon = float(row['latitude']), float(row['longitude'])
        if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180) or (lat == lon == 0):
            raise ValueError('Invalid store coordinates')
    for row in games:
        if not str(row['title_ko']).strip():
            raise ValueError('Empty title')
        values = []
        for key in ('min_players', 'max_players', 'playtime_min'):
            value = row[key]
            numeric = None if value is None or str(value).strip() == '' else float(value)
            if numeric is not None and (not math.isfinite(numeric) or numeric <= 0):
                raise ValueError(f'Invalid {key}')
            values.append(numeric)
        if values[0] is not None and values[1] is not None and values[0] > values[1]:
            raise ValueError('Reversed player range')
    store_ids, game_ids = {r['store_id'] for r in stores}, {r['game_id'] for r in games}
    seen = set()
    for row in tables['fact_inventory']:
        key = (row['store_id'], row['game_id'])
        if key in seen or key[0] not in store_ids or key[1] not in game_ids:
            raise ValueError('Duplicate or orphan inventory')
        seen.add(key)
        if date.fromisoformat(row['collected_date']) > date.today():
            raise ValueError('Future collection date')


def publish(root, source, tables):
    if not re.fullmatch(r'[a-z][a-z0-9_]*', source):
        raise ValueError('Invalid source name')
    validate(tables)
    root = Path(root).resolve()
    generation = root / 'snapshots' / source / uuid.uuid4().hex
    generation.mkdir(parents=True)
    for kind, rows in tables.items():
        if kind not in FIELDS:
            continue
        with (generation / f'{kind}_{source}.csv').open('w', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    manifest = {'directory': generation.relative_to(root).as_posix(),
                'published_at': datetime.now(timezone.utc).isoformat(),
                'counts': {k: len(v) for k, v in tables.items()}}
    pointer = root / f'active_{source}.json'
    temporary = root / f'.{pointer.name}.{uuid.uuid4().hex}.tmp'
    temporary.write_text(json.dumps(manifest, ensure_ascii=False), encoding='utf-8')
    os.replace(temporary, pointer)
    return manifest


def source_directories(root):
    root = Path(root).resolve()
    sources = {p.stem.removeprefix('fact_inventory_'): root for p in root.glob('fact_inventory_*.csv')}
    for pointer in root.glob('active_*.json'):
        source = pointer.stem.removeprefix('active_')
        directory = (root / json.loads(pointer.read_text(encoding='utf-8'))['directory']).resolve()
        if not directory.is_relative_to(root / 'snapshots') or not directory.is_dir():
            raise ValueError(f'Invalid snapshot pointer: {source}')
        sources[source] = directory
    return sources


def revision(root):
    root = Path(root)
    return tuple((p.name, p.stat().st_mtime_ns, p.stat().st_size)
                 for p in sorted(root.iterdir()) if p.suffix in ('.csv', '.json')) if root.is_dir() else ()
