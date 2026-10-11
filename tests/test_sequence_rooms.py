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


def move_for_contact(env, aid, dx, dy):
    """Set the test fixture heading, then exercise the real forward action."""
    env.turn_agent(aid, math.degrees(math.atan2(dy, dx)) % 360)
    env.apply_action(aid, {"type": "move_forward", "distance": math.hypot(dx, dy)})


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
        def steer(dx, dy):
            facing = math.degrees(math.atan2(dy, dx)) % 360
            angle = (facing - obs['self']['facing'] + 180) % 360 - 180
            if abs(angle) > 0.001:
                return {"type": "turn", "angle": angle}
            return {"type": "move_forward", "distance": math.hypot(dx, dy)}

        if abs(dx) > 1:
            if obs['self']['y'] < 110:
                return steer(0, 110-obs['self']['y'])
            return steer(dx, 0)
        return steer(0, dy)


class SequenceRoomsTests(unittest.TestCase):
    def test_goal_toggle_changes_only_prompt_goal(self):
        from benchmark import build_episode
        from mapgen import generate_map
        from mapgen.builder import build_environment
        builders = (lambda enabled: build_sequence_rooms(seed=3, reveal_goal=enabled),
                    lambda enabled: build_environment(generate_map(seed=3), reveal_goal=enabled),
                    lambda enabled: build_episode(reveal_goal=enabled))
        for build in builders:
            shown, hidden = build(True), build(False)
            self.assertEqual(shown[0].objects, hidden[0].objects)
            for aid in shown[1]:
                self.assertIn('Goal:', shown[1][aid])
                self.assertNotIn('Goal:', hidden[1][aid])
                self.assertIn('Other agents:', hidden[1][aid])
            if len(shown) == 3:
                self.assertEqual(shown[2], hidden[2])
        _, tasks, _ = build_sequence_rooms(seed=3, reveal_goal=False)
        for text in tasks.values():
            self.assertIn('strictly in overall order', text)
            self.assertIn('resets the entire sequence', text)
            self.assertNotIn("unlock door 'vault'", text)

    def test_prompts_give_minimal_rules_without_solution_strategy(self):
        from policy import CODE_POLICY_SYSTEM_PROMPT, CODE_STEP_SYSTEM_PROMPT, HYBRID_POLICY_SYSTEM_PROMPT
        from benchmark import build_episode
        from mapgen import generate_map
        from mapgen.builder import task_descriptions
        env, tasks, _ = build_sequence_rooms(seed=3)
        for descriptions in (tasks, build_episode()[1], task_descriptions(generate_map(seed=3))):
            for aid, text in descriptions.items():
                self.assertIn(f"You are agent {aid}", text)
                self.assertIn("Other agents:", text)
                self.assertIn("move_forward", text)
                self.assertIn('Goal:', text)
                for hint in ("your_presses", "pressure plate", "clue_A",
                             "ALL of these goals"):
                    self.assertNotIn(hint, text)
                for strategy in ('travel below', 'approaching your target vertically',
                                 'pressed order 3', 'wait for their message', 'approximately ('):
                    self.assertNotIn(strategy, text)
        for text in tasks.values():
            self.assertIn('strictly in overall order: first position 1, then position 2', text)
            self.assertIn('automatically inputs', text)
            self.assertIn('Only one pad input is allowed per step', text)
            self.assertIn('resets the entire sequence', text)
            self.assertIn('60 steps', text)
        for prompt in (CODE_POLICY_SYSTEM_PROMPT, CODE_STEP_SYSTEM_PROMPT, HYBRID_POLICY_SYSTEM_PROMPT):
            for hint in ("your_presses", "sequence_rooms", "avoid accidentally touching", "global progress"):
                self.assertNotIn(hint, prompt)
        # Local clues remain discoverable through the environment, not the prompt.
        self.assertIn("your_presses", env.objects['clue_A']['content'])

    def test_simultaneous_presses_cannot_clear_by_application_order(self):
        for agent_order in (("A", "B"), ("B", "A")):
            env, _, objectives = build_sequence_rooms(seed=2, pads_per_room=2, presses_per_room=1)
            env.agents = {aid: env.agents[aid] for aid in agent_order}
            # Arrange the answer in exactly the engine's step-1 application order.
            order = agent_order[1:] + agent_order[:1]
            pads = {aid: next(pid for pid in env.sequence if env.objects[pid]['room'] == aid)
                    for aid in agent_order}
            env.set_sequence([pads[aid] for aid in order])
            for aid in agent_order:
                pad = env.objects[pads[aid]]
                env.agents[aid].x, env.agents[aid].y = pad['x'], pad['y'] + 15
                env.turn_agent(aid, 270)
                class EnterPad:
                    def decide(self, obs):
                        return {'type': 'move_forward', 'distance': 10}
                env.agents[aid].set_policy(EnterPad())
            env.step()
            self.assertEqual((env.progress, env.resets), (0, 1))
            self.assertFalse(env.solved)
            self.assertTrue(env.objects['vault']['locked'])
            self.assertIsNone(clear_step(env.event_log.entries, objectives))
            resets = [e for e in env.event_log.entries if e['type'] == 'sequence_reset']
            self.assertEqual(resets[0]['reason'], 'simultaneous_input')
            self.assertFalse(any(e['type'] == 'number_accepted' for e in env.event_log.entries))

    def test_every_out_of_order_contact_resets_and_requires_full_retry(self):
        for seed in range(10):
            env, _, objectives = build_sequence_rooms(seed=seed)
            for pid in env.sequence[1:]:
                pad = env.objects[pid]
                aid = pad['room']
                # Approach afresh, so each assertion tests an actual entry.
                env.agents[aid].x, env.agents[aid].y = pad['x'], pad['y'] + 15
                env._pads_inside[aid] = set()
                move_for_contact(env, aid, 0, -10)
                self.assertEqual(env.progress, 0, (seed, pid))
                self.assertTrue(env.objects['vault']['locked'])
                self.assertIsNone(clear_step(env.event_log.entries, objectives))
            for index, pid in enumerate(env.sequence):
                pad = env.objects[pid]
                aid = pad['room']
                env.agents[aid].x, env.agents[aid].y = pad['x'], pad['y'] + 15
                env._pads_inside[aid] = set()
                move_for_contact(env, aid, 0, -10)
                self.assertEqual(env.progress, index + 1)
            self.assertTrue(env.solved)

    def test_one_move_across_multiple_pads_cannot_submit_a_sequence(self):
        env, _, _ = build_sequence_rooms(seed=2, pads_per_room=2, presses_per_room=2)
        pads = sorted((p for p in env.objects.values()
                       if p['type'] == 'number_pad' and p['room'] == 'A'), key=lambda p: p['x'])
        env.set_sequence([p['object_id'] for p in pads])
        agent = env.agents['A']
        agent.x, agent.y = pads[0]['x'] - 15, pads[0]['y']
        env.max_move = 200
        move_for_contact(env, 'A', pads[-1]['x'] - agent.x + 15, 0)
        self.assertEqual((env.progress, env.resets), (0, 1))
        self.assertFalse(env.solved)
        self.assertTrue(env.objects['vault']['locked'])

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
        move_for_contact(env, aid, 0, -15)
        self.assertEqual(env.progress, 1)
        for action in ({'type': 'noop'}, {'type': 'press_button', 'button_id': first}):
            env.apply_action(aid, action)
        move_for_contact(env, aid, 0, -2)
        self.assertEqual(env.progress, 1)
        self.assertEqual(env.resets, 0)
        move_for_contact(env, aid, 0, 20)
        move_for_contact(env, aid, 0, -20)
        self.assertEqual(env.resets, 1)

    def test_crossing_pad_triggers_even_if_destination_is_outside(self):
        env, _, _ = build_sequence_rooms(seed=2, pads_per_room=2, presses_per_room=1)
        first = env.sequence[0]
        pad = env.objects[first]
        agent = env.agents[pad['room']]
        agent.x, agent.y = pad['x']-15, pad['y']
        move_for_contact(env, pad['room'], 20, 0)
        self.assertEqual(env.progress, 1)
        # A longer permitted move passes entirely across the pad in one action.
        env, _, _ = build_sequence_rooms(seed=2, pads_per_room=2, presses_per_room=1)
        pad = env.objects[env.sequence[0]]
        env.max_move = 40
        agent = env.agents[pad['room']]
        agent.x, agent.y = pad['x']-15, pad['y']
        move_for_contact(env, pad['room'], 30, 0)
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
