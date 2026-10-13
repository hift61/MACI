"""Scenario maps (scenarios/): every map is solvable, recovers from mistakes, and hides its secrets."""
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mapgen.builder import build_environment  # noqa: E402  (also puts enviroment/ on sys.path)
from mapgen.spec import MapSpec  # noqa: E402
from scenarios import SCENARIO_NAMES, load  # noqa: E402
from scenarios.oracle import run  # noqa: E402
from enviroment import Environment  # noqa: E402


def event_types(env):
    return [e["type"] for e in env.event_log.entries]


class ScenarioSolvableTests(unittest.TestCase):
    def test_every_scenario_clears_with_and_without_mistakes(self):
        for name in SCENARIO_NAMES:
            for mode in ("solution", "mistake"):
                with self.subTest(scenario=name, mode=mode):
                    step, _ = run(load(name), mode)
                    self.assertIsNotNone(step, f"{name} {mode} did not clear")

    def test_mistakes_really_happen_and_cost_time(self):
        # (시나리오, 실수 스크립트에서 반드시 나와야 하는 이벤트)
        expected = {
            "s03_split_experiment": "lever_pulled",
            "s04_half_mastermind": "keypad_attempt",
            "s05_lossy_sync": "sync_fail",
            "s06_short_radio": "keypad_reset",
            "s10_moving_world": "sync_fail",
            "s11_pincer": "pickup_blocked",
            "s12_unreliable_eyes": "keypad_reset",
            "s13_crossed_testimony": "keypad_attempt",
            "s14_silent_porters": "pickup_blocked",
        }
        for name, event in expected.items():
            with self.subTest(scenario=name):
                _, env = run(load(name), "mistake")
                self.assertIn(event, event_types(env))
        for name in ("s01_deadlock", "s04_half_mastermind", "s07_me_vs_us", "s08_boring_role",
                     "s13_crossed_testimony", "s15_glass_division"):
            with self.subTest(scenario=name):
                self.assertGreater(run(load(name), "mistake")[0], run(load(name), "solution")[0])

    def test_no_failure_state_is_ever_reached(self):
        for name in SCENARIO_NAMES:
            with self.subTest(scenario=name):
                _, env = run(load(name), "mistake")
                self.assertIsNone(env.failure)


class ScenarioFileTests(unittest.TestCase):
    def test_json_round_trip_builds_the_same_world(self):
        for name in SCENARIO_NAMES:
            with self.subTest(scenario=name):
                spec = load(name).build()
                again = MapSpec.from_dict(spec.to_dict())
                env_a, tasks_a, objectives_a = build_environment(spec)
                env_b, tasks_b, objectives_b = build_environment(again)
                self.assertEqual(set(env_a.objects), set(env_b.objects))
                self.assertEqual(tasks_a, tasks_b)
                self.assertEqual(objectives_a, objectives_b)
                self.assertEqual(spec.config["source"], f"scenarios/{name}.py")

    def test_exported_maps_match_the_scenario_code(self):
        for name in SCENARIO_NAMES:
            with self.subTest(scenario=name):
                path = ROOT / "map_datas" / f"{name}.json"
                self.assertTrue(path.is_file(), "run: python -m scenarios")
                self.assertEqual(MapSpec.load(str(path)).to_dict(),
                                 MapSpec.from_dict(load(name).build().to_dict()).to_dict())

    def test_plain_maps_still_use_the_plain_environment(self):
        env, _, _ = build_environment(MapSpec(seed=1, width=100, height=100,
                                              agents=[{"id": "A", "x": 10, "y": 10, "facing": 0}]))
        self.assertIs(type(env), Environment)

    def test_task_text_follows_information_contract_v2(self):
        _, tasks, _ = build_environment(load("s01_deadlock").build())
        self.assertIn("Goal: Clear all three stages", tasks["A"])
        for removed in ("room A", "Object guide", "permanently impossible", "several stages"):
            self.assertNotIn(removed, tasks["A"])  # 역할/물체 설명/안심 문구/단계 설명은 주지 않음
        _, tasks, _ = build_environment(load("s09_shared_budget").build())
        self.assertIn("C2 is at about (250, 125).", tasks["B"])  # 시야로 알아낼 수 없는 필수 정보만


