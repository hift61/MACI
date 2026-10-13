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
            "s17_push_blocks": "blocks_reset",
            "s19_hot_cargo": "cargo_spoiled",
            "s20_scales": "scale_balanced",
            "s21_silent_signs": "keypad_reset",
            "s22_narrow_bridge": "zone_overloaded",
        }
        for name, event in expected.items():
            with self.subTest(scenario=name):
                _, env = run(load(name), "mistake")
                self.assertIn(event, event_types(env))
        for name in ("s01_deadlock", "s04_half_mastermind", "s07_me_vs_us", "s08_boring_role",
                     "s13_crossed_testimony", "s15_glass_division", "s16_remote_maze", "s17_push_blocks",
                     "s18_assembly_line", "s19_hot_cargo", "s20_scales", "s21_silent_signs", "s22_narrow_bridge",
                     "s23_key_chests", "s24_shared_purse"):
            with self.subTest(scenario=name):
                self.assertGreater(run(load(name), "mistake")[0], run(load(name), "solution")[0])

    def test_template_example_solves_and_is_not_exported(self):
        template = load("_template")
        self.assertNotIn("_template", SCENARIO_NAMES)
        solved, _ = run(template, "solution")
        recovered, _ = run(template, "mistake")
        self.assertIsNotNone(solved)
        self.assertGreater(recovered, solved)

    def test_no_failure_state_is_ever_reached(self):
        for name in SCENARIO_NAMES:
            with self.subTest(scenario=name):
                _, env = run(load(name), "mistake")
                self.assertIsNone(env.failure)


class ClueHintVersionTests(unittest.TestCase):
    """맵마다 두 버전: 단서에 장치 규칙 힌트가 있는 기본 버전과, 퍼즐 자료만 남긴 _nohint 버전"""

    @staticmethod
    def clues(spec):
        objects = spec.objects + [o for st in (spec.rules or {}).get("stages", []) for o in st["objects"]]
        return [o for o in objects if o["kind"] in ("clue", "variant_clue")]

    def test_nohint_version_keeps_only_puzzle_data_and_still_clears(self):
        from scenarios.common import CLUE_DATA_KEYS, without_clue_hints
        for name in SCENARIO_NAMES:
            with self.subTest(scenario=name):
                spec = load(name).build()
                bare = without_clue_hints(spec)
                self.assertEqual(bare.scenario, name + "_nohint")
                self.assertFalse(bare.config["clue_hints"])
                for o in self.clues(bare):
                    content = o["params"]["content"]
                    if isinstance(content, dict):
                        self.assertTrue(content and set(content) <= CLUE_DATA_KEYS, (o["id"], content))
                # 단서 말고는 같은 맵
                strip = lambda objs: [o for o in objs if o["kind"] not in ("clue", "variant_clue")]
                self.assertEqual(strip(bare.objects), strip(spec.objects))
                self.assertEqual(bare.objectives, spec.objectives)
                self.assertIsNotNone(run(load(name), "solution", clue_hints=False)[0])

    def test_hint_version_has_rule_sentences_somewhere(self):
        from scenarios.common import CLUE_DATA_KEYS
        for name in SCENARIO_NAMES:
            with self.subTest(scenario=name):
                keys = {k for o in self.clues(load(name).build())
                        if isinstance(o["params"]["content"], dict) for k in o["params"]["content"]}
                self.assertTrue(keys - CLUE_DATA_KEYS, f"{name} has no rule hint in its clues")

    def test_default_map_can_drop_its_hint_clues(self):
        from benchmark import build_episode
        kinds = lambda env: [o.get("type") for o in env.objects.values()]
        self.assertEqual(kinds(build_episode()[0]).count("clue"), 2)
        self.assertEqual(kinds(build_episode(clue_hints=False)[0]).count("clue"), 0)


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

    def test_task_descriptions_give_only_the_goal(self):
        # 정보 전달 원칙: 맵에서는 목표 문장만 (물체 설명, 위치, 역할, 단서 읽기 지시 없음)
        import re
        for name in SCENARIO_NAMES:
            with self.subTest(scenario=name):
                env, tasks, _ = build_environment(load(name).build())
                for text in tasks.values():
                    self.assertIn("Goal: ", text)
                    self.assertNotIn('{"type"', text)  # 목표가 JSON이 아닌 문장
                    self.assertIn("Nothing in this map can make the task permanently impossible", text)
                    for banned in ("Object guide", "Read the clue", "Read manual", "room A (", "You start",
                                   "several stages"):
                        self.assertNotIn(banned, text)
                    self.assertIsNone(re.search(r"\b(north|south|east|west)\b", text, re.I))
                for stage in env.stages:
                    self.assertNotIn("Read ", stage["briefing"])

    def test_system_prompt_explains_every_object_type(self):
        from policy import CODE_POLICY_SYSTEM_PROMPT
        for kind in ("door", "key", "button", "lever", "pressure_plate", "switch_plate", "sync_pad", "item",
                     "keypad", "display", "clue", "receptacle", "station", "scale", "checkpoint", "goal_zone",
                     "capacity_zone", "block", "block_target", "chest", "number_pad", "portal", "marker"):
            self.assertIn(f"{kind}:", CODE_POLICY_SYSTEM_PROMPT)
        for field in ('"coin"', '"cargo"', '"bonus"', '"latch"', '"reset"', '"cooldown"', '"operators"'):
            self.assertIn(field, CODE_POLICY_SYSTEM_PROMPT)


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


