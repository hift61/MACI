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
            self.assertEqual(reader.scene['score']['total'], 0)
            final_score = json.loads(path.with_suffix('.score.json').read_text(encoding='utf-8'))
            for key in ('agents', 'team', 'total', 'individual_total'):
                self.assertEqual(reader.records[-1]['score'][key], final_score[key])
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
                self.assertTrue(any('→' in line for line in view.panel_lines(reader.records[-1])))
                Path('artifacts').mkdir(exist_ok=True)
                pygame.image.save(view.screen, 'artifacts/sequence-replay.png')
                view.select_tab('details')
                view.draw()
                self.assertTrue(any('누적 점수 내역' in line for line in view.panel_lines(reader.records[-1])))
            finally:
                pygame.quit()

    def test_live_messages_and_scores_follow_selected_frame(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'run.jsonl'
            def record(step, sender, receiver, content, points):
                return {'step': step, 'agents': [{'agent': 'A', 'position': [40, 40]}],
                        'messages': [{'step': step, 'from': sender, 'receiver_id': receiver,
                                      'type': 'text', 'content': content}],
                        'score': {'total': points, 'individual_total': points,
                                  'team': {'score': 0}, 'agents': {'A': {'score': points, 'items': []}}}}
            first = record(1, 'A', 'B', '먼저 발견했어\n다음 줄도 표시', 3)
            second = record(2, 'B', 'A', '확인했어', 5)
            path.write_text(json.dumps(first, ensure_ascii=False) + '\n', encoding='utf-8')
            view = Viewer(path, live=True)
            try:
                with path.open('a', encoding='utf-8') as file:
                    file.write(json.dumps(second, ensure_ascii=False) + '\n')
                view.reader.poll()
                view.seek(1)
                view.draw()
                lines = view.panel_lines(second)
                self.assertIn('step 2  B → A', lines)
                self.assertIn('다음 줄도 표시', lines)
                self.assertEqual(len(view.reader.messages_through(1)), 2)
                view.seek(0)
                view.draw()
                lines = view.panel_lines(first)
                self.assertNotIn('확인했어', lines)
                self.assertEqual(len(view.reader.messages_through(0)), 1)
                self.assertEqual(view.reader.frames()[view.index]['score']['total'], 3)
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
