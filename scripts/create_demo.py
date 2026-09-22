"""Generate explicitly fictional data; never overwrite existing metadata."""
import csv
import sys
from datetime import date
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'service_app'))
from snapshots import publish


def main():
    root = ROOT / 'data'
    root.mkdir(exist_ok=True)
    metadata = root / 'master_boardlife.csv'
    if metadata.exists():
        raise SystemExit('Existing metadata found. Demo generation stopped without changes.')
    games = [dict(game_id='demo_party', title_ko='[데모] 이야기 카드', min_players=2, max_players=6, playtime_min=20, difficulty='Easy'),
             dict(game_id='demo_strategy', title_ko='[데모] 도시 설계', min_players=2, max_players=4, playtime_min=120, difficulty='Hard')]
    rows = [dict(game_name_kr=g['title_ko'], bgg_id='', game_name_en='',
                 categories=c, themes='', mechanisms=m, weight=w, rating='', max_time=g['playtime_min'], url='')
            for g, c, m, w in zip(games, ['파티게임', '전략게임'], ['스토리텔링', '일꾼 놓기'], [1.2, 3.2])]
    with metadata.open('x', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    publish(root, 'demo', dict(dim_game=games,
        dim_store=[dict(store_id='demo_store', branch_name='[가상] 체험 매장', address='가상 데이터 — 실제 매장 아님', latitude=37.4979, longitude=127.0276)],
        fact_inventory=[dict(store_id='demo_store', game_id=g['game_id'], collected_date=date.today().isoformat()) for g in games]))
    print('Fictional demo published. Disable by removing data/active_demo.json before real service use.')


if __name__ == '__main__':
    main()
