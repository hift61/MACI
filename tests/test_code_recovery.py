"""Code execution failures recover without waiting for an LLM on the simulation thread."""
import copy
import sys
import threading
import time
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'enviroment'))
from policy import CodePolicy


def observation():
    return {'self': {'x': 50., 'y': 50., 'facing': 0., 'step': 1,
                     'map_width': 100., 'map_height': 100., 'inventory': []},
            'memory': {'plan': 'keep'}, 'inbox': [], 'walls': [],
            'visible_objects': [], 'known_objects': {}}


class CodeRecoveryTests(unittest.TestCase):
    def policy(self):
        policy = CodePolicy('test', 'test task', max_replans=0)
        policy.generated_code = 'def decide(observation):\n    return 1 / 0'
        return policy

    def test_wait_until_success(self):
        policy = self.policy()
        release, entered = threading.Event(), threading.Event()
        def generate(prompt=None):
            entered.set()
            release.wait(5)
            return 'def decide(observation):\n    return {"type": "move", "dx": 5, "dy": 0}'
        policy._generate_code = generate
        obs = observation()
        before = copy.deepcopy(obs)
        actions = []
        thread = threading.Thread(target=lambda: actions.append(policy.decide(obs)))
        thread.start()
        try:
            self.assertTrue(entered.wait(2))
            self.assertTrue(thread.is_alive())
            self.assertEqual(actions, [])
            self.assertEqual(obs, before)
            release.set()
            thread.join(4)
            self.assertFalse(thread.is_alive())
            self.assertEqual(actions, [{'type': 'move', 'dx': 5, 'dy': 0}])
            self.assertIsNone(policy.last_error)
            self.assertEqual(policy.last_recovery['status'], 'recovered')
            self.assertEqual(obs, before)
        finally:
            release.set()
            thread.join(5)

    def test_retries_api_and_code_errors_without_consuming_steps(self):
        from unittest.mock import patch
        from time import sleep
        policy = self.policy()
        answers = iter([RuntimeError('provider unavailable'),
                        'def decide(observation):\n    return 1 / 0',
                        'def decide(observation):\n    return {"type": "noop"}'])
        calls = []
        def generate(prompt=None):
            calls.append(prompt)
            answer = next(answers)
            if isinstance(answer, Exception):
                raise answer
            return answer
        policy._generate_code = generate
        obs = observation()
        with patch('policy.time.sleep', side_effect=lambda _: sleep(.01)):
            action = policy.decide(obs)
        self.assertEqual(action, {'type': 'noop'})
        self.assertEqual(len(calls), 3)
        self.assertEqual(obs['self']['step'], 1)
        self.assertIsNone(policy.last_error)
        self.assertEqual(policy.last_recovery['attempts'], 3)


if __name__ == '__main__':
    unittest.main()
