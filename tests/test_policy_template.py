"""The supplied layout must work inside the real policy sandbox."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'enviroment'))
from policy import POLICY_LAYOUT, CODE_POLICY_SYSTEM_PROMPT, CODE_STEP_SYSTEM_PROMPT, HYBRID_POLICY_SYSTEM_PROMPT
from policy_sandbox import run_decide_code


class PolicyTemplateTests(unittest.TestCase):
    def observation(self):
        return {'self': {'x': 10., 'y': 10., 'step': 1}, 'memory': {'previous': True},
                'known_objects': {'goal': {'object_id': 'goal', 'x': 90., 'y': 10.}},
                'visible_objects': [], 'walls': [], 'inbox': []}

    def filled(self, body):
        return POLICY_LAYOUT.replace('    return finish()\n    # DECISION END', body + '\n    # DECISION END')

    def test_base_layout_returns_memory_without_mutating_observation(self):
        obs = self.observation()
        result = run_decide_code(POLICY_LAYOUT, obs)
        self.assertIsNone(result['error'])
        self.assertEqual(result['action'], {'type': 'noop', 'memory': {'previous': True}})

    def test_movement_uses_remembered_goal_and_preserves_memory(self):
        code = self.filled('    target = find_object("goal")\n    memory["phase"] = "approach"\n    return move_toward(target["x"], target["y"])')
        result = run_decide_code(code, self.observation())
        self.assertIsNone(result['error'])
        self.assertEqual(result['action']['dx'], 20.)
        self.assertEqual(result['action']['dy'], 0.)
        self.assertEqual(result['action']['memory'], {'previous': True, 'phase': 'approach'})

    def test_message_and_arrival_helpers(self):
        result = run_decide_code(self.filled('    return send_message("B", "ready")'), self.observation())
        self.assertEqual(result['action'], {'type': 'send_message', 'receiver_id': 'B', 'content': 'ready', 'memory': {'previous': True}})
        result = run_decide_code(self.filled('    return move_toward(x, y)'), self.observation())
        self.assertIsNone(result['error'])
        self.assertEqual(result['action']['type'], 'noop')

    def test_all_code_prompts_supply_same_layout(self):
        for prompt in (CODE_POLICY_SYSTEM_PROMPT, CODE_STEP_SYSTEM_PROMPT, HYBRID_POLICY_SYSTEM_PROMPT):
            self.assertIn(POLICY_LAYOUT, prompt)
            self.assertIn('DECISION START/END', prompt)


if __name__ == '__main__':
    unittest.main()
