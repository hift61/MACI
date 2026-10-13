"""API-reported usage drives actual per-agent score deductions."""
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'enviroment'))
from policy import CodePolicy, _create_with_retry
from token_usage import TokenUsage
from blind_code import build_blind_code
from scoring import score_episode


class TokenUsageTests(unittest.TestCase):
    def test_only_output_tokens_reduce_score(self):
        policy = CodePolicy('test', 'task')
        policy.client = Mock()
        policy.client.chat.completions.create.side_effect = [
            SimpleNamespace(choices=[object()], usage=SimpleNamespace(prompt_tokens=400_000, completion_tokens=50_000, total_tokens=450_000)),
            SimpleNamespace(choices=[object()], usage=SimpleNamespace(prompt_tokens=200_000, completion_tokens=2_500, total_tokens=202_500))]
        _create_with_retry(policy.client)
        env, _, objectives = build_blind_code()
        env.agents['A'].set_policy(policy)
        score = score_episode(env, 150, objectives)
        self.assertEqual(score['agents']['A']['token_penalty'], 0)
        _create_with_retry(policy.client)
        score = score_episode(env, 150, objectives)
        self.assertEqual(policy.token_usage['total_tokens'], 652_500)
        self.assertEqual(policy.token_usage['completion_tokens'], 52_500)
        self.assertEqual(policy.token_usage['requests'], 2)
        self.assertEqual(score['agents']['A']['token_penalty'], -2.5)
        self.assertEqual(score['agents']['B']['token_penalty'], 0)
        self.assertEqual(score['total'], -2.5)
        self.assertEqual(score['agents']['A']['items'][-1]['reason'], '과도한 토큰 소비')
        # Repeated scoring reads must not accumulate another deduction.
        self.assertEqual(score_episode(env, 150, objectives)['total'], -2.5)
        policy.reset()
        self.assertEqual(policy.token_usage['total_tokens'], 0)

    def test_missing_usage_is_marked_and_not_guessed(self):
        usage = TokenUsage()
        usage.record(SimpleNamespace(usage=None))
        self.assertEqual(usage.snapshot()['unreported_requests'], 1)
        self.assertEqual(usage.snapshot()['total_tokens'], 0)
        usage.record(SimpleNamespace(usage=SimpleNamespace(prompt_tokens=100, completion_tokens=20)))
        self.assertEqual(usage.snapshot()['total_tokens'], 120)

    def test_absence_notice_survives_hidden_goal(self):
        _, tasks, _ = build_blind_code(reveal_goal=False)
        for text in tasks.values():
            self.assertIn('no clue blocks or display/update blocks', text)
            self.assertIn('No hints, prefix correctness', text)
            self.assertNotIn('50000', text)  # 정보 계약 v2: 비용 규칙은 --disclose-costs일 때만
            self.assertNotIn('Goal:', text)
