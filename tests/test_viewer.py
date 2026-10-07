"""Trace streaming, rendering, and sequence benchmark integration without APIs."""
import os
os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import benchmark
from viewer import TraceReader, Viewer
import pygame
from tests.test_sequence_rooms import TurnTakingPolicy


class ViewerTests(unittest.TestCase):
    def test_partial_utf8_line_waits_and_does_not_duplicate(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'run.jsonl'
            encoded = json.dumps({'step': 1, 'agents': [], 'note': '이동'}, ensure_ascii=False).encode('utf-8')
            split = encoded.index('이'.encode('utf-8')) + 1
            path.write_bytes(encoded[:split])
            reader = TraceReader(path)
            reader.poll()
            self.assertEqual(reader.records, [])
            with path.open('ab') as file:
                file.write(encoded[split:] + b'\n')
            reader.poll()
            reader.poll()
            self.assertEqual(len(reader.records), 1)
            self.assertEqual(reader.records[0]['note'], '이동')

    def test_sequence_clear_and_replay(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'run.jsonl'
            policies = iter([TurnTakingPolicy('A', 'B'), TurnTakingPolicy('B', 'A')])
            with patch.object(benchmark, 'make_policy', side_effect=lambda *a, **k: next(policies)), contextlib.redirect_stdout(io.StringIO()):
                benchmark.run_episode('demo', '', '', {}, 80, str(path), policy_kind='tooluse',
                                      environment_kind='sequence_rooms', sequence_seed=3)
            reader = TraceReader(path)
            reader.poll()
            self.assertTrue(reader.records[-1]['cleared'])
            self.assertTrue(reader.scene)
            self.assertEqual(reader.scene['world']['width'], 400)
            self.assertTrue(any(o['type'] == 'number_pad' for o in reader.scene['world']['objects']))
            self.assertTrue(any(r['messages'] for r in reader.records))
            view = Viewer(path)
            try:
                view.draw()
                view.tick(.25)
                self.assertEqual(view.index, 0)
                self.assertAlmostEqual(view.elapsed, .5)
                view.tick(.25)
                self.assertEqual(view.index, 1)
                view.seek(len(reader.frames()) - 1)
                view.draw()
                Path('artifacts').mkdir(exist_ok=True)
                pygame.image.save(view.screen, 'artifacts/sequence-replay.png')
            finally:
                pygame.quit()

    def test_turn_limit_failure_recorded(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'run.jsonl'
            with contextlib.redirect_stdout(io.StringIO()):
                benchmark.run_episode('demo', '', '', {}, 2, str(path), policy_kind='noop', environment_kind='sequence_rooms')
            reader = TraceReader(path)
            reader.poll()
            self.assertEqual(len(reader.records), 2)
            self.assertEqual(reader.records[-1]['failure']['reason'], 'turn_limit')
            vault = next(o for o in reader.records[-1]['world']['objects'] if o['object_id'] == 'vault')
            self.assertTrue(vault['sealed'])
            self.assertTrue(path.with_suffix('.score.json').exists())

    def test_old_log_positions_render(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'old.jsonl'
            path.write_text(json.dumps({'step': 1, 'agents': [{'agent': 'A', 'position': [40, 40]}]}) + '\n', encoding='utf-8')
            view = Viewer(path)
            try:
                view.draw()
            finally:
                pygame.quit()


if __name__ == '__main__':
    unittest.main()
