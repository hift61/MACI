"""Generated code reuse has no turn cap; accounting still records usage."""
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'enviroment'))
from policy import CodePolicy, HybridPolicy, LiveCodePolicy
from enviroment import Environment
from agent import Agent

CODE = 'def decide(obs): return {"type": "move_forward", "distance": 1}'


def observation(step):
    return {'self': {'step': step, 'x': float(step), 'y': 0., 'facing': 0.},
            'known_objects': {}, 'visible_objects': [], 'inbox': [], 'memory': {}, 'walls': []}


class CodeReuseTests(unittest.TestCase):
    def test_code_policy_reuses_code_beyond_three_turns(self):
        policy = CodePolicy('test', 'task', max_replans=0)
        with patch.object(policy, '_generate_code', return_value=CODE) as generate:
            for step in range(1, 9):
                self.assertEqual(policy.decide(observation(step))['type'], 'move_forward')
            self.assertEqual(generate.call_count, 1)
        self.assertEqual(policy.code_turns, 8)
        self.assertEqual(policy.code_checks.snapshot()['execution_attempts'], 8)
        policy.reset()
        self.assertEqual(policy.code_turns, 0)

    def test_hybrid_reuses_code_beyond_three_turns(self):
        policy = HybridPolicy('test', 'task')
        with patch.object(policy, '_ask_llm', return_value=CODE) as ask:
            for step in range(1, 9):
                self.assertEqual(policy.decide(observation(step))['type'], 'move_forward')
            self.assertEqual(ask.call_count, 1)
        self.assertEqual(policy.code_turns, 8)

    def test_live_can_execute_identical_responses_beyond_three_turns(self):
        policy = LiveCodePolicy('test', 'task')
        with patch.object(policy, '_generate_code', return_value=CODE):
            for step in range(1, 9):
                self.assertEqual(policy.decide(observation(step))['type'], 'move_forward')
        self.assertIsNone(policy.last_error)
        self.assertEqual(policy.code_turns, 8)

    def test_default_view_reaches_200_but_still_respects_walls_and_angle(self):
        wall = SimpleNamespace(x=100., y=100., width=10., height=120.)
        env = Environment(SimpleNamespace(map_width=500., map_height=500., walls=[wall]))
        agent = env.add_agent('A', 10., 250., facing=0.)
        self.assertEqual(agent.view_radius, 200.)
        self.assertEqual(Agent('B', 0., 0.).view_radius, 200.)
        env.add_object('far_visible', 160., 250.)
        env.add_object('too_far', 211., 250.)
        env.add_object('behind', 0., 250.)
        env.add_object('occluded', 150., 180.)
        visible = {o['object_id'] for o in env.get_observation('A')['visible_objects']}
        self.assertIn('far_visible', visible)
        self.assertNotIn('too_far', visible)
        self.assertNotIn('behind', visible)
        self.assertNotIn('occluded', visible)


if __name__ == '__main__':
    unittest.main()
