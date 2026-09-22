import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'service_app'))
from snapshots import publish, source_directories, revision
from search import load_catalog


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tables = {
            'dim_store': [dict(store_id='s', branch_name='매장', address='주소', latitude=37.5, longitude=127)],
            'dim_game': [dict(game_id='g', title_ko='게임', min_players=2, max_players=4, playtime_min=30)],
            'fact_inventory': [dict(store_id='s', game_id='g', collected_date='2026-01-01')],
        }

    def test_invalid_import_preserves_active_generation(self):
        with tempfile.TemporaryDirectory() as root:
            publish(root, 'partner', self.tables)
            before = revision(root)
            for change in ('empty', 'orphan', 'duplicate', 'bad_coordinates', 'future'):
                data = copy.deepcopy(self.tables)
                if change == 'empty': data['dim_game'] = []
                if change == 'orphan': data['fact_inventory'][0]['game_id'] = 'unknown'
                if change == 'duplicate': data['fact_inventory'] *= 2
                if change == 'bad_coordinates': data['dim_store'][0]['latitude'] = 'NaN'
                if change == 'future': data['fact_inventory'][0]['collected_date'] = '2999-01-01'
                with self.assertRaises(ValueError): publish(root, 'partner', data)
                self.assertEqual(revision(root), before)
            rows, warnings = load_catalog(root)
            self.assertEqual(len(rows), 1)
            self.assertFalse(warnings)

    def test_publish_failure_keeps_previous_pointer(self):
        with tempfile.TemporaryDirectory() as root:
            publish(root, 'partner', self.tables)
            before = source_directories(root)
            with patch('snapshots.os.replace', side_effect=OSError('simulated disk error')):
                with self.assertRaises(OSError): publish(root, 'partner', self.tables)
            self.assertEqual(source_directories(root), before)

    def test_pointer_cannot_escape_data_directory(self):
        with tempfile.TemporaryDirectory() as root:
            (Path(root) / 'active_bad.json').write_text(json.dumps({'directory': '..'}))
            with self.assertRaises(ValueError): source_directories(root)
