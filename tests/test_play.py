"""Human play (play.py): two players take turns on one computer with LLM-equivalent observations."""
import os
os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'

import contextlib
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest

import benchmark
import play


def observation(objects=(), inventory=(), x=100.0, y=100.0, facing=0.0, step=1):
    return {'self': {'x': x, 'y': y, 'facing': facing, 'heading': {'x': 1.0, 'y': 0.0}, 'step': step,
                     'inventory': list(inventory), 'map_width': 400, 'map_height': 240},
            'visible_objects': list(objects), 'known_objects': {o['object_id']: o for o in objects},
            'walls': [], 'inbox': [], 'memory': {}, 'last_action_result': None, 'notices': []}


class ActionHelperTests(unittest.TestCase):
    def test_interaction_picks_the_nearest_usable_object_in_reach(self):
        objects = [{'object_id': 'far_key', 'type': 'key', 'x': 130, 'y': 100},
                   {'object_id': 'btn', 'type': 'button', 'x': 110, 'y': 100},
                   {'object_id': 'lever', 'type': 'lever', 'x': 112, 'y': 100}]
        self.assertEqual(play.interaction_action(observation(objects)), {'type': 'press_button', 'button_id': 'btn'})
        self.assertIsNone(play.interaction_action(observation(objects[:1])))

    def test_locked_door_uses_a_matching_key(self):
        door = {'object_id': 'gate', 'type': 'door', 'x': 120, 'y': 100, 'locked': True, 'radius': 10}
        key = {'object_id': 'k1', 'type': 'key', 'unlocks': 'gate'}
        self.assertEqual(play.interaction_action(observation([door], [key])), {'type': 'use_key', 'key_id': 'k1'})
        self.assertIsNone(play.interaction_action(observation([door])))

    def test_turn_toward_and_drop(self):
        self.assertEqual(play.turn_toward(observation(facing=0), 100, 200), {'type': 'turn', 'angle': 90.0})
        self.assertEqual(play.turn_toward(observation(facing=350), 200, 100), {'type': 'turn', 'angle': 10.0})
        self.assertIsNone(play.drop_action(observation()))
        self.assertEqual(play.drop_action(observation(inventory=[{'object_id': 'gem'}])), {'type': 'drop', 'object_id': 'gem'})


class HumanEpisodeTests(unittest.TestCase):
    def run_episode(self, bridge, serve, steps=3):
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()):
            path = Path(folder) / 'human.jsonl'
            tasks = {}

            def factory(agent_id, description):
                tasks[agent_id] = description
                return play.HumanPolicy(bridge, agent_id, description)
            server = threading.Thread(target=serve, daemon=True)
            server.start()
            benchmark.run_episode('human', '', '', {}, steps, str(path), policy_kind='human',
                                  environment_kind='sequence_rooms', sequence_seed=3, policy_factory=factory)
            records = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
            score = json.loads(path.with_suffix('.score.json').read_text(encoding='utf-8'))
        return records, score, tasks

    def test_two_players_act_each_step_and_the_run_is_logged_like_a_benchmark(self):
        bridge = play.HumanBridge()
        seen = []

        def serve():
            while True:
                agent_id, obs, reply = bridge.requests.get()
                seen.append((obs['self']['step'], agent_id))
                self.assertNotIn('team', obs)  # a player only sees their own observation
                reply.put({'type': 'turn', 'angle': 10} if agent_id == 'A' else {'type': 'noop'})
        records, score, tasks = self.run_episode(bridge, serve)
        self.assertEqual(sorted(seen), [(s, a) for s in (1, 2, 3) for a in ('A', 'B')])
        self.assertEqual({a['model'] for r in records for a in r['agents']}, {'human'})
        self.assertEqual(records[-1]['agents'][0]['decision']['final_action'], {'type': 'turn', 'angle': 10})
        self.assertIn('room', tasks['A'])
        self.assertIsNone(score['stopped'])

    def test_quitting_ends_the_episode_and_keeps_the_log(self):
        bridge = play.HumanBridge()

        def serve():
            agent_id, obs, reply = bridge.requests.get()
            bridge.close()
            reply.put(None)
            while True:
                _, _, other = bridge.requests.get()
                other.put(None)
        _, score, _ = self.run_episode(bridge, serve, steps=50)
        self.assertEqual(score['stopped'], 'player quit')


