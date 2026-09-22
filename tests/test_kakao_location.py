import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'service_app'))
from kakao_location import search_places, resolve_location, fetch, PlaceChoices, settings
from locations import LocationError


class KakaoTests(unittest.TestCase):
    def test_existing_key_name_supported_without_bypassing_cost_gate(self):
        with patch.dict('os.environ', {}, clear=True), patch('kakao_location.dotenv_values', return_value={'KAKAO_API_KEY': ' test '}):
            self.assertEqual(settings(), ('test', False))

    def test_environment_key_precedes_file(self):
        with patch.dict('os.environ', {'KAKAO_API_KEY': 'environment'}, clear=True), patch('kakao_location.dotenv_values', return_value={'KAKAO_REST_API_KEY': 'file'}):
            self.assertEqual(settings()[0], 'environment')

    def test_unconfigured_never_calls_api(self):
        for config in [('', True), ('test-key', False)]:
            with patch('kakao_location.settings', return_value=config), patch('kakao_location.fetch') as call:
                with self.assertRaises(LocationError): search_places('홍대')
                call.assert_not_called()

    def test_address_fallback_coordinates(self):
        with patch('kakao_location.settings', return_value=('test-key', True)), patch('kakao_location.fetch', side_effect=[[], [dict(address_name='서울 테스트로 1', x='127.0', y='37.5')]]) as call:
            result = resolve_location('서울 테스트로 1')
            self.assertEqual((result['lat'], result['lon']), (37.5, 127))
            self.assertEqual(call.call_args.args[0], 'address')

    def test_ambiguous_and_invalid_coordinates(self):
        docs = [dict(place_name='중앙역', address_name=a, x='127', y='37') for a in ['안산', '부산']]
        docs.append(dict(place_name='invalid', x='nan', y='37'))
        with patch('kakao_location.settings', return_value=('test-key', True)), patch('kakao_location.fetch', return_value=docs):
            with self.assertRaises(PlaceChoices) as caught: resolve_location('중앙역')
            self.assertEqual(len(caught.exception.places), 2)

    def test_quota_error_no_retry_or_secret(self):
        with patch('kakao_location.urlopen', side_effect=HTTPError('url', 429, 'secret', {}, None)) as call:
            with self.assertRaises(LocationError) as caught: fetch('keyword', '홍대', 'secret')
            self.assertNotIn('secret', str(caught.exception))
            self.assertEqual(call.call_count, 1)

    def test_chat_candidate_selection_preserves_conditions(self):
        from streamlit.testing.v1 import AppTest
        conditions = dict(query='파티', players=4, minutes=45, location='중앙역')
        places = [dict(label='안산 중앙역', lat=37.3, lon=126.8, basis='카카오'),
                  dict(label='부산 중앙역', lat=35.1, lon=129.0, basis='카카오')]
        with patch('chat_ui.model_ready', return_value=True), patch('chat_ui.plan', return_value=conditions), patch('chat_ui.resolve_location', side_effect=PlaceChoices(places)), patch('chat_ui.respond', return_value='추천'):
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'service_app/app.py')).run()
            app.chat_input[0].set_value('중앙역에서 4명 파티게임').run()
            self.assertFalse(app.exception)
            app.chat_input[0].set_value('2번').run()
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state.chat_location['label'], '부산 중앙역')
            self.assertEqual(app.session_state.last_plan['players'], 4)
