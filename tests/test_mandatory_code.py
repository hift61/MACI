"""All benchmark LLM modes execute cached code rather than per-turn JSON replies."""
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import benchmark
from policy import CodePolicy, HybridPolicy, CODE_POLICY_SYSTEM_PROMPT, _generate_code_with_submission_gate
from policy_sandbox import CodeChecks


CODE = 'def decide(obs): return {"type": "noop", "recheck_after": 20}'


def observation(step):
    return {'self': {'step': step, 'x': 0., 'y': 0., 'facing': 0.},
            'inbox': [], 'memory': {}, 'known_objects': {}, 'visible_objects': [], 'walls': []}


def response(code, call_id):
    call = SimpleNamespace(id=call_id, function=SimpleNamespace(
        name='submit_policy_code', arguments=json.dumps({'code': code})))
    message = SimpleNamespace(content=None, tool_calls=[call])
    return SimpleNamespace(choices=[SimpleNamespace(finish_reason='tool_calls', message=message)], usage=None)


class MandatoryCodeTests(unittest.TestCase):
    def test_programmatic_hybrid_cannot_apply_a_direct_json_reply(self):
        policy = HybridPolicy('test', 'task')
        with patch.object(policy, '_ask_llm', return_value='{"type":"move_forward","distance":20}'):
            self.assertEqual(policy.decide(observation(1)), {'type': 'noop'})
        self.assertIn('Code execution is required', policy.last_error)
        self.assertEqual(policy.code_checks.snapshot()['execution_attempts'], 0)

    def test_both_llm_cli_names_require_code(self):
        for kind in ('code', 'hybrid'):
            policy = benchmark.make_policy(kind, 'test', 'task', 'https://example.test/v1', 'test', {}, 15)
            self.assertIs(type(policy), CodePolicy)

    def test_direct_json_is_rejected_then_corrected_before_execution(self):
        client, checks, history = Mock(), CodeChecks(), []
        client.chat.completions.create.side_effect = [
            response('{"type":"move_forward","distance":20}', 'invalid'), response(CODE, 'valid')]
        result = _generate_code_with_submission_gate(client, 'test', CODE_POLICY_SYSTEM_PROMPT,
                                                     'task', 0, 4000, {}, checks, history)
        self.assertEqual(result, CODE)
        validation = [json.loads(m['content']) for m in history if m['role'] == 'tool']
        self.assertFalse(validation[0]['accepted'])
        self.assertIn('direct JSON', validation[0]['error'])
        self.assertTrue(validation[1]['accepted'])
        self.assertEqual(checks.snapshot()['execution_attempts'], 0)

    def test_intentional_waits_reuse_code_until_review_deadline(self):
        policy = CodePolicy('test', 'task')
        with patch.object(policy, '_generate_code', return_value=CODE) as generate:
            for step in range(1, 21):
                self.assertEqual(policy.decide(observation(step))['type'], 'noop')
            self.assertEqual(generate.call_count, 1)
            self.assertIn('Current observation', generate.call_args.args[0])
            self.assertEqual(policy.code_checks.snapshot()['execution_successes'], 20)
            policy.decide(observation(21))
            self.assertEqual(generate.call_count, 2)

    def test_blocked_forward_motion_still_triggers_review(self):
        policy = CodePolicy('test', 'task')
        blocked = 'def decide(obs): return {"type":"move_forward","distance":20}'
        with patch.object(policy, '_generate_code', return_value=blocked) as generate:
            policy.decide(observation(1))
            policy.decide(observation(2))
            self.assertEqual(generate.call_count, 2)
            self.assertIn('blocked', policy.last_replan['reason'])