class PlayWindowTests(unittest.TestCase):
    def setUp(self):
        self.bridge = play.HumanBridge()
        self.app = play.PlayApp(self.bridge, 80, Path('x.jsonl'))
        self.app.tasks = {'A': 'task A', 'B': 'task B'}

    def tearDown(self):
        play.pygame.quit()

    def request(self, agent_id, obs):
        reply = play.queue.Queue()
        self.bridge.requests.put((agent_id, obs, reply))
        return reply

    def test_turns_are_hidden_behind_a_curtain_and_actions_reach_the_game(self):
        clue = {'object_id': 'clue_A', 'type': 'clue', 'x': 120, 'y': 90, 'content': {'order': 1}}
        reply_b = self.request('B', observation(step=2))
        reply_a = self.request('A', observation([clue], step=2))
        self.app.poll()
        self.assertEqual(self.app.current, 'A')
        self.assertTrue(self.app.curtain)
        self.app.draw()
        self.app.handle_key(play.pygame.K_UP)  # ignored behind the curtain
        self.assertTrue(reply_a.empty())
        self.app.handle_key(play.pygame.K_RETURN)
        self.app.draw()
        self.app.handle_key(play.pygame.K_UP, play.pygame.KMOD_SHIFT)
        self.assertEqual(reply_a.get_nowait(), {'type': 'move_forward', 'distance': 5})
        self.app.poll()
        self.assertEqual(self.app.current, 'B')
        self.assertTrue(self.app.curtain)
        self.app.handle_key(play.pygame.K_RETURN)
        self.app.handle_key(play.pygame.K_t)
        self.app.handle_key(0, 0, 't')  # the text event of the key that opened the box is swallowed
        for char in 'go 7':
            self.app.handle_key(0, 0, char)
        self.app.draw()
        self.app.handle_key(play.pygame.K_RETURN)
        self.assertEqual(reply_b.get_nowait(), {'type': 'send_message', 'receiver_id': 'A', 'content': 'go 7'})

    def test_numeric_inputs_clicks_and_invalid_interactions(self):
        reply = self.request('A', observation(step=3))
        self.app.poll()
        self.app.handle_key(play.pygame.K_RETURN)
        self.app.handle_key(play.pygame.K_e)
        self.assertTrue(reply.empty())
        self.assertIn('상호작용할 물체가 없습니다', self.app.info)
        self.app.handle_key(play.pygame.K_r)
        for char in 'r-30':
            self.app.handle_key(0, 0, char)
        self.app.handle_key(play.pygame.K_RETURN)
        self.assertEqual(reply.get_nowait(), {'type': 'turn', 'angle': -30.0})
        reply = self.request('A', observation(step=4))
        self.app.poll()
        self.app.handle_key(play.pygame.K_RETURN)
        to_world, to_screen = self.app._transform(self.app.observation)
        self.app.handle_click(to_screen(100, 200), 3)
        self.assertEqual(reply.get_nowait(), {'type': 'turn', 'angle': 90.0})

    def test_finish_screen_reports_the_score(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'run.jsonl'
            path.with_suffix('.score.json').write_text(json.dumps({
                'total': 80, 'team': {'cleared': True, 'clear_step': 12, 'score': 70},
                'agents': {'A': {'score': 5}, 'B': {'score': 5}}}), encoding='utf-8')
            self.app.log_path = path
            self.app.finish()
            self.app.draw()
        self.assertIn('클리어: 예', self.app.result_lines[0])


if __name__ == '__main__':
    unittest.main()
