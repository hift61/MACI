"""Generated-source compilation and independent runtime counters."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'enviroment'))
from policy_sandbox import CodeChecks, compile_policy_code, run_decide_code
from policy import CodePolicy, _safety_check_error
import benchmark


class PolicyChecksTests(unittest.TestCase):
    def test_compile_failure_never_executes(self):
        checks = CodeChecks()
        with patch('policy_sandbox._run_decide_code') as run:
            result = run_decide_code('return 1', {'self': {'step': 1}}, checks=checks)
        self.assertIsNotNone(result['error'])
        run.assert_not_called()
        self.assertEqual(checks.snapshot()['compile_failures'], 1)
        self.assertEqual(checks.snapshot()['execution_attempts'], 0)

    def test_compilation_does_not_run_source(self):
        checks = CodeChecks()
        self.assertIsNone(compile_policy_code('raise RuntimeError("must not execute")', checks))
        self.assertEqual(checks.snapshot()['compile_successes'], 1)
        self.assertEqual(checks.snapshot()['execution_attempts'], 0)

    def test_runtime_failure_is_separate_from_compile_success(self):
        checks = CodeChecks()
        result = run_decide_code('def decide(observation):\n    return 1 / 0', {'self': {'step': 7}}, checks=checks)
        self.assertIn('ZeroDivisionError', result['error'])
        result = run_decide_code('def decide(observation):\n    return {"type": "noop"}', {'self': {'step': 7}}, checks=checks)
        self.assertIsNone(result['error'])
        self.assertEqual(checks.snapshot(), {'compile_attempts': 2, 'compile_successes': 2, 'compile_failures': 0,
                                           'execution_attempts': 2, 'execution_successes': 1, 'execution_failures': 1})

    def test_submission_is_compiled_and_counted(self):
        checks, events = CodeChecks(), []
        checks.sink = events.append
        self.assertIsNotNone(_safety_check_error('return 1', checks))
        self.assertEqual(events[0]['context'], 'submission')
        self.assertEqual(events[0]['phase'], 'compile')
        self.assertEqual(len(events[0]['code_sha256']), 64)

    def test_benchmark_persists_audit_and_totals(self):
        policies = [CodePolicy('test', 'task'), CodePolicy('test', 'task')]
        for p in policies:
            p._generate_code = lambda *args: 'def decide(observation):\n    return {"type": "noop"}'
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'run.jsonl'
            with patch.object(benchmark, 'make_policy', side_effect=policies), contextlib.redirect_stdout(io.StringIO()):
                benchmark.run_episode('test', '', '', {}, 1, str(path))
            audit = [json.loads(line) for line in path.with_suffix('.code_checks.jsonl').read_text(encoding='utf-8').splitlines()]
            self.assertEqual(len(audit), 4)
            self.assertEqual({e['agent'] for e in audit}, {'A', 'B'})
            self.assertEqual({e['phase'] for e in audit}, {'compile', 'execution'})
            record = json.loads(path.read_text(encoding='utf-8'))
            score = json.loads(path.with_suffix('.score.json').read_text(encoding='utf-8'))
            for agent in record['agents']:
                counts = agent['decision']['code_checks']
                self.assertEqual(counts['execution_attempts'], 1)
                self.assertEqual(counts, score['code_checks'][agent['agent']])


if __name__ == '__main__':
    unittest.main()
