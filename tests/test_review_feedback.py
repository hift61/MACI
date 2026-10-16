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
            reply(call('teleport', {})),
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

    def test_events_outside_own_action_count_as_progress_and_discovery(self):
        env, _, _ = build_environment(load('s03_split_experiment').build())
        env.step_count = 7
        env._log('object_seen', ['B'], object_id='x', object_type='lever')
        env._log('level_completed', ['A', 'B'], level=1)
        env.step_count = 10
        status = env.progress_status('B')
        self.assertEqual((status['steps_since_progress'], status['steps_since_discovery']), (3, 3))


if __name__ == '__main__':
    unittest.main()


class PromptCacheTests(unittest.TestCase):
    def test_tool_list_is_the_same_whether_or_not_keep_is_allowed(self):
        tool_sets = []
        for allow_keep in (False, True):
            client = Mock()
            client.chat.completions.create.return_value = reply(call('submit_policy_code', {'code': CODE}))
            _generate_code_with_submission_gate(client, 'm', 'sys', 'task', 0.0, 100, {}, history=[],
                                                allow_keep=allow_keep)
            tool_sets.append([t['function']['name'] for t in client.chat.completions.create.call_args.kwargs['tools']])
        self.assertEqual(tool_sets[0], tool_sets[1])

    def test_keep_is_refused_with_a_reason_when_there_is_no_code(self):
        client, checks, history = Mock(), CodeChecks(), []
        client.chat.completions.create.side_effect = [reply(call('keep_current_code', {})),
                                                      reply(call('submit_policy_code', {'code': CODE}))]
        self.assertEqual(_generate_code_with_submission_gate(client, 'm', 'sys', 'task', 0.0, 100, {},
                                                             checks=checks, history=history), CODE)
        refusal = json.loads(next(m['content'] for m in history if m['role'] == 'tool'))
        self.assertFalse(refusal['kept'])
        self.assertEqual(checks.snapshot()['tool_call_failures'], 1)

    def test_anthropic_requests_get_cache_marks_and_others_are_unchanged(self):
        from policy import _cache_marked
        messages = [{'role': 'system', 'content': 'rules'}, {'role': 'user', 'content': 'task'},
                    {'role': 'assistant', 'content': None, 'tool_calls': []},
                    {'role': 'user', 'content': 'Context management status (advisory):\n{}'}]
        self.assertIs(_cache_marked(messages, 'openai/gpt-6-luna'), messages)
        marked = _cache_marked(messages, 'anthropic/claude-haiku-5.5')
        self.assertEqual(marked[0]['content'][0]['cache_control'], {'type': 'ephemeral'})
        self.assertEqual(marked[1]['content'][0]['text'], 'task')  # last stable message before the status line
        self.assertIsInstance(marked[3]['content'], str)  # the changing status line is not cached
        self.assertEqual(messages[0]['content'], 'rules')  # caller's history untouched


class CommunicationHelperTests(unittest.TestCase):
    def test_template_offers_a_helper_for_every_communication_action(self):
        from policy import POLICY_LAYOUT
        for name in ('send_message', 'share_belief', 'request_info', 'confirm', 'claim_role', 'claim_task',
                     'issue_command'):
            self.assertIn(f'def {name}(', POLICY_LAYOUT)

    def test_helpers_produce_actions_the_environment_delivers(self):
        from policy import POLICY_LAYOUT
        from policy_sandbox import run_decide_code
        env, _, _ = build_environment(load('s03_split_experiment').build())
        calls = {'share_belief': "share_belief('B', 'L1', 'opens G2')", 'request_info': "request_info('B', 'L4')",
                 'confirm': "confirm('B', 'L1', True)", 'claim_role': "claim_role('scout')",
                 'claim_task': "claim_task('west levers')", 'issue_command': "issue_command('B', {'type': 'noop'})"}
        for kind, call_text in calls.items():
            code = POLICY_LAYOUT.replace('    return finish()\n    # DECISION END', f'    return {call_text}\n    # DECISION END')
            result = run_decide_code(code, env.get_observation('A'))
            self.assertIsNone(result['error'], kind)
            env.apply_action('A', result['action'])
            self.assertEqual(env.agents['B'].inbox[-1]['type'],
                             {'share_belief': 'belief', 'request_info': 'request', 'confirm': 'confirm',
                              'claim_role': 'role_claim', 'claim_task': 'task_claim', 'issue_command': 'command'}[kind])
