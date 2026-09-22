import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'service_app'))
from local_llm import plan, respond, LocalModelError, generate
from streamlit.testing.v1 import AppTest


class LocalLLMTests(unittest.TestCase):
    def test_two_styles_are_separate_even_if_model_collapses_them(self):
        wrong = dict(query='파티 전략', players=4, minutes=60)
        with patch('local_llm.generate', return_value=json.dumps(wrong)):
            result = plan([dict(role='user', content='4명 간단히 즐길 파티게임과 진득한 전략게임 두 종류')], dict(players=4, minutes=60))
        self.assertEqual([(r['query'], r['style'], r['minutes']) for r in result['requests']],
                         [('파티', 'light', 45), ('전략', 'deep', 180)])

    def test_empty_results_do_not_invent_evidence(self):
        with patch('local_llm.generate') as call:
            answer = respond([], [], {})
        call.assert_not_called()
        self.assertIn('찾지 못했어요', answer)

    def test_explicit_quantities_override_model_mistake(self):
        with patch('local_llm.generate', return_value=json.dumps({'query': '마피아', 'players': 3, 'minutes': 90})):
            result = plan([{'role': 'user', 'content': '네 명이서 한 시간 안에 마피아'}], {'players': 4, 'minutes': 60})
        self.assertEqual((result['players'], result['minutes']), (4, 60))

    def test_invalid_model_constraints_rejected(self):
        with patch('local_llm.generate', return_value=json.dumps({'query': '', 'players': -1, 'minutes': 30})):
            with self.assertRaises(LocalModelError):
                plan([{'role': 'user', 'content': '추천'}], {'players': 4, 'minutes': 60})

    def test_chat_uses_bounded_history_and_evidence(self):
        history = [{'role': 'user', 'content': str(i)} for i in range(20)]
        with patch('local_llm.generate', return_value='답변') as call:
            answer = respond(history, [{'title_ko': '검증된게임', 'collected_date': '2026-09-22'}], {'players': 4})
        self.assertEqual(answer, '답변')
        messages = call.call_args.args[0]
        self.assertEqual(len(messages), 9)
        self.assertIn('검증된게임', messages[0]['content'])

    def test_cloud_model_rejected(self):
        with patch('local_llm.MODEL', 'model:cloud'):
            with self.assertRaises(LocalModelError): generate([])

    def test_chat_input_exists_even_without_data(self):
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'DATA_DIR': folder}), patch('chat_ui.model_ready', return_value=False):
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'service_app/app.py')).run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.chat_input), 1)
            self.assertEqual(len(app.text_input), 1)

    def test_successful_chat_and_followup(self):
        path = str(Path(__file__).resolve().parents[1] / 'service_app/app.py')
        with patch('chat_ui.model_ready', return_value=True), patch('chat_ui.plan', return_value={'query':'마피아', 'players':4, 'minutes':60}) as planner, patch('chat_ui.respond', return_value='보유 목록을 바탕으로 추천합니다.'):
            app = AppTest.from_file(path, default_timeout=30).run()
            app.chat_input[0].set_value('4명 마피아').run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.chat_message), 2)
            app.chat_input[0].set_value('더 쉬운 거').run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.chat_message), 4)
            self.assertEqual(planner.call_args.args[0][-1]['content'], '더 쉬운 거')
            self.assertEqual(planner.call_args.args[0][0]['content'], '4명 마피아')
