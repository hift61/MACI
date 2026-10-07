"""Per-agent context survives regeneration, validation errors and provider fallback."""
import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'enviroment'))
from policy import CodePolicy


def response(code, tool=True, token='submit-1'):
    calls = [NS(id=token, function=NS(name='submit_policy_code', arguments=json.dumps({'code': code})))] if tool else []
    return NS(choices=[NS(finish_reason='stop', message=NS(content=None if tool else code, tool_calls=calls))])


class ContextTests(unittest.TestCase):
    def test_prior_code_steps_and_validation_errors_reach_next_request(self):
        policy = CodePolicy('test', 'agent A private task')
        good = 'def decide(obs):\n    return {"type": "noop"}'
        requests = []
        answers = iter([response(good, token='first'), response('def decide(:', token='bad'), response(good, token='fixed')])
        def create(client, **kwargs):
            requests.append(copy.deepcopy(kwargs['messages']))
            return next(answers)
        with patch('policy._create_with_retry', side_effect=create):
            policy._generate_code()
            policy.remember_step({'self': {'step': 1}, 'visible_objects': [{'object_id': 'clue_A'}]},
                                 {'type': 'noop'}, {'self': {'step': 1}})
            policy._generate_code('Repair after runtime failure')
        prior_codes = [json.loads(tc['function']['arguments'])['code'] for message in requests[1]
                       for tc in message.get('tool_calls', [])]
        self.assertIn(good, prior_codes)
        self.assertTrue(any('Simulation step result' in (m.get('content') or '') for m in requests[1]))
        tool_results = [json.loads(m['content']) for m in requests[2] if m['role'] == 'tool']
        self.assertTrue(any(not result['accepted'] for result in tool_results))
        self.assertEqual(sum(m['role'] == 'system' for m in policy.conversation_history), 1)
        self.assertEqual(policy.code_checks.snapshot()['compile_failures'], 1)

    def test_agents_are_isolated_and_reset_clears_context(self):
        a, b = CodePolicy('test', 'task A'), CodePolicy('test', 'task B')
        a.conversation_history.append({'role': 'user', 'content': 'A private clue'})
        self.assertEqual(b.conversation_history, [])
        a.reset()
        self.assertEqual(a.conversation_history, [])

    def test_toolless_fallback_keeps_prior_conversation(self):
        policy = CodePolicy('test', 'task')
        good = 'def decide(obs):\n    return {"type": "noop"}'
        requests = []
        answers = iter([RuntimeError('tools unsupported'), response(good, tool=False), response(good)])
        def create(client, **kwargs):
            requests.append(copy.deepcopy(kwargs['messages']))
            answer = next(answers)
            if isinstance(answer, Exception):
                raise answer
            return answer
        with patch('policy._create_with_retry', side_effect=create):
            policy._generate_code()
            policy._generate_code('next request')
        self.assertTrue(any(m['role'] == 'assistant' and m['content'] == good for m in requests[2]))

    def test_environment_remembers_only_own_observations(self):
        from sequence_rooms import build_sequence_rooms
        env, _, _ = build_sequence_rooms(seed=3)
        policies = {}
        for aid in ('A', 'B'):
            p = CodePolicy('test', 'task')
            p.generated_code = 'def decide(obs): return {"type": "noop"}'
            p.conversation_history.append({'role': 'system', 'content': 'test'})
            env.agents[aid].set_policy(p)
            policies[aid] = p
        env.step()
        for aid, other in (('A', 'B'), ('B', 'A')):
            feedback = policies[aid].conversation_history[-1]['content']
            self.assertTrue(feedback.startswith('Simulation step result:'))
            data = json.loads(feedback.split('\n', 1)[1])
            visible = [o['object_id'] for o in data['next_observation']['visible_objects']]
            self.assertIn('clue_' + aid, visible)
            self.assertNotIn('clue_' + other, visible)


if __name__ == '__main__':
    unittest.main()