class ScenarioSecretTests(unittest.TestCase):
    def visible(self, env, agent_id, object_id):
        observation = env.get_observation(agent_id)
        return next((o for o in observation["visible_objects"] if o["object_id"] == object_id), None)

    def test_secret_fields_are_not_observed(self):
        env, _, _ = build_environment(load("s04_half_mastermind").build())
        env.agents["A"].x, env.agents["A"].y, env.agents["A"].facing = 105, 60, 270
        panel = self.visible(env, "A", "color_panel_1")
        self.assertIsNotNone(panel)
        self.assertNotIn("_code", panel)
        self.assertEqual(panel["length"], 3)

        env, _, _ = build_environment(load("s03_split_experiment").build())
        gate = self.visible(env, "A", "G1") or env._disguise(env.objects["G1"])
        self.assertNotIn("_levers", gate)

        env, _, _ = build_environment(load("s11_pincer").build())
        env._load_stage(2)
        core = env._disguise(env.objects["core_3"])
        self.assertNotIn("waypoints", core)
        self.assertEqual(core["category"], "coop")

    def test_variant_clue_shows_each_agent_its_own_reading(self):
        env, _, _ = build_environment(load("s12_unreliable_eyes").build())
        for agent_id in ("A", "B"):
            env.agents[agent_id].x, env.agents[agent_id].y, env.agents[agent_id].facing = 60, 100, 270
        self.assertIn("4 1", self.visible(env, "A", "clue_1")["content"])
        self.assertIn("4 7", self.visible(env, "B", "clue_1")["content"])
        env.step()
        self.assertIn("4 1", env.get_observation("A")["known_objects"]["clue_1"]["content"])


class ScenarioRuleTests(unittest.TestCase):
    def test_short_radio_refuses_long_and_frequent_messages(self):
        env, _, _ = build_environment(load("s06_short_radio").build())
        env.step_count = 1
        env.apply_action("A", {"type": "send_message", "receiver_id": "B", "content": "r2c3 r4c1 r1c4"})
        self.assertEqual(env.agents["B"].inbox, [])
        self.assertIn("NOT sent", env.agents["A"].inbox[-1]["content"])
        env.apply_action("A", {"type": "send_message", "receiver_id": "B", "content": "23,41,14"})
        self.assertEqual(env.agents["B"].inbox[-1]["content"], "23,41,14")
        env.step_count = 3
        env.apply_action("A", {"type": "send_message", "receiver_id": "B", "content": "32"})
        self.assertEqual(len(env.agents["B"].inbox), 1)
        env.step_count = 6
        env.apply_action("A", {"type": "send_message", "receiver_id": "B", "content": "32"})
        self.assertEqual(len(env.agents["B"].inbox), 2)

    def test_lossy_radio_loses_and_delays_messages_reproducibly(self):
        def deliveries():
            env, _, _ = build_environment(load("s05_lossy_sync").build())
            for step in range(1, 61):
                env.step_count = step
                env._flush_messages()
                env.apply_action("A", {"type": "send_message", "receiver_id": "B", "content": f"m{step}"})
            return env.message_stats, [(m["content"], m["step"]) for m in env.agents["B"].inbox]
        stats, inbox = deliveries()
        self.assertGreater(stats["lost"], 5)
        self.assertGreater(stats["delayed"], 5)
        self.assertTrue(any(int(content[1:]) < step for content, step in inbox))
        self.assertEqual(deliveries(), (stats, inbox))

    def test_glass_walls_block_movement_but_not_sight(self):
        spec = MapSpec(seed=0, width=200, height=200, scenario="glass_test",
                       rules={"glass_walls": [[100, 0, 10, 200]]},
                       agents=[{"id": "A", "x": 50, "y": 100, "facing": 0}],
                       objects=[{"kind": "clue", "id": "sign", "x": 150, "y": 100,
                                 "params": {"content": "hi", "hidden": False}}])
        env, _, _ = build_environment(spec)
        self.assertIn("sign", [o["object_id"] for o in env.get_observation("A")["visible_objects"]])
        env.move_forward("A", 20)
        env.move_forward("A", 20)
        env.move_forward("A", 20)
        self.assertLess(env.agents["A"].x, 100)

    def test_sync_pads_push_back_a_lone_entry(self):
        env, _, _ = build_environment(load("s05_lossy_sync").build())
        env.agents["A"].x, env.agents["A"].y = 105, 80
        env.agents["A"].facing = 270
        env.step_count = 1
        env.apply_action("A", {"type": "move_forward", "distance": 20})
        env._update_pressure_plates()
        self.assertEqual((env.agents["A"].x, env.agents["A"].y), (105, 110))
        self.assertFalse(env.objects["pad_A"]["armed"])
        self.assertIn("sync_fail", event_types(env))
        # 이동은 유효(ok)했지만 동기화는 실패 -> 알림으로 알려 주고, 시도/헛된 시도로 집계
        self.assertEqual(env.get_observation("A")["last_action_result"]["status"], "ok")
        self.assertEqual(env.get_observation("A")["notices"][-1]["type"], "sync_fail")
        self.assertEqual(env.get_observation("B")["notices"], [])
        from scoring import score_episode
        team = score_episode(env, 150, [{"type": "sync_success", "group": "sync"}])["team"]
        self.assertEqual((team["attempts"], team["failed_attempts"], team["sync_failures"]), (1, 1, 1))

    def test_periodic_gate_follows_its_schedule(self):
        module = load("s10_moving_world")
        env, _, _ = build_environment(module.build())
        for step in range(1, 30):
            env.step_count = step
            env._update_periodic_doors()
            for gate in ("gate_A", "gate_B"):
                self.assertEqual(not env.objects[gate]["locked"], module.is_open(gate, step))

    def test_bonus_items_score_and_expire(self):
        from scoring import score_episode
        env, _, objectives = build_environment(load("s07_me_vs_us").build())
        env.agents["A"].x, env.agents["A"].y = 30, 40
        env.pick_up("A", "gem_1")
        env.step_count = 39
        env.step()
        self.assertNotIn("gem_2", env.objects)
        score = score_episode(env, max_steps=100, objectives=objectives)
        self.assertIn(25.0, [item["points"] for item in score["agents"]["A"]["items"]])
        self.assertEqual(score["team"]["metrics"]["bonus_points"], {"A": 25.0})

    def test_switch_plate_does_not_relock_a_latched_door(self):
        env, _, _ = build_environment(load("s01_deadlock").build())
        env._load_stage(1)
        env.agents["B"].x, env.agents["B"].y = 200, 271
        env.pull_lever("B", "release_A2")
        env.step()
        self.assertFalse(env.objects["door_A2"]["locked"])

    def test_spawned_items_avoid_walls(self):
        env, _, _ = build_environment(load("s08_boring_role").build())
        for _ in range(60):
            env.step()
        spawned = [o for o in env.objects.values() if o["object_id"].startswith(("part_", "gem_"))]
        self.assertTrue(spawned)
        for item in spawned:
            self.assertLess(item["y"], 150)
            self.assertFalse(any(wx <= item["x"] <= wx + ww and wy <= item["y"] <= wy + wh
                                 for wx, wy, ww, wh in env._walls()))


