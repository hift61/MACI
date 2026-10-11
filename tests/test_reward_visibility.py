"""Numeric score visibility changes neither puzzles nor correctness feedback."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import benchmark
from types import SimpleNamespace
from unittest.mock import Mock
from policy import _create_with_retry
from curriculum import build_curriculum


class RewardVisibilityTests(unittest.TestCase):
    def test_http_success_with_provider_error_is_reported_correctly(self):
        client = Mock()
        client.chat.completions.create.return_value = SimpleNamespace(
            choices=None, usage=None, model_extra={'error': {
                'message': 'Your input exceeds the context window', 'code': 400,
                'metadata': {'provider_code': 'context_length_exceeded'}}})
        with self.assertRaisesRegex(ValueError, 'context_length_exceeded'):
            _create_with_retry(client)
        client.chat.completions.create.assert_called_once()
    def test_reward_copy_does_not_allow_score_mutation(self):
        env, _, _ = build_curriculum()
        state = {'individual_score': 2, 'team_score': 0, 'total_score': 2}
        env.reward_provider = lambda aid: state
        obs = env.get_observation('A')
        obs['reward']['individual_score'] = 999
        self.assertEqual(state['individual_score'], 2)

    def test_identical_seed_and_feedback_with_only_numeric_scores_toggled(self):
        with tempfile.TemporaryDirectory() as folder:
            runs = []
            observations = []
            for visible in (False, True):
                captured = []
                class CapturePolicy:
                    def decide(self, observation):
                        captured.append(observation)
                        return {'type': 'noop'}
                path = Path(folder) / f'{visible}.jsonl'
                with contextlib.redirect_stdout(io.StringIO()), patch.object(
                        benchmark, 'make_policy', side_effect=lambda *a, **k: CapturePolicy()):
                    benchmark.run_episode('demo', '', '', {}, 2, str(path),
                                          policy_kind='noop', environment_kind='curriculum',
                                          reward_visible=visible)
                runs.append([json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()])
                observations.append(captured)
            for hidden, visible in zip(*runs):
                self.assertEqual(hidden['world'], visible['world'])
                self.assertEqual(hidden['score'], visible['score'])
            first = sorted(observations[0], key=lambda o: (o['self']['step'], o['self']['x']))
            second = sorted(observations[1], key=lambda o: (o['self']['step'], o['self']['x']))
            for a, b in zip(first, second):
                self.assertNotIn('reward', a)
                self.assertIn('reward', b)
                self.assertEqual(a, {k: v for k, v in b.items() if k != 'reward'})
