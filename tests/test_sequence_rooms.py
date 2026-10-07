"""Two-room number-sequence environment checks; no API requests."""
import math
import os
import sys
import unittest

ENVIRONMENT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "enviroment")
if ENVIRONMENT_DIR not in sys.path:
    sys.path.insert(0, ENVIRONMENT_DIR)

from scoring import clear_step, score_episode  # noqa: E402
from sequence_rooms import build_sequence_rooms  # noqa: E402


class TurnTakingPolicy:
    """Reads its room's clue, presses its numbers only when every earlier
    order has been reported, and announces each press to the partner."""

    def __init__(self, agent_id, partner_id):
        self.agent_id, self.partner_id = agent_id, partner_id
        self.pressed = []
        self.announce = None

    def decide(self, obs):
        if self.announce is not None:
            order, self.announce = self.announce, None
            return {"type": "send_message", "receiver_id": self.partner_id, "content": f"pressed order {order}"}
        clue = obs["known_objects"][f"clue_{self.agent_id}"]["content"]
        done = set(self.pressed) | {int(m["content"].split()[-1]) for m in obs["inbox"] if m.get("type") == "text"}
        mine = [p for p in clue["your_presses"] if p["order"] not in self.pressed]
        if not mine:
            return {"type": "noop"}
        nxt = mine[0]
        if any(o not in done for o in range(1, nxt["order"])):
            return {"type": "noop"}
        pad = next(o for o in obs["known_objects"].values()
                   if o["type"] == "number_pad" and o["number"] == nxt["number"])
        dx, dy = pad["x"] - obs["self"]["x"], pad["y"] - obs["self"]["y"]
        if math.hypot(dx, dy) <= pad['touch_radius']:
            self.pressed.append(nxt["order"])
            return {"type": "send_message", "receiver_id": self.partner_id,
                    "content": f"pressed order {nxt['order']}"}
        # Retreat below the row before horizontal travel to avoid touching decoys.
        if abs(dx) > 1:
            if obs['self']['y'] < 110:
                return {"type": "move", "dx": 0, "dy": 110-obs['self']['y']}
            return {"type": "move", "dx": dx, "dy": 0}
        return {"type": "move", "dx": 0, "dy": dy}


