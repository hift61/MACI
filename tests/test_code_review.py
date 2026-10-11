"""Code-selected review deadlines must not slide with repeated executions."""
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'enviroment'))
from policy import CodePolicy, HybridPolicy, POLICY_LAYOUT
from policy_sandbox import run_decide_code


CODE = 'def decide(obs): return {"type": "move_forward", "distance": 1, "recheck_after": 3}'


def observation(step):
    return {'self': {'step': step, 'x': float(step), 'y': 0., 'facing': 0.},
            'known_objects': {}, 'visible_objects': [], 'inbox': [], 'memory': {}, 'walls': []}


class CodeReviewTests(unittest.TestCase):
    def test_code_review_uses_current_state_and_can_keep_identical_code(self):
        policy = CodePolicy('test', 'task', max_replans=0)
        with patch.object(policy, '_generate_code', return_value=CODE) as generate:
            for step in range(1, 4):
                policy.decide(observation(step))
                self.assertEqual(policy.next_review_step, 4)
            self.assertEqual(generate.call_count, 1)
            policy.decide(observation(4))
            self.assertEqual(generate.call_count, 2)
            self.assertIn('"step": 4', generate.call_args.args[0])
            self.assertEqual(policy.last_replan['kind'], 'scheduled_review')
            self.assertEqual(policy.next_review_step, 7)
            for step in range(5, 7):
                policy.decide(observation(step))
            policy.decide(observation(7))
            self.assertEqual(generate.call_count, 3)
            self.assertEqual(policy.code_turns, 7)
        policy.reset()
        self.assertIsNone(policy.next_review_step)

    def test_hybrid_reviews_before_deadline_execution(self):
        policy = HybridPolicy('test', 'task')
        with patch.object(policy, '_ask_llm', return_value=CODE) as ask:
            for step in range(1, 4):
                policy.decide(observation(step))
            self.assertEqual(ask.call_count, 1)
            policy.decide(observation(4))
            self.assertEqual(ask.call_count, 2)
            self.assertEqual(ask.call_args.args[0]['self']['step'], 4)
            self.assertEqual(policy.next_review_step, 7)
            self.assertEqual(policy.code_turns, 4)

    def test_scaffold_allows_code_to_choose_interval(self):
        code = POLICY_LAYOUT.replace('    return finish()\n    # DECISION END',
                                     '    recheck_after = 2\n    return finish()\n    # DECISION END')
        result = run_decide_code(code, observation(1))
        self.assertIsNone(result['error'])
        self.assertEqual(result['action']['recheck_after'], 2)

    def test_invalid_interval_does_not_create_deadline(self):
        for interval in (True, 0, -1, 2.5, '3'):
            policy = CodePolicy('test', 'task')
            policy._schedule_review({'recheck_after': interval}, observation(1))
            self.assertIsNone(policy.next_review_step)
