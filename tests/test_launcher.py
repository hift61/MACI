"""Headless GUI integration checks; no paid API requests."""
import os
os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'

import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import launcher


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.app = launcher.Launcher()
        self.app.auto_view = False

    def tearDown(self):
        if self.app.proc:
            self.app.stop()
            self.app.proc.wait(timeout=10)
        launcher.pygame.quit()

    def finish(self):
        deadline = time.monotonic() + 30
        while self.app.proc is not None and time.monotonic() < deadline:
            self.app.poll()
            time.sleep(.02)
        self.assertIsNone(self.app.proc, 'subprocess did not finish')

    def test_all_tabs_render(self):
        for tab in ('맵', '실행', '결과', 'LLM 채점', '디버그'):
            self.app.switch(tab)
            self.app.draw()
            self.assertGreater(len(self.app.widgets), 5)

    def test_generation_options_and_llm_command(self):
        with patch.object(self.app, 'start') as start:
            self.app.reveal = True
            self.app.generate()
            args = start.call_args.args[0]
            self.assertIn('--reveal-positions', args)
            self.assertEqual(args[args.index('--seed') + 1], '42')
            self.app.policy = 'code'
            with patch.object(self.app, 'key_ready', return_value=True):
                self.app.run_episode()
            self.assertIn('--model', start.call_args.args[0])
            self.assertNotIn('--api-key-env', start.call_args.args[0])
        with patch.object(self.app, 'key_ready', return_value=False):
            with self.assertRaises(ValueError):
                self.app.run_episode()

    def test_actual_generate_run_and_results(self):
        with tempfile.TemporaryDirectory(dir=launcher.ROOT) as folder:
            directory = Path(folder)
            source = directory / 'map.json'
            self.app.start(['-m', 'mapgen', '--seed', '42', '--out', str(source)], '맵 생성', source)
            self.finish()
            self.assertTrue(source.is_file())
            self.assertEqual(self.app.path('map'), source)
            result = directory / 'run.jsonl'
            self.app.start(['benchmark.py', '--policy', 'tooluse', '--steps', '3',
                            '--map-file', str(source), '--out', str(result)], '에피소드 실행', result)
            self.finish()
            self.assertTrue(result.with_suffix('.score.json').is_file(), '\n'.join(self.app.logs))
            records = [json.loads(line) for line in result.read_text(encoding='utf-8').splitlines()]
            self.assertEqual(len(records), 3)
            self.assertEqual(self.app.tab, '결과')
            self.assertTrue(any('총점' in line for line in self.app.detail))
            self.assertTrue(any('step 3' in line for line in self.app.detail))
            with patch.object(self.app, 'key_ready', return_value=True), patch.object(self.app, 'start') as start:
                self.app.fields['turns'] = ''
                self.app.fields['agent'] = 'A'
                self.app.judge(True)
                args = start.call_args.args[0]
                self.assertIn('--set-baseline', args)
                self.assertIn('--agent', args)
                self.assertNotIn('--max-turns', args)

    def test_subprocess_failure_visible(self):
        self.app.start(['-c', 'raise RuntimeError("test failure")'], '검증')
        self.finish()
        self.assertIn('실패', self.app.status)
        self.assertTrue(any('test failure' in line for line in self.app.logs))

    def test_stop_and_busy_guard(self):
        self.app.start(['-c', 'import time; time.sleep(60)'], '검증')
        with self.assertRaises(ValueError):
            self.app.start(['-c', 'pass'], '중복 작업')
        self.app.stop()
        self.finish()
        self.assertEqual(self.app.status, '작업 중단됨')

    def test_editor_arguments(self):
        with patch.object(self.app, 'start') as start:
            self.app.editor(True)
            args = start.call_args.args[0]
            self.assertEqual(args[:2], ['-m', 'mapgen.editor'])
            self.assertIn('--out', args)
            self.assertNotIn('--load', args)

    def test_sequence_settings_and_auto_viewer(self):
        self.app.environment = 'sequence_rooms'
        self.app.auto_view = True
        self.app.fields['map'] = 'nonexistent-map.json'
        self.app.fields['resets'] = '2'
        with patch.object(self.app, 'start') as start, patch.object(self.app, 'open_viewer') as view:
            self.app.run_episode()
            args = start.call_args.args[0]
            self.assertIn('--environment', args)
            self.assertIn('sequence_rooms', args)
            self.assertIn('--max-resets', args)
            self.assertNotIn('--map-file', args)
            view.assert_called_once_with(start.call_args.args[2], live=True)
        self.app.fields['presses'] = '6'
        with self.assertRaises(ValueError):
            self.app.run_episode()

    def test_sequence_cli_and_observer_snapshot(self):
        with tempfile.TemporaryDirectory(dir=launcher.ROOT) as folder:
            output = Path(folder) / 'sequence.jsonl'
            self.app.start(['benchmark.py', '--environment', 'sequence_rooms', '--sequence-seed', '7',
                            '--pads-per-room', '4', '--presses-per-room', '2',
                            '--max-resets', '1', '--policy', 'noop', '--steps', '2', '--out', str(output)],
                           '에피소드 실행', output)
            self.finish()
            self.assertTrue(output.is_file(), '\n'.join(self.app.logs))
            records = [json.loads(line) for line in output.read_text(encoding='utf-8').splitlines()]
            self.assertEqual(records[-1]['environment'], 'sequence_rooms')
            self.assertEqual(records[-1]['failure']['reason'], 'turn_limit')
            self.assertEqual(sum(o['type'] == 'number_pad' for o in records[-1]['world']['objects']), 8)
            self.assertTrue(output.with_suffix('.scene.json').is_file())

    def test_debug_toggle_and_live_pipe(self):
        self.app.debug = True
        with patch.object(self.app, 'start') as start:
            self.app.run_episode()
            self.assertIn('--debug', start.call_args.args[0])
            self.assertEqual(self.app.tab, '디버그')
        self.app.start(['-c', 'import time; print("[DEBUG] live log", flush=True); time.sleep(10)'], '로그 검증')
        deadline = time.monotonic()+3
        while not any('[DEBUG] live log' == line for line in self.app.logs) and time.monotonic() < deadline:
            self.app.poll()
            time.sleep(.01)
        self.assertIn('[DEBUG] live log', self.app.logs)
        self.assertIsNotNone(self.app.proc)
        self.assertIsNone(self.app.proc.poll())
        self.app.draw()
        self.assertTrue(self.app._debug_lines)
        self.app.stop()
        self.finish()


if __name__ == '__main__':
    unittest.main()
