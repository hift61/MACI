"""New inbox entries interrupt cached code before the receiving decision."""
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'enviroment'))
from policy import CodePolicy, HybridPolicy


CODE = 'def decide(obs): return {"type": "move_forward", "distance": 1, "recheck_after": 100}'
REPLY = 'def decide(obs): return {"type": "send_message", "receiver_id": "B", "content": "received", "recheck_after": 100}'


def observation(step, inbox=()):
    return {'self': {'step': step, 'x': float(step), 'y': 0., 'facing': 0.},
            'known_objects': {}, 'visible_objects': [], 'inbox': list(inbox), 'memory': {}, 'walls': []}


class MessageInterruptTests(unittest.TestCase):
    def test_code_policy_interrupt_ignores_review_deadline_and_replan_budget(self):
        policy = CodePolicy('test', 'task', max_replans=0)
        messages = [{'type': 'text', 'from': 'B', 'step': 1, 'content': 'new contact'}]
        with patch.object(policy, '_generate_code', side_effect=[CODE, REPLY]) as generate:
            policy.decide(observation(1))
            self.assertEqual(policy.next_review_step, 101)
            action = policy.decide(observation(2, messages))
            self.assertEqual(action['type'], 'send_message')
            self.assertEqual(generate.call_count, 2)
            self.assertIn('new contact', generate.call_args.args[0])
            self.assertEqual(policy.last_replan['kind'], 'message_received')
            self.assertEqual(policy.last_message_interrupt, {'step': 2, 'count': 1})
            policy.decide(observation(3, messages))
            self.assertEqual(generate.call_count, 2)
            self.assertIsNone(policy.last_message_interrupt)
        policy.reset()
        self.assertEqual(len(policy._new_messages(observation(1, messages))), 1)

    def test_hybrid_coalesces_new_messages_and_does_not_repeat_old_inbox(self):
        policy = HybridPolicy('test', 'task')
        first = {'type': 'text', 'from': 'B', 'step': 1, 'content': 'hello'}
        second = {'type': 'belief', 'from': 'B', 'step': 1, 'subject': 'door', 'claim': True}
        third = {'type': 'request', 'from': 'B', 'step': 3, 'subject': 'status'}
        with patch.object(policy, '_ask_llm', side_effect=[CODE, REPLY, CODE]) as ask:
            policy.decide(observation(1))
            action = policy.decide(observation(2, [first, second]))
            self.assertEqual(action['type'], 'send_message')
            self.assertEqual(ask.call_count, 2)
            self.assertEqual(ask.call_args.args[0]['inbox'], [first, second])
            self.assertEqual(policy.last_message_interrupt['count'], 2)
            policy.decide(observation(3, [first, second]))
            self.assertEqual(ask.call_count, 2)
            policy.decide(observation(4, [first, second, third]))
            self.assertEqual(ask.call_count, 3)
            self.assertEqual(policy.last_message_interrupt['count'], 1)

    def test_first_generation_receives_preexisting_inbox(self):
        policy = CodePolicy('test', 'task', max_replans=0)
        with patch.object(policy, '_generate_code', return_value=REPLY) as generate:
            policy.decide(observation(1, [{'from': 'B', 'content': 'already delivered'}]))
            self.assertIn('already delivered', generate.call_args.args[0])
