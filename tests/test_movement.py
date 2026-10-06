"""Continuous movement contract and collision regression tests (no API calls)."""
import math
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "enviroment"))

from enviroment import Environment
from policy import CodePolicy
from policy_sandbox import run_decide_code
from rule import ForbidActionRule


class MovementTests(unittest.TestCase):
    def make_env(self, x=10.0, y=10.0, facing=0.0, walls=(), max_move=20.0):
        game_map = SimpleNamespace(map_width=100.0, map_height=100.0, walls=list(walls))
        env = Environment(game_map, max_move=max_move)
        env.add_agent("A", x, y, facing=facing)
        return env

    def forward(self, env, distance):
        return env.apply_action("A", {"type": "move_forward", "distance": distance})

    def test_fractional_forward_and_heading(self):
        env = self.make_env(x=10.125, y=9.875, facing=37.5)
        self.forward(env, 2.75)
        agent = env.agents["A"]
        self.assertAlmostEqual(agent.x, 10.125 + 2.75 * math.cos(math.radians(37.5)))
        self.assertAlmostEqual(agent.y, 9.875 + 2.75 * math.sin(math.radians(37.5)))
        self.assertEqual(agent.facing, 37.5)
        self.assertAlmostEqual(agent.last_move["distance"], 2.75)
        self.assertFalse(agent.last_move["blocked"])

    def test_small_moves_accumulate_without_rounding(self):
        env = self.make_env()
        for _ in range(100):
            self.forward(env, 0.01)
        self.assertAlmostEqual(env.agents["A"].x, 11.0)

    def test_fractional_turn_and_legacy_move(self):
        env = self.make_env()
        env.apply_action("A", {"type": "turn", "facing": 405.5})
        self.assertEqual(env.agents["A"].facing, 45.5)
        env.apply_action("A", {"type": "move", "dx": 0.25, "dy": -0.5})
        self.assertEqual((env.agents["A"].x, env.agents["A"].y), (10.25, 9.5))
        self.assertAlmostEqual(env.agents["A"].facing, math.degrees(math.atan2(-0.5, 0.25)) % 360)

    def test_distance_limit_is_distinct_from_collision(self):
        env = self.make_env(max_move=1.25)
        self.forward(env, 10.0)
        move = env.agents["A"].last_move
        self.assertEqual(move["requested_distance"], 10.0)
        self.assertEqual(move["distance"], 1.25)
        self.assertTrue(move["limited"])
        self.assertFalse(move["blocked"])
        unlimited = self.make_env(max_move=None)
        self.forward(unlimited, 30.5)
        self.assertEqual(unlimited.agents["A"].x, 40.5)

    def test_invalid_distance_does_not_change_position(self):
        for distance in (-0.1, True, "2.5", None, float("nan"), float("inf")):
            with self.subTest(distance=distance):
                env = self.make_env()
                self.assertEqual(self.forward(env, distance), {"type": "noop"})
                self.assertEqual(env.agents["A"].x, 10.0)
        env = self.make_env()
        self.assertEqual(env.apply_action("A", {"type": "move_forward"}), {"type": "noop"})

    def test_zero_distance_keeps_pose(self):
        env = self.make_env(facing=22.5)
        self.forward(env, 0)
        self.assertEqual(env.agents["A"].facing, 22.5)
        self.assertEqual(env.agents["A"].last_move["distance"], 0)
        self.assertFalse(env.agents["A"].last_move["blocked"])

    def test_boundary_preserves_diagonal_path(self):
        env = self.make_env(x=99, y=10, facing=45)
        self.forward(env, 10)
        self.assertAlmostEqual(env.agents["A"].x, 100)
        self.assertAlmostEqual(env.agents["A"].y, 11)
        self.assertTrue(env.agents["A"].last_move["blocked"])
        env.turn_agent("A", 90)
        self.forward(env, 0.25)
        self.assertEqual(env.agents["A"].x, 100)
        self.assertAlmostEqual(env.agents["A"].y, 11.25)

    def test_wall_contact_stops_before_wall_and_allows_exit(self):
        wall = SimpleNamespace(x=12.25, y=0, width=0.1, height=100)
        env = self.make_env(walls=[wall])
        self.forward(env, 10.5)
        self.assertAlmostEqual(env.agents["A"].x, 11.75)
        self.assertTrue(env.agents["A"].last_move["blocked"])
        env.turn_agent("A", 180)
        self.forward(env, 0.125)
        self.assertAlmostEqual(env.agents["A"].x, 11.625)

    def test_door_contact_is_partial_and_cannot_tunnel(self):
        env = self.make_env(max_move=None)
        env.add_door("gate", 20.25, 10, radius=2.0)
        self.forward(env, 30)
        self.assertAlmostEqual(env.agents["A"].x, 17.75)
        self.assertTrue(env.agents["A"].last_move["blocked"])
        env.objects["gate"]["locked"] = False
        self.forward(env, 10.25)
        self.assertAlmostEqual(env.agents["A"].x, 28.0)

    def test_earliest_obstacle_wins(self):
        wall = SimpleNamespace(x=30, y=0, width=1, height=100)
        env = self.make_env(walls=[wall], max_move=None)
        env.add_door("gate", 20, 10, radius=2)
        self.forward(env, 50)
        self.assertEqual(env.agents["A"].x, 17.5)

    def test_forward_obeys_rules_and_coop_constraints(self):
        env = self.make_env()
        env.add_agent_rule("A", ForbidActionRule({"move_forward"}))
        self.assertEqual(self.forward(env, 2.5), {"type": "noop"})
        self.assertEqual(env.agents["A"].x, 10)
        env.agents["A"].rules.clear()
        env.agents["A"].inventory.append({"category": "coop", "required_agents": 2, "object_id": "crate"})
        self.forward(env, 2.5)
        self.assertEqual(env.agents["A"].last_move["distance"], 0)
        self.assertTrue(env.agents["A"].last_move["blocked"])

    def test_spatial_state_snapshot_and_portal_distance(self):
        env = self.make_env()
        before = env.get_observation("A")
        self.assertIsNone(before["self"]["last_move"])
        self.assertEqual(before["self"]["heading"], {"x": 1.0, "y": 0.0})
        env.add_portal("portal", 12.5, 10, 70.125, 80.25, radius=0.5)
        self.forward(env, 2.5)
        after = env.get_observation("A")
        self.assertEqual((after["self"]["x"], after["self"]["y"]), (70.125, 80.25))
        self.assertEqual(after["self"]["last_move"]["distance"], 2.5)
        after["self"]["last_move"]["distance"] = 99
        self.assertEqual(env.agents["A"].last_move["distance"], 2.5)
        self.assertEqual(before["self"]["x"], 10)

    def test_generated_forward_code_runs_in_sandbox(self):
        env = self.make_env()
        result = run_decide_code('def decide(observation):\n    return {"type": "move_forward", "distance": 0.375}', env.get_observation("A"))
        self.assertIsNone(result["error"])
        env.apply_action("A", result["action"])
        self.assertEqual(env.agents["A"].x, 10.375)

    def test_code_policy_detects_blocked_forward_immediately(self):
        policy = CodePolicy.__new__(CodePolicy)
        policy._last_pos = (10, 10)
        policy._last_action = {"type": "move_forward", "distance": 0.25}
        policy._stall_count = 0
        policy.stall_limit = 3
        self.assertIn("blocked", policy._stuck_reason(self.make_env().get_observation("A")))

    def test_step_records_fractional_action_and_observation(self):
        env = self.make_env()
        class ForwardPolicy:
            def decide(self, observation):
                return {"type": "move_forward", "distance": 0.125}
        env.agents["A"].set_policy(ForwardPolicy())
        env.step()
        self.assertEqual(env.agents["A"].x, 10.125)
        self.assertEqual(env.agents["A"].last_move["step"], 1)
        env.step()
        decision = env.decision_log.filter(step=2)[0]
        self.assertEqual(decision["observation"]["self"]["last_move"]["distance"], 0.125)
        self.assertEqual(decision["final_action"]["type"], "move_forward")
        self.assertEqual(env.agents["A"].x, 10.25)


if __name__ == "__main__":
    unittest.main()
