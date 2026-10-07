"""Debug output must reach disk before a blocked simulation step completes."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import benchmark
from policy import CodePolicy


class DebugTests(unittest.TestCase):
    def test_debug_events_during_repair_wait(self):
        entered, release = threading.Event(), threading.Event()
        policies = [CodePolicy('test', 'task'), CodePolicy('test', 'task')]
        policies[0].generated_code = 'def decide(observation):\n    return 1 / 0'
        policies[1].generated_code = 'def decide(observation):\n    return {"type": "noop"}'

        def generate(*args):
            entered.set()
            release.wait(5)
            return 'def decide(observation):\n    return {"type": "noop"}'

        policies[0]._generate_code = generate
        errors = []
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'run.jsonl'
            def run():
                try:
                    benchmark.run_episode('test', '', '', {}, 1, str(path), debug=True)
                except Exception as exc:
                    errors.append(exc)
            with patch.object(benchmark, 'make_policy', side_effect=policies), contextlib.redirect_stdout(io.StringIO()):
                thread = threading.Thread(target=run)
                thread.start()
                try:
                    self.assertTrue(entered.wait(3))
                    self.assertTrue(thread.is_alive())
                    events = [json.loads(s) for s in path.with_suffix('.debug.jsonl').read_text(encoding='utf-8').splitlines()]
                    self.assertTrue(any(e['event'] == 'recovery_wait_started' for e in events))
                    self.assertTrue(any(e['event'] == 'code_check' and not e['check']['success'] for e in events))
                    self.assertEqual(path.read_text(encoding='utf-8'), '')
                finally:
                    release.set()
                    thread.join(5)
            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])
            events = [json.loads(s) for s in path.with_suffix('.debug.jsonl').read_text(encoding='utf-8').splitlines()]
            self.assertEqual(events[-1]['event'], 'episode_finished')
            self.assertTrue(any(e['event'] == 'agent_action' for e in events))

    def test_generation_request_lifecycle(self):
        policy = CodePolicy('test', 'task')
        events = []
        policy.debug_sink = lambda event, details: events.append((event, details))
        with patch('policy._generate_code_with_submission_gate', return_value='def decide(obs): return {"type": "noop"}'):
            policy._generate_code()
        self.assertEqual([e[0] for e in events], ['llm_request_started', 'code_generated'])


if __name__ == '__main__':
    unittest.main()
