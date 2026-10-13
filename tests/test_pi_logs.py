"""Remote (Raspberry Pi) log reader: the remote helper runs here instead of over ssh."""
import os
os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import pi_logs


def local_runner(args):
    """Runs the helper with the local Python, exactly as ssh would run it on the Pi."""
    result = subprocess.run([sys.executable, '-', *args], input=pi_logs.REMOTE_HELPER.encode('utf-8'),
                            capture_output=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode('utf-8', 'replace'))
    return result.stdout


def record(step, cleared=False):
    return json.dumps({'step': step, 'configured_steps': 10, 'cleared': cleared, 'environment': 'map',
                       'controller': 'decentralized', 'agents': [{'agent': 'A', 'model': 'm1'}]})


class PiLogsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.remote = base / 'remote'
        (self.remote / 'trial').mkdir(parents=True)
        done = self.remote / 'trial' / 's01.jsonl'
        done.write_text(record(1) + '\n' + record(2, True) + '\n', encoding='utf-8')
        done.with_suffix('.score.json').write_text(json.dumps(
            {'total': 50, 'team': {'cleared': True, 'clear_step': 2}, 'stopped': None}), encoding='utf-8')
        done.with_suffix('.log').write_text('\n'.join(f'line {i}' for i in range(100)), encoding='utf-8')
        (self.remote / 'trial' / 's01.context_archive.jsonl').write_text('{"big": 1}\n', encoding='utf-8')
        (self.remote / 'trial' / 's01.debug.jsonl').write_text('{}\n', encoding='utf-8')
        self.running = self.remote / 'live.jsonl'
        self.running.write_text(record(1) + '\n', encoding='utf-8')
        self.local = base / 'local'
        self.patch = patch.object(pi_logs, 'LOCAL_DIR', self.local)
        self.patch.start()
        self.client = pi_logs.PiClient('unused', str(self.remote), local_runner)

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def test_lists_runs_in_subfolders_without_sidecar_files(self):
        data = self.client.list_runs()
        runs = {r['path'].replace('\\', '/'): r for r in data['runs']}
        self.assertEqual(set(runs), {'trial/s01.jsonl', 'live.jsonl'})
        done = runs['trial/s01.jsonl']
        self.assertEqual((done['done'], done['cleared'], done['step'], done['total'], done['model']),
                         (True, True, 2, 50, 'm1'))
        self.assertEqual(pi_logs.run_status(done, data['now']), '클리어')
        self.assertEqual(pi_logs.run_status(runs['live.jsonl'], data['now']), '진행 중')
        self.assertEqual(pi_logs.run_status(runs['live.jsonl'], data['now'] + 1000), '멈춤')

    def test_tail_download_and_follow(self):
        self.assertEqual(self.client.tail_log('trial/s01.jsonl', 3), ['line 97', 'line 98', 'line 99'])
        path = self.client.download('trial/s01.jsonl')
        names = sorted(p.name for p in path.parent.iterdir())
        self.assertEqual(names, ['s01.debug.jsonl', 's01.jsonl', 's01.log', 's01.score.json'])
        self.client.download('trial/s01.jsonl', include_context=True)
        self.assertTrue((path.parent / 's01.context_archive.jsonl').is_file())

        live = self.client.download('live.jsonl')
        self.assertEqual(self.client.append_new('live.jsonl'), 0)
        with self.running.open('a', encoding='utf-8') as file:
            file.write(record(2) + '\n')
        self.assertGreater(self.client.append_new('live.jsonl'), 0)
        self.assertEqual([json.loads(l)['step'] for l in live.read_text(encoding='utf-8').splitlines()], [1, 2])

    def test_paths_cannot_escape_either_root(self):
        with self.assertRaises(RuntimeError):
            self.client.tail_log('../outside.jsonl')
        with self.assertRaises(ValueError):
            pi_logs.local_path('../../x.jsonl')

    def test_window_lists_selects_and_shows_the_log(self):
        app = pi_logs.PiLogsApp('unused', str(self.remote), local_runner)
        try:
            app.refresh()
            deadline = time.time() + 30
            while (not app.runs or app.busy) and time.time() < deadline:
                app.poll()
                time.sleep(0.05)
            app.select(next(r['path'] for r in app.runs if r['path'].endswith('s01.jsonl')))
            while (not app.log_lines or app.busy) and time.time() < deadline:
                app.poll()
                time.sleep(0.05)
            app.draw()
            self.assertEqual(len(app.runs), 2)
            self.assertEqual(app.log_lines[-1], 'line 99')

            def unreachable(args):
                raise RuntimeError('ssh: connect timed out')
            app.runner = unreachable
            app.refresh()
            while app.busy and time.time() < deadline:
                app.poll()
                time.sleep(0.05)
            self.assertIn('목록 새로고침 실패', app.status)
            self.assertIn('connect timed out', app.status)
        finally:
            app.pygame.quit()


if __name__ == '__main__':
    unittest.main()
