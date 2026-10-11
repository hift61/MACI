"""Progression, learning preservation, and discovery without the answer key."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import benchmark
from curriculum import build_curriculum
from scoring import score_episode
from tests.test_blind_code import enter


class CurriculumTests(unittest.TestCase):
    def test_feedback_and_shared_observations_allow_discovery(self):
        # A test controller exchanges each room's observations through messages.
        # It discovers prefixes through contact feedback, without reading sequence.
        for seed in range(5):
            env, _, objectives = build_curriculum(seed)
            inputs = 0
            while not env.solved:
                level = env.level
                candidates = []
                for aid in env.agents:
                    pads = [o['object_id'] for o in env.get_observation(aid)['visible_objects']
                            if o['type'] == 'number_pad']
                    other = 'B' if aid == 'A' else 'A'
                    env.send_message(aid, other, json.dumps(pads))
                    candidates.extend((aid, pad) for pad in json.loads(env.agents[other].inbox[-1]['content']))
                prefix = []
                length = env.get_observation('A')['level_state']['sequence_length']
                while env.level == level and not env.solved:
                    for aid, pad in candidates:
                        if env.progress == 0:
                            for owner, known in prefix:
                                enter(env, owner, known)
                                inputs += 1
                        enter(env, aid, pad)
                        inputs += 1
                        self.assertLess(inputs, 1000)
                        feedback = env.get_observation(aid)['input_feedback']
                        if env.level != level or env.solved:
                            break
                        if feedback['result'] == 'accepted':
                            prefix.append((aid, pad))
                            break
                    self.assertLessEqual(len(prefix), length)
            self.assertEqual(env.completed_levels, [1, 2, 3, 4, 5])
            self.assertFalse(env.objects['vault']['locked'])
            result = score_episode(env, 600, objectives)
            rewards = [item for data in result['agents'].values() for item in data['items']
                       if item['reason'] == '\uB2E8\uACC4 \uC644\uB8CC']
            self.assertEqual({item['target'] for item in rewards}, {1, 2, 3, 4, 5})
            self.assertTrue(env.message_log.entries)

    def test_retry_and_level_transition_preserve_learning(self):
        env, _, _ = build_curriculum()
        for aid, agent in env.agents.items():
            agent.memory = {'learned': [1, 2]}
            agent.policy = SimpleNamespace(generated_code='old', _next_review_step=50,
                                           history=['past'], token_usage={'completion_tokens': 123})
        env.send_message('A', 'B', 'learning')
        first = env.sequence[0]
        enter(env, 'A', first)
        self.assertEqual(env.level, 2)
        wrong = next(k for k, v in env.objects.items()
                     if v['type'] == 'number_pad' and k != env.sequence[0])
        answer = list(env.sequence)
        enter(env, 'A', wrong)
        self.assertEqual(env.sequence, answer)
        self.assertEqual(env.progress, 0)
        self.assertIsNone(env.failure)
        for agent in env.agents.values():
            self.assertEqual(agent.memory, {'learned': [1, 2]})
            self.assertEqual(agent.policy.history, ['past'])
            self.assertEqual(agent.policy.token_usage['completion_tokens'], 123)
            self.assertIsNone(agent.policy.generated_code)
            self.assertIsNone(agent.policy._next_review_step)
        self.assertEqual(env.agents['B'].inbox[-1]['content'], 'learning')

    def test_cooperation_and_simultaneous_inputs(self):
        env, _, _ = build_curriculum()
        env._load_level(2)
        self.assertEqual({env.objects[p]['room'] for p in env.sequence}, {'A', 'B'})
        remote = next(p for p in env.sequence if env.objects[p]['room'] == 'B')
        env.press_number_pad('A', remote, contact=True)
        self.assertEqual(env.progress, 0)
        env._resolve_contacts([(env.objects[p]['room'], p) for p in env.sequence])
        self.assertEqual(env.resets, 1)
        self.assertEqual(env.progress, 0)
        self.assertEqual(env.completed_levels, [])
        self.assertIsNone(env.failure)

    def test_observations_never_reveal_next_digit(self):
        env, tasks, _ = build_curriculum(reveal_goal=False)
        env._load_level(4)
        before = env.get_observation('A')
        env.sequence.reverse()
        self.assertEqual(env.get_observation('A'), before)
        self.assertNotIn('Goal:', tasks['A'])
        self.assertFalse(any(o['type'] in ('clue', 'display') for o in env.objects.values()))

    def test_benchmark_log_and_episode_limit(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'run.jsonl'
            with contextlib.redirect_stdout(io.StringIO()):
                benchmark.run_episode('demo', '', '', {}, 2, str(path), policy_kind='noop',
                                      environment_kind='curriculum')
            records = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
            self.assertEqual(records[-1]['failure']['reason'], 'turn_limit')
            self.assertEqual(records[-1]['world']['level_state']['level'], 1)
            self.assertEqual(records[-1]['score']['team']['level_state']['completed_levels'], [])
            from viewer import Viewer
            view = Viewer(path)
            try:
                view.seek(len(view.reader.frames()) - 1)
                view.draw()
            finally:
                import pygame
                pygame.quit()
