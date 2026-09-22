"""Print aggregate quality measurements without exposing source rows."""
import json
import sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'service_app'))
from search import load_catalog, search

records, warnings = load_catalog(Path(__file__).resolve().parents[1] / 'data')
print(json.dumps({
    'inventory_records': len(records),
    'stores': len({r['store_id'] for r in records}),
    'games': len({r['game_id'] for r in records}),
    'sources': dict(Counter(r['source'] for r in records)),
    'metadata_matched_records': sum(r['metadata_matched'] for r in records),
    'bgg_enriched_records': sum(r['bgg_rating'] is not None for r in records),
    'latest_collection_by_source': {s: max(r.get('collected_date', '') for r in records if r['source'] == s) for s in {r['source'] for r in records}},
    'recent_gangnam_4player_results': len(search(records, players=4, minutes=60)),
    'warnings': warnings,
}, ensure_ascii=False, indent=2))
