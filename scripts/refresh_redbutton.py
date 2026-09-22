"""Run locally: fetch public inventory, validate, then atomically publish."""
import sys
import json
from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'service_app'))
sys.path.insert(0, str(ROOT / 'scripts'))
from snapshots import publish
from extract_redbutton import RedButtonPipeline


def main():
    pipeline = RedButtonPipeline()
    stores = pipeline.build_dim_store()
    games = pipeline.build_dim_game()
    inventory = pipeline.build_fact_inventory(stores)
    staging = ROOT / 'data' / 'collection_runs' / datetime.now().strftime('%Y%m%dT%H%M%S')
    staging.mkdir(parents=True, exist_ok=False)
    for kind, frame in [('dim_store', stores), ('dim_game', games), ('fact_inventory', inventory)]:
        frame.to_csv(staging / f'{kind}_redbutton.csv', index=False, encoding='utf-8')
    # Preserve complete raw response-derived tables for review before filtering.
    invalid = games['title_ko'].fillna('').str.strip().eq('')
    rejected = games.loc[invalid, 'game_id'].tolist()
    if invalid.mean() > 0.01:
        raise ValueError('More than 1% of game names missing; review parser')
    excluded_facts = inventory['game_id'].isin(rejected)
    report = {'rejected_game_ids': rejected, 'excluded_inventory_count': int(excluded_facts.sum()),
              'reason': 'empty source title', 'raw_directory': str(staging.relative_to(ROOT / 'data'))}
    (staging / 'quality.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Quality review:', report)
    games = games.loc[~invalid]
    inventory = inventory.loc[~excluded_facts]
    tables = {k: v.astype(object).where(v.notna(), None).to_dict('records') for k, v in
              [('dim_store', stores), ('dim_game', games), ('fact_inventory', inventory)]}
    result = publish(ROOT / 'data', 'redbutton', tables)
    print('Published validated snapshot:', result)


if __name__ == '__main__':
    main()