class ScenarioDeviceTests(unittest.TestCase):
    """s16~s24에 추가된 장치 (블록, 가공대, 화물, 저울, 정원 구역, 상자, 동전, 메시지 금지, 조작자 제한)."""

    def env_with(self, objects, agents=(("A", 100, 100), ("B", 100, 100)), rules=None, walls=()):
        spec = MapSpec(seed=0, width=300, height=300, scenario="device_test", rules=rules or {},
                       walls=[list(w) for w in walls],
                       agents=[{"id": a, "x": x, "y": y, "facing": 0} for a, x, y in agents],
                       objects=[{"kind": k, "id": i, "x": x, "y": y, "params": p} for k, i, x, y, p in objects])
        return build_environment(spec)[0]

    def push(self, env, agent_ids):
        env.step_count += 1
        for agent_id in agent_ids:
            env.apply_action(agent_id, {"type": "move_forward", "distance": 20})
        env._update_pressure_plates()

    def test_block_needs_two_agents_pushing_the_same_way(self):
        env = self.env_with([("push_block", "blk", 125, 100, {})], agents=(("A", 100, 100), ("B", 100, 100)))
        self.push(env, ["A"])
        self.assertEqual(env.objects["blk"]["x"], 125)
        self.assertIn("push_too_weak", event_types(env))
        self.push(env, ["A", "B"])
        self.assertEqual(env.objects["blk"]["x"], 145)
        self.assertLess(env.agents["A"].x, 145 - 12)  # 블록은 단단해서 통과하지 못함

    def test_reset_lever_returns_blocks(self):
        env = self.env_with([("push_block", "blk", 125, 100, {}), ("reset_lever", "rst", 108, 100, {"blocks": ["blk"]})])
        self.push(env, ["A", "B"])
        env.pull_lever("A", "rst")
        self.assertEqual((env.objects["blk"]["x"], env.objects["blk"]["y"]), (125, 100))

    def test_station_turns_input_into_output_after_delay(self):
        env = self.env_with([("station", "oven", 100, 100, {"input": "ore", "output": "ingot", "process_steps": 2}),
                             ("item", "ore_1", 100, 100, {})])
        env.pick_up("A", "ore_1")
        env.drop("A", "ore_1")
        self.assertNotIn("ore_1", env.objects)
        for _ in range(2):
            env.step()
        self.assertTrue(any(i.startswith("ingot") for i in env.objects))

    def test_cargo_slows_carrier_and_returns_after_hold_limit_unless_handed_over(self):
        env = self.env_with([("cargo", "box", 100, 100, {"hold_limit": 3, "carry_speed": 5})])
        env.pick_up("A", "box")
        env.move_forward("A", 20)
        self.assertAlmostEqual(env.agents["A"].x, 105)
        env.drop("A", "box")
        env.pick_up("B", "box")
        self.assertIn("cargo_handoff", event_types(env))
        for _ in range(3):
            env.step()
        self.assertIn("cargo_spoiled", event_types(env))
        self.assertEqual((env.objects["box"]["x"], env.objects["box"]["y"]), (100, 100))

    def test_scale_reads_hidden_weights(self):
        env = self.env_with([("weighted_item", "c1", 100, 100, {"weight": 4}), ("weighted_item", "c2", 100, 100, {"weight": 6}),
                             ("scale", "test", 100, 100, {}), ("scale", "vault", 200, 200, {"target": 10})])
        env.step()
        self.assertEqual(env.objects["test"]["reading"], 10)
        self.assertNotIn("_weight", env._disguise(env.objects["c1"]))
        self.assertNotIn("_target", env._disguise(env.objects["vault"]))

    def test_capacity_zone_throws_back_both_agents(self):
        env = self.env_with([("capacity_zone", "bridge", 150, 100, {"width": 40, "height": 20})],
                            agents=(("A", 115, 100), ("B", 185, 100)))
        env.agents["B"].facing = 180
        env.step_count = 1
        env._update_pressure_plates()
        env.apply_action("A", {"type": "move_forward", "distance": 20})
        env.apply_action("B", {"type": "move_forward", "distance": 20})
        env._update_pressure_plates()
        self.assertEqual((env.agents["A"].x, env.agents["B"].x), (115, 185))
        self.assertIn("zone_overloaded", event_types(env))

    def test_chest_opens_with_its_key_and_releases_contents(self):
        env = self.env_with([("chest", "box", 100, 110, {"contents": [{"kind": "item", "id": "gem"}]}),
                             ("key", "k", 100, 100, {"unlocks": "box"})])
        self.assertNotIn("_contents", env._disguise(env.objects["box"]))
        env.pick_up("A", "k")
        env.use_key("A", "k")
        self.assertFalse(env.objects["box"]["locked"])
        self.assertIn("gem", env.objects)

    def test_coins_held_at_the_end_score_and_tolls_open_doors(self):
        from scoring import score_episode
        env = self.env_with([("coin", "coin_1", 100, 100, {"value": 5}), ("coin", "coin_2", 100, 100, {"value": 5}),
                             ("door", "gate", 250, 250, {}),
                             ("receptacle", "toll", 100, 100, {"accepts": ["coin"], "target": 1, "opens": ["gate"]})])
        env.pick_up("A", "coin_1")
        env.pick_up("A", "coin_2")
        env.drop("A", "coin_1")
        self.assertFalse(env.objects["gate"]["locked"])
        score = score_episode(env, max_steps=10, objectives=[])
        self.assertIn(("보유 동전", 5), [(i["reason"], i["points"]) for i in score["agents"]["A"]["items"]])

    def test_messages_can_be_disabled_and_panels_limited_to_operators(self):
        env = self.env_with([("keypad", "pad", 100, 100, {"code": ["x"], "operators": ["B"]}),
                             ("keypad_button", "btn", 100, 100, {"panel": "pad", "label": "x"})],
                            rules={"message_disabled": True})
        env.apply_action("A", {"type": "send_message", "receiver_id": "B", "content": "hi"})
        self.assertEqual(env.agents["B"].inbox, [])
        env.press_button("A", "btn")
        self.assertIn("keypad_denied", event_types(env))
        env.press_button("B", "btn")
        self.assertTrue(env.objects["pad"]["solved"])

    def test_goal_zone_can_require_only_some_agents(self):
        env = self.env_with([("goal_zone", "exit", 100, 100, {"width": 20, "height": 20, "agents": ["A"]})],
                            agents=(("A", 100, 100), ("B", 250, 250)))
        env.step()
        self.assertIn("team_assembled", event_types(env))


if __name__ == "__main__":
    unittest.main()