class SequenceRoomsTests(unittest.TestCase):
    def test_rooms_use_different_numbers_and_clues_are_visible(self):
        env, tasks, _ = build_sequence_rooms(seed=3)
        numbers = {room: {o["number"] for o in env.objects.values() if o["type"] == "number_pad" and o["room"] == room}
                   for room in ("A", "B")}
        self.assertFalse(numbers["A"] & numbers["B"])
        self.assertEqual(set(tasks), {"A", "B"})
        for room in ("A", "B"):
            visible = {o["object_id"] for o in env.get_observation(room)["visible_objects"]}
            self.assertIn(f"clue_{room}", visible)
            self.assertNotIn(f"clue_{'B' if room == 'A' else 'A'}", visible)  # 벽에 가려 상대 방은 안 보임
            self.assertTrue({o for o in visible if o.startswith(f"pad_{room}")})

    def test_cooperative_turn_taking_clears(self):
        for seed in range(5):
            env, _, objectives = build_sequence_rooms(seed=seed, max_turns=80)
            env.agents["A"].set_policy(TurnTakingPolicy("A", "B"))
            env.agents["B"].set_policy(TurnTakingPolicy("B", "A"))
            for _ in range(80):
                env.step()
            self.assertIsNone(env.failure, seed)
            self.assertIsNotNone(clear_step(env.event_log.entries, objectives), seed)
            self.assertEqual(env.resets, 0)
            score = score_episode(env, max_steps=80, objectives=objectives)
            self.assertTrue(score["team"]["cleared"])
            self.assertEqual(score["team"]["failed_attempts"], 0)

    def test_wrong_order_resets_whole_sequence(self):
        env, _, _ = build_sequence_rooms(seed=1)
        first, second = env.sequence[0], env.sequence[1]
        presser = env.objects[first]["room"]
        env.agents[presser].x, env.agents[presser].y = env.objects[first]["x"], env.objects[first]["y"]
        env.apply_action(presser, {"type": "noop"})
        self.assertEqual(env.progress, 1)
        other = env.objects[second]["room"]
        wrong = next(p for p, o in env.objects.items()
                     if o["type"] == "number_pad" and o["room"] == other and p != second)
        env.agents[other].x, env.agents[other].y = env.objects[wrong]["x"], env.objects[wrong]["y"]
        env.apply_action(other, {"type": "noop"})
        self.assertEqual((env.progress, env.resets), (0, 1))
        self.assertEqual(env.objects[f"display_{other}"]["last_press"]["result"], "wrong_reset")
        self.assertEqual(env.objects["display_A"]["resets"], 1)

    def test_turn_limit_seals_vault(self):
        env, _, objectives = build_sequence_rooms(seed=0, max_turns=5)
        for _ in range(10):
            env.step()
        self.assertEqual(env.step_count, 5)
        self.assertEqual(env.failure["reason"], "turn_limit")
        self.assertEqual(env.failure["sealed_doors"], ["vault"])
        self.assertTrue(env.objects["vault"]["sealed"])
        self.assertIsNone(clear_step(env.event_log.entries, objectives))

    def test_contact_once_until_leave_and_reenter(self):
        env, _, _ = build_sequence_rooms(seed=2)
        first = env.sequence[0]
        pad = env.objects[first]
        aid = pad['room']
        agent = env.agents[aid]
        agent.x, agent.y = pad['x'], pad['y'] + 20
        env.apply_action(aid, {'type': 'move', 'dx': 0, 'dy': -15})
        self.assertEqual(env.progress, 1)
        for action in ({'type': 'noop'}, {'type': 'press_button', 'button_id': first},
                       {'type': 'move', 'dx': 0, 'dy': -2}):
            env.apply_action(aid, action)
        self.assertEqual(env.progress, 1)
        self.assertEqual(env.resets, 0)
        env.apply_action(aid, {'type': 'move', 'dx': 0, 'dy': 20})
        env.apply_action(aid, {'type': 'move', 'dx': 0, 'dy': -20})
        self.assertEqual(env.resets, 1)

    def test_crossing_pad_triggers_even_if_destination_is_outside(self):
        env, _, _ = build_sequence_rooms(seed=2, pads_per_room=2, presses_per_room=1)
        first = env.sequence[0]
        pad = env.objects[first]
        agent = env.agents[pad['room']]
        agent.x, agent.y = pad['x']-15, pad['y']
        env.apply_action(pad['room'], {'type': 'move', 'dx': 20, 'dy': 0})
        self.assertEqual(env.progress, 1)
        # A longer permitted move passes entirely across the pad in one action.
        env, _, _ = build_sequence_rooms(seed=2, pads_per_room=2, presses_per_room=1)
        pad = env.objects[env.sequence[0]]
        env.max_move = 40
        agent = env.agents[pad['room']]
        agent.x, agent.y = pad['x']-15, pad['y']
        env.apply_action(pad['room'], {'type': 'move', 'dx': 30, 'dy': 0})
        self.assertEqual(env.progress, 1)
        self.assertGreater(abs(agent.x-pad['x']), pad['touch_radius'])

    def test_random_layout_is_seeded_and_stable_after_reset(self):
        first, _, _ = build_sequence_rooms(seed=8)
        again, _, _ = build_sequence_rooms(seed=8)
        different, _, _ = build_sequence_rooms(seed=9)
        pads = lambda e: [(p['object_id'], p['number'], p['x']) for p in e.objects.values() if p['type'] == 'number_pad']
        self.assertEqual(pads(first), pads(again))
        self.assertEqual(first.sequence, again.sequence)
        self.assertNotEqual(pads(first), pads(different))
        layout, sequence = pads(first), list(first.sequence)
        wrong = next(p for p in first.objects.values() if p['type'] == 'number_pad' and p['object_id'] != sequence[0])
        aid = wrong['room']
        first.agents[aid].x, first.agents[aid].y = wrong['x'], wrong['y']
        first.apply_action(aid, {'type': 'noop'})
        self.assertEqual(first.resets, 1)
        self.assertEqual(pads(first), layout)
        self.assertEqual(first.sequence, sequence)


if __name__ == "__main__":
    unittest.main()