class ScenarioStageTests(unittest.TestCase):
    def test_stages_load_in_order_and_reset_positions(self):
        env, _, objectives = build_environment(load("s04_half_mastermind").build())
        self.assertEqual(objectives, [{"type": "all_stages_completed"}])
        self.assertEqual(env.get_observation("A")["stage"]["stage"], 1)
        self.assertIn("color_panel_1", env.objects)
        env.agents["A"].x = 40
        env.agents["A"].policy = type("P", (), {"generated_code": "x", "_stall_count": 2})()
        env._solve_keypad("A", env.objects["color_panel_1"])
        env._check_stage()
        self.assertNotIn("color_panel_1", env.objects)
        self.assertIn("color_panel_2", env.objects)
        self.assertEqual((env.agents["A"].x, env.agents["A"].y), (105, 160))
        self.assertIsNone(env.agents["A"].policy.generated_code)
        observation = env.get_observation("A")
        self.assertEqual(observation["stage"]["stage"], 2)
        self.assertEqual(observation["notices"][-1]["type"], "stage_started")
        self.assertEqual(observation["known_objects"].keys() & {"color_panel_1"}, set())
        self.assertIn("level_completed", event_types(env))

    def test_stage_walls_replace_the_map_walls(self):
        env, _, _ = build_environment(load("s02_leapfrog").build())
        first = len(env._walls())
        env._load_stage(2)
        self.assertGreater(len(env._walls()), first)
        self.assertIn("d3_7", env.objects)
        self.assertNotIn("d1_1", env.objects)


if __name__ == "__main__":
    unittest.main()
