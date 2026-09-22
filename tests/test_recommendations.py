import sys
import unittest
from pathlib import Path
from datetime import date
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'service_app'))
from recommendations import recommend
from locations import resolve_location, location_in_text, LocationError


class RecommendationTests(unittest.TestCase):
    def row(self, title, category='전략게임', weight=3, **extra):
        return dict(title_ko=title, categories=category, recommendation_weight=weight,
                    recommendation_rating=8, metadata='추상전략 파티게임 전략게임',
                    latitude=37.4979, longitude=127.0276, source='test',
                    store_id=title, branch_name=title+'점', address='서울 강남구 테스트로 1',
                    min_players=2, max_players=4, playtime_min=60,
                    collected_date=date.today().isoformat(), bgg_rating=8, **extra)

    def test_strategy_requires_category_and_depth(self):
        rows = [self.row('클러스터', '가족게임', 1), self.row('윷놀이', '파티게임', 1.2),
                self.row('입문전략', weight=1.8), self.row('진득한전략')]
        result = recommend(rows, dict(query='전략', style='deep', minutes=180), dict(players=4))
        self.assertEqual([r['title_ko'] for r in result], ['진득한전략'])

    def test_no_expansions_duplicates_or_unknown_depth(self):
        rows = [self.row('본판'), self.row('본판'), self.row('확장', themes='본판이 필요한 확장'),
                self.row('불명', weight=None)]
        result = recommend(rows, dict(query='전략', style='deep', minutes=180), dict(players=4))
        self.assertEqual([r['title_ko'] for r in result], ['본판'])

    def test_metadata_time_enforced(self):
        result = recommend([self.row('긴게임', metadata_max_time=180)],
                           dict(query='전략', style='deep', minutes=60), dict(players=4))
        self.assertEqual(result, [])

    def test_chat_place_uses_verified_coordinates(self):
        self.assertEqual(location_in_text('홍대에서 찾아줘'), '홍대')
        self.assertEqual(resolve_location('홍대', [])['label'], '홍대입구역')
        self.assertEqual(location_in_text('그럼 추천해줘', '강남역'), '')
        with self.assertRaises(LocationError):
            resolve_location('아무역', [])
        with self.assertRaises(LocationError):
            resolve_location('본판점', [self.row('본판'), {**self.row('본판'), 'store_id': 'other'}])


if __name__ == '__main__':
    unittest.main()
