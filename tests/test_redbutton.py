import sys
import unittest
from pathlib import Path
from unittest.mock import Mock
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from extract_redbutton import RedButtonPipeline


class RedbuttonTests(unittest.TestCase):
    def crawler(self, html):
        crawler = RedButtonPipeline.__new__(RedButtonPipeline)
        crawler.session = Mock()
        crawler.session.post.return_value.json.return_value = {'html': html}
        crawler.api_url, crawler.headers, crawler.timeout = 'https://example.test', {}, 1
        return crawler

    def test_empty_store_response_fails_closed(self):
        crawler = self.crawler('')
        with self.assertRaises(RuntimeError):
            crawler.build_fact_inventory(pd.DataFrame([{'store_id': 'red_1', 'branch_id': 1}]))

    def test_longest_duration_is_used(self):
        crawler = self.crawler('''<div class="red-game-wrap">
        <span class="content-rule">난이도 Easy</span><span class="content-rule">2~4명</span>
        <span class="content-rule">30~60분</span><span class="game-title">게임</span>
        <span class="content-store" data-game-id="1"></span></div>''')
        row = crawler.build_dim_game().iloc[0]
        self.assertEqual(row['playtime_min'], 60)
        self.assertEqual(row['max_players'], 4)
