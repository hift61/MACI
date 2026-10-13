"""No secret oracle and mandatory participation by both agents."""
import copy
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'enviroment'))
from blind_code import build_blind_code


def enter(env, aid, pad_id):
    pad = env.objects[pad_id]
    env.agents[aid].x, env.agents[aid].y = pad['x'], pad['y'] + 15
    env._pads_inside[aid] = set()
    env.turn_agent(aid, 270)
    env.apply_action(aid, {'type': 'move_forward', 'distance': 10})


class BlindCodeTests(unittest.TestCase):
    def test_no_clues_displays_or_seed_based_secret(self):
        with patch('blind_code.secrets.choice', side_effect=lambda pads: pads[0]):
            first, tasks, _ = build_blind_code(seed=7)
        with patch('blind_code.secrets.choice', side_effect=lambda pads: pads[-1]):
            second, _, _ = build_blind_code(seed=7)
        self.assertEqual(first.objects, second.objects)
        self.assertNotEqual(first.sequence, second.sequence)
        self.assertEqual(len(first.sequence), 10)
        self.assertEqual([first.objects[p]['room'] for p in first.sequence].count('A'), 5)
        self.assertEqual([first.objects[p]['room'] for p in first.sequence].count('B'), 5)
        self.assertFalse(any(o['type'] in ('clue', 'display') for o in first.objects.values()))
        for aid in first.agents:
            self.assertEqual(first.get_observation(aid), second.get_observation(aid))
            self.assertIn('no clue blocks or display/update blocks', tasks[aid])
            self.assertNotIn('output token', tasks[aid])  # 정보 계약 v2: 비용 규칙은 기본으로 숨김

    def test_secret_changes_do_not_change_partial_observations(self):
        first, _, _ = build_blind_code()
        second = copy.deepcopy(first)
        pad = first.sequence[0]
        alternative = next(p for p in first.objects if first.objects[p]['type'] == 'number_pad' and p != pad)
        second.sequence[0] = alternative
        aid = first.objects[pad]['room']
        enter(first, aid, pad)
        enter(second, aid, pad)
        for agent in first.agents:
            self.assertEqual(first.get_observation(agent), second.get_observation(agent))
        self.assertFalse(any(e['type'] in ('number_accepted', 'sequence_reset')
                             for e in first.event_log.entries + second.event_log.entries))

    def test_correct_cooperative_code_unlocks_only_after_ten_digits(self):
        env, _, _ = build_blind_code()
        for i, pad_id in enumerate(env.sequence):
            enter(env, env.objects[pad_id]['room'], pad_id)
            self.assertEqual(env.objects['vault']['locked'], i < 9)
        self.assertTrue(env.solved)
        self.assertEqual(set(env._contributors), {'A', 'B'})

    def test_solo_attempt_and_cross_room_input_cannot_clear(self):
        env, _, _ = build_blind_code()
        own = next(p for p, o in env.objects.items() if o['type'] == 'number_pad' and o['room'] == 'A')
        remote = next(p for p, o in env.objects.items() if o['type'] == 'number_pad' and o['room'] == 'B')
        env.press_number_pad('A', remote, contact=True)
        self.assertEqual(env.submitted, [])
        # Even a malformed all-A answer cannot defeat the participation rule.
        env.set_sequence([own] * 10)
        for _ in range(10):
            enter(env, 'A', own)
        self.assertFalse(env.solved)
        self.assertIsNone(env.failure)
        self.assertEqual(env.resets, 1)
        self.assertTrue(env.objects['vault']['locked'])
        self.assertFalse(env.objects['vault'].get('sealed', False))

    def test_wrong_full_code_has_no_prefix_feedback_and_allows_retry(self):
        env, _, _ = build_blind_code()
        attempt = list(env.sequence)
        attempt[-1] = next(p for p, o in env.objects.items()
                           if o['type'] == 'number_pad' and o['room'] == env.objects[attempt[-1]]['room']
                           and p != attempt[-1])
        for i, pad in enumerate(attempt):
            enter(env, env.objects[pad]['room'], pad)
            if i < 9:
                self.assertIsNone(env.failure)
        self.assertIsNone(env.failure)
        self.assertEqual(env.resets, 1)
        self.assertEqual(env.submitted, [])
        self.assertEqual(env.progress, 0)
        for aid, agent in env.agents.items():
            self.assertEqual((agent.x, agent.y, agent.facing), env._initial_agent_states[aid])
        for pad in env.sequence:
            enter(env, env.objects[pad]['room'], pad)
        self.assertTrue(env.solved)

    def test_simultaneous_inputs_restart_and_apply_penalty_without_losing_context(self):
        from policy import CodePolicy
        from scoring import score_episode
        env, _, objectives = build_blind_code()
        original = list(env.sequence)
        for aid in env.agents:
            policy = CodePolicy('test', 'task')
            policy.generated_code = 'def decide(obs): return {"type": "noop"}'
            policy.conversation_history.append({'role': 'user', 'content': 'keep this context'})
            env.agents[aid].set_policy(policy)
            env.agents[aid].memory = {'old_plan': True}
        contacts = [(aid, next(p for p, o in env.objects.items()
                              if o['type'] == 'number_pad' and o['room'] == aid)) for aid in env.agents]
        env._resolve_contacts(contacts)
        self.assertIsNone(env.failure)
        self.assertEqual(env.resets, 1)
        self.assertEqual(env.sequence, original)
        score = score_episode(env, 150, objectives)
        for aid in env.agents:
            agent = env.agents[aid]
            self.assertEqual(agent.memory, {})
            self.assertIsNone(agent.policy.generated_code)
            self.assertEqual(agent.policy.conversation_history[-1]['content'], 'keep this context')
            self.assertEqual(score['agents'][aid]['score'], -3)

    def test_local_endpoint_does_not_require_cloud_key(self):
        from benchmark import is_local_endpoint
        self.assertTrue(is_local_endpoint('http://127.0.0.1:8080/v1'))
        self.assertFalse(is_local_endpoint('https://openrouter.ai/api/v1'))
