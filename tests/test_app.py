import csv
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'service_app'))
from streamlit.testing.v1 import AppTest

class AppTests(unittest.TestCase):
    def test_search_and_stale_opt_in(self):
        with tempfile.TemporaryDirectory() as folder:
            tables = {
                'dim_game_partner.csv': [{'game_id': 'partner_g', 'title_ko': '마피아', 'min_players': 2, 'max_players': 4, 'playtime_min': 30}],
                'dim_store_partner.csv': [{'store_id': 'partner_s', 'branch_name': '가상매장', 'address': '가상주소', 'latitude': 37.4979, 'longitude': 127.0276}],
                'fact_inventory_partner.csv': [{'store_id': 'partner_s', 'game_id': 'partner_g', 'collected_date': '2000-01-01'}],
            }
            for name, rows in tables.items():
                with (Path(folder) / name).open('w', encoding='utf-8', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                    writer.writeheader()
                    writer.writerows(rows)
            with patch.dict(os.environ, {'DATA_DIR': folder}):
                app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'service_app/app.py'), default_timeout=30).run()
                self.assertEqual(len(app.exception), 0)
                self.assertTrue(any('검색 결과 0건' in h.value for h in app.subheader))
                app.checkbox[0].check().run()
                self.assertEqual(len(app.exception), 0)
                self.assertGreater(len(app.subheader), 1)
                app.text_input[0].set_value('4명이서 1시간 마피아').run()
                self.assertEqual(len(app.exception), 0)
                self.assertGreater(len(app.subheader), 1)
                app.text_input[0].set_value('5명이서 마피아').run()
                self.assertTrue(any('검색 결과 0건' in h.value for h in app.subheader))

if __name__ == '__main__':
    unittest.main()
