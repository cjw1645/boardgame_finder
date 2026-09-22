import sys
import unittest
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'service_app'))
from search import search, parse_query, distance, load_catalog

class SearchTests(unittest.TestCase):
    def setUp(self):
        self.row = dict(title_ko='테스트 추리', metadata='블러핑 정체 숨기기', latitude=37.4979,
            longitude=127.0276, source='test', min_players='2', max_players='4',
            playtime_min='60', collected_date='2026-09-21', bgg_rating=None)
        self.today = date(2026, 9, 21)

    def find(self, **kwargs):
        return search([self.row], today=self.today, **kwargs)

    def test_prompt_constraints(self):
        self.assertEqual(parse_query('4명이서 1시간 30분'), (4, 90))
        self.assertEqual(parse_query('네 명이서 한 시간 반'), (4, 90))
        self.assertEqual(len(self.find(query='네 명이서 한 시간 마피아 추천해줘')), 1)
        self.assertEqual(len(self.find(query='4명이서 1시간 동안 할 수 있는 마피아 게임 추천해줘')), 1)
        self.assertEqual(self.find(query='5명이서 1시간 마피아'), [])
        self.assertEqual(self.find(minutes=30), [])

    def test_stale_and_missing_dates(self):
        for value in ('2026-06-01', '', '2027-01-01'):
            self.row['collected_date'] = value
            self.assertEqual(self.find(), [])
            self.assertEqual(len(self.find(max_age_days=None)), 1)

    def test_distance_and_source(self):
        self.assertAlmostEqual(distance(0, 0, 0, 1), 111.195, places=2)
        self.assertEqual(self.find(lat=0, lon=0), [])
        self.assertEqual(self.find(sources=[]), [])
        with self.assertRaises(ValueError):
            self.find(lat=91)

    def test_unknown_numeric_fields_excluded(self):
        self.row['max_players'] = 'NaN'
        self.assertEqual(self.find(players=4), [])

    def test_unmatched_query(self):
        self.assertEqual(self.find(query='없는게임'), [])

    def test_title_spacing_and_digits(self):
        self.row['title_ko'] = '세일럼 1692'
        self.assertEqual(len(self.find(query='세일럼1692')), 1)
        self.assertEqual(self.find(query='세일럼 1693'), [])
        self.row['title_ko'] = '다빈치 코드'
        self.assertEqual(len(self.find(query='다빈치코드')), 1)

    def test_all_requested_keywords_required(self):
        self.assertEqual(self.find(query='협력 추리'), [])
        self.row['metadata'] = '협동 블러핑'
        self.assertEqual(len(self.find(query='협력 추리')), 1)

    def test_easy_and_negative_preferences(self):
        self.assertEqual(self.find(query='초보자용 추리'), [])
        self.row['difficulty'] = 'Easy'
        self.assertEqual(len(self.find(query='초보자용 추리')), 1)
        self.assertEqual(self.find(query='마피아 말고 추리'), [])
        self.row['metadata'] = 'deduction'
        self.assertEqual(len(self.find(query='마피아 말고 추리')), 1)

    def test_social_deduction_is_not_any_deduction_game(self):
        self.row['metadata'] = '추리 블러핑'
        self.assertEqual(self.find(query='마피아'), [])

    def test_invalid_duration_is_not_ignored(self):
        for query in ('0분', '25시간', '0명'):
            with self.assertRaises(ValueError):
                self.find(query=query)

    def test_empty_catalog(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(load_catalog(folder), ([], []))

if __name__ == '__main__':
    unittest.main()
