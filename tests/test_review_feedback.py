"""Review/feedback fixes: keep_current_code offered when the review text asks for it, tool-call failures and
rejected submissions counted, specific no-effect reasons, and stall metrics."""
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'enviroment'))

from mapgen.builder import build_environment  # noqa: E402
from policy import CodePolicy, _generate_code_with_submission_gate  # noqa: E402
from policy_sandbox import CodeChecks  # noqa: E402
from scenarios import load  # noqa: E402

CODE = 'def decide(o): return {"type": "noop", "recheck_after": 1}'


def call(name, arguments, call_id='c1'):
    return SimpleNamespace(id=call_id, function=SimpleNamespace(name=name, arguments=json.dumps(arguments)))


def reply(*calls):
    message = SimpleNamespace(content=None, tool_calls=list(calls), model_extra={})
    return SimpleNamespace(choices=[SimpleNamespace(finish_reason='tool_calls', message=message)], usage=None)


class KeepOnScheduledReviewTests(unittest.TestCase):
    def test_interval_review_offers_keep_and_keeping_works(self):
        policy = CodePolicy('test', 'task')
        policy.client = Mock()
        policy.client.chat.completions.create.return_value = reply(call('keep_current_code', {'reason': 'fine'}))
        observation = {'self': {'step': 1, 'x': 0., 'y': 0., 'facing': 0.}, 'inbox': [], 'memory': {},
                       'known_objects': {}, 'visible_objects': [], 'walls': []}
        with patch.object(policy, '_generate_code', wraps=policy._generate_code) as generate:
            policy.generated_code = CODE
            policy._next_review_step = 1
            policy.decide(observation)
        self.assertTrue(generate.call_args.kwargs.get('allow_keep'))
        tools = [t['function']['name'] for t in policy.client.chat.completions.create.call_args.kwargs['tools']]
        self.assertIn('keep_current_code', tools)
        self.assertEqual(policy.generated_code, CODE)
        self.assertTrue(policy.last_replan['kept'])


class FailureCountingTests(unittest.TestCase):
    def test_unavailable_tool_and_rejected_import_are_counted_and_explained(self):
        client, checks, history = Mock(), CodeChecks(), []
        client.chat.completions.create.side_effect = [
            reply(call('keep_current_code', {})),
            reply(call('submit_policy_code', {'code': 'import os\ndef decide(o): return {"type": "noop"}'})),
            reply(call('submit_policy_code', {'code': CODE})),
        ]
        code = _generate_code_with_submission_gate(client, 'm', 'sys', 'task', 0.0, 100, {}, checks=checks,
                                                   history=history)
        self.assertEqual(code, CODE)
        counts = checks.snapshot()
        self.assertEqual((counts['tool_call_failures'], counts['submission_rejections']), (1, 1))
        unavailable = json.loads(next(m['content'] for m in history if m['role'] == 'tool'))
        self.assertIn('not available in this call', unavailable['error'])
        self.assertIn('submit_policy_code', unavailable['error'])


class NoEffectReasonTests(unittest.TestCase):
    def setUp(self):
        self.env, _, _ = build_environment(load('s03_split_experiment').build())
        self.agent = self.env.agents['A']

    def result(self, action):
        self.env.apply_action('A', action)
        return self.env.get_observation('A')['last_action_result']

    def test_reasons_name_the_actual_cause(self):
        lever = next(o for o in self.env.objects.values() if o['type'] == 'lever')
        self.agent.x, self.agent.y = lever['x'] + 60, lever['y']
        far = self.result({'type': 'pull_lever', 'lever_id': lever['object_id']})
        self.assertEqual(far['code'], 'out_of_range')
        self.assertIn('60.0 units away', far['reason'])
        self.assertEqual(self.result({'type': 'pull_lever', 'lever_id': 'nope'})['code'], 'missing_target')
        self.assertEqual(self.result({'type': 'drop', 'object_id': 'nope'})['code'], 'not_carried')
        door = next(o for o in self.env.objects.values() if o['type'] == 'door')
        self.agent.x, self.agent.y = door['x'], door['y'] - 20
        self.assertEqual(self.result({'type': 'pull_lever', 'lever_id': door['object_id']})['code'],
                         'wrong_target_type')

    def test_cooldown_is_reported(self):
        lever = next(o for o in self.env.objects.values() if o['type'] == 'lever' and 'cooldown' in o)
        self.agent.x, self.agent.y = lever['x'], lever['y'] + 5
        self.assertEqual(self.result({'type': 'pull_lever', 'lever_id': lever['object_id']})['status'], 'ok')
        cooling = self.result({'type': 'pull_lever', 'lever_id': lever['object_id']})
        self.assertEqual(cooling['code'], 'cooldown')


class ProgressStatusTests(unittest.TestCase):
    def test_stall_metrics_count_steps_and_repeated_actions(self):
        env, _, _ = build_environment(load('s03_split_experiment').build())
        for step in range(1, 6):
            env.step_count = step
            env.apply_action('A', {'type': 'turn', 'angle': 0})
        status = env.progress_status('A')
        self.assertEqual(status['same_action_streak'], 5)
        self.assertEqual(status['steps_since_progress'], 5)
        lever = next(o for o in env.objects.values() if o['type'] == 'lever')
        env.agents['A'].x, env.agents['A'].y = lever['x'], lever['y'] + 5
        env.step_count = 6
        env.apply_action('A', {'type': 'pull_lever', 'lever_id': lever['object_id']})
        status = env.progress_status('A')
        self.assertEqual((status['steps_since_progress'], status['same_action_streak']), (0, 1))


if __name__ == '__main__':
    unittest.main()
