"""MACI benchmark runner: plays out one cooperative episode with Code-as-
Policies agents (CodePolicy - see enviroment/policy.py) and writes a
manifest.jsonl of every step's decisions and messages, in the shape
maci_judge.py expects. Mirrors the split from the sibling MACI benchmark
project: a run produces logs, and a separate judge script scores them
afterward (see maci_judge.py) instead of judging live.

Usage:
    python benchmark.py --model upstage/solar-pro4 --steps 40
    python benchmark.py --model upstage/solar-pro4 --steps 40 --out my_run.jsonl
    python benchmark.py --model upstage/solar-pro4 --steps 80 --map-seed 42        # 무작위 생성 맵
    python benchmark.py --model upstage/solar-pro4 --steps 80 --map-file map_datas/map_42.json
    python benchmark.py --policy tooluse --map-seed 42 --steps 80                  # API 키 없이 실행 확인용
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
ENVIRONMENT_DIR = os.path.join(HERE, "enviroment")
if ENVIRONMENT_DIR not in sys.path:
    sys.path.insert(0, ENVIRONMENT_DIR)  # enviroment/*.py use flat sibling imports (from policy import ...)

from enviroment import Environment  # noqa: E402
from policy import CodePolicy, NoopPolicy, RandomPolicy, ToolUsePolicy  # noqa: E402
from scoring import clear_step, score_episode  # noqa: E402
from mapgen import MapSpec, generate_map  # noqa: E402
from mapgen.builder import build_environment  # noqa: E402
from world_core import GameMap  # noqa: E402
from sequence_rooms import build_sequence_rooms  # noqa: E402

RUNS_DIR = os.path.join(HERE, "benchmark_runs")


def read_secret(filename: str = "key.txt") -> str:
    """Read the API key from a file relative to this project's directory."""
    filename = os.path.join(HERE, filename)
    try:
        with open(filename, encoding="utf-8-sig") as f:
            value = f.read().strip()
    except FileNotFoundError:
        raise SystemExit(
            f"Missing credential: create {filename} containing just the API key."
        )
    if not value:
        raise SystemExit(f"Empty credential file: put your API key in {filename}.")
    return value


def build_episode():
    """A door that only unlocks while an agent stands on each of two
    separated pressure plates AT THE SAME TIME (see enviroment.py's
    add_pressure_plate AND-condition note) - neither agent can solve this
    alone, so it exercises real coordination (e.g. via send_message), not
    just navigation."""
    game_map = GameMap()
    env = Environment(game_map, interact_radius=15.0)

    env.add_door("gate", x=250, y=250, locked=True, radius=10.0)
    env.add_pressure_plate("plate_a", x=40, y=40, linked_door_id="gate", radius=12.0)
    env.add_pressure_plate("plate_b", x=460, y=460, linked_door_id="gate", radius=12.0)

    env.add_agent("A", x=40, y=460)
    env.add_agent("B", x=460, y=40)

    task_descriptions = {
        "A": (
            "You are agent A in a 500x500 area. You and agent B must unlock the "
            "door 'gate' by BOTH standing on your own pressure plate AT THE SAME "
            "TIME - stepping off releases it immediately. Your plate 'plate_a' is "
            "at approximately (40, 40); B's plate 'plate_b' is at approximately "
            "(460, 460). Move to your plate, use send_message to agree on timing "
            "with B, then stay there until you both confirm you're ready."
        ),
        "B": (
            "You are agent B in a 500x500 area. You and agent A must unlock the "
            "door 'gate' by BOTH standing on your own pressure plate AT THE SAME "
            "TIME - stepping off releases it immediately. Your plate 'plate_b' is "
            "at approximately (460, 460); A's plate 'plate_a' is at approximately "
            "(40, 40). Move to your plate, use send_message to agree on timing "
            "with A, then stay there until you both confirm you're ready."
        ),
    }
    return env, task_descriptions


# 기본 맵(build_episode)의 클리어 조건: gate가 열린 순간 (형식은 scoring._matches 참고)
GATE_OBJECTIVES = [{"type": "door_unlocked", "door_id": "gate"}]


# map_spec이 있으면 mapgen으로 만든 맵, 없으면 기본 압력판 맵(build_episode)으로 진행
# --policy 선택지. code만 LLM(API 키 필요)을 쓰고, 나머지는 API 키 없이 파이프라인 전체(맵/로그/
# 채점)가 도는지 확인하는 용도의 규칙 기반 정책
POLICY_CHOICES = ("code", "tooluse", "random", "noop")


def make_policy(kind: str, model: str, description: str, base_url: str, api_key: str, extra_params: dict,
                interact_radius: float):
    if kind == "code":
        return CodePolicy(model=model, task_description=description, base_url=base_url,
                          api_key=api_key, extra_params=extra_params)
    if kind == "tooluse":
        return ToolUsePolicy(interact_radius=interact_radius, step_size=10.0)
    if kind == "random":
        return RandomPolicy(step_size=10.0)
    if kind == "noop":
        return NoopPolicy()
    raise ValueError(f"unknown policy: {kind!r} (expected one of {POLICY_CHOICES})")


def run_episode(model: str, base_url: str, api_key: str, extra_params: dict, steps: int, log_path: str,
                map_spec: MapSpec = None, policy_kind: str = "code", environment_kind: str = "map",
                sequence_seed: int = 42, pads_per_room: int = 5, presses_per_room: int = 3,
                max_resets: int | None = None, debug: bool = False) -> None:
    if steps < 1:
        raise ValueError("steps must be at least 1")
    if environment_kind == "sequence_rooms":
        if map_spec is not None:
            raise ValueError("sequence_rooms cannot be combined with a map")
        env, task_descriptions, objectives = build_sequence_rooms(
            seed=sequence_seed, pads_per_room=pads_per_room, presses_per_room=presses_per_room,
            max_turns=steps, max_resets=max_resets)
    elif environment_kind != "map":
        raise ValueError(f"unknown environment: {environment_kind}")
    elif map_spec is not None:
        env, task_descriptions, objectives = build_environment(map_spec)
    else:
        env, task_descriptions = build_episode()
        objectives = GATE_OBJECTIVES

    os.makedirs(os.path.dirname(os.path.abspath(log_path)), exist_ok=True)
    debug_path = os.path.splitext(log_path)[0] + ".debug.jsonl"
    debug_lock = threading.Lock()
    if debug:
        with open(debug_path, 'w', encoding='utf-8'):
            pass

    def emit_debug(event, agent=None, **details):
        if not debug:
            return
        record = {'time': datetime.datetime.now().astimezone().isoformat(timespec='milliseconds'),
                  'step': env.step_count, 'event': event, 'agent': agent, **details}
        line = json.dumps(record, ensure_ascii=False, default=str)
        with debug_lock:
            with open(debug_path, 'a', encoding='utf-8') as file:
                file.write(line + '\n')
            print('[DEBUG] ' + line, flush=True)

    emit_debug('environment_ready', environment=environment_kind, steps=steps)
    checks_path = os.path.splitext(log_path)[0] + ".code_checks.jsonl"
    with open(checks_path, "w", encoding="utf-8"):
        pass
    checks_lock = threading.Lock()

    def write_check(agent_id, event):
        with checks_lock, open(checks_path, "a", encoding="utf-8") as checks_file:
            checks_file.write(json.dumps({"agent": agent_id, **event}, ensure_ascii=False) + "\n")
        emit_debug('code_check', agent_id, check=event)

    policies = {}
    for agent_id, description in task_descriptions.items():
        policies[agent_id] = make_policy(policy_kind, model, description, base_url, api_key, extra_params,
                                         env.interact_radius)
        checks = getattr(policies[agent_id], "code_checks", None)
        if checks is not None:
            checks.sink = lambda event, aid=agent_id: write_check(aid, event)
        policies[agent_id].debug_sink = lambda event, details, aid=agent_id: emit_debug(event, aid, **details)
        env.agents[agent_id].set_policy(policies[agent_id])

    # Observer-only state; this is never added to the agents' observations.
    def snapshot():
        return {"width": env.game_map.map_width, "height": env.game_map.map_height,
                "walls": env._walls(), "objects": list(env.objects.values())}

    os.makedirs(os.path.dirname(os.path.abspath(log_path)), exist_ok=True)
    scene_path = os.path.splitext(log_path)[0] + ".scene.json"
    with open(scene_path, "w", encoding="utf-8") as scene:
        json.dump({"environment": environment_kind, "world": snapshot(),
                   "agents": [{"agent": aid, "position": [a.x, a.y], "facing": a.facing}
                              for aid, a in env.agents.items()]}, scene, ensure_ascii=False)

    with open(log_path, "w", encoding="utf-8") as f:
        for step in range(1, steps + 1):
            emit_debug('step_started', next_step=step)
            env.step()

            decisions_by_agent = {d["agent_id"]: d for d in env.decision_log.filter(step=step)}
            step_messages = [m for m in env.message_log.entries if m["step"] == step]

            record = {
                "step": step,
                "task": dict(task_descriptions),
                "map_seed": sequence_seed if environment_kind == "sequence_rooms" else (map_spec.seed if map_spec is not None else None),
                "environment": environment_kind,
                "world": snapshot(),
                "failure": env.failure,
                "objectives": objectives,
                "cleared": clear_step(env.event_log.entries, objectives) is not None,
                "messages": step_messages,
                "events": env.event_log.filter(step=step),
                "agents": [
                    {
                        "agent": agent_id,
                        "model": model if policy_kind == "code" else policy_kind,
                        "position": [env.agents[agent_id].x, env.agents[agent_id].y],
                        "facing": env.agents[agent_id].facing,
                        "spatial_state": env.agents[agent_id].spatial_state(),
                        "generated_code": getattr(policies[agent_id], "generated_code", None),
                        "decision": {
                            "action": decisions_by_agent.get(agent_id, {}).get("action"),
                            "final_action": decisions_by_agent.get(agent_id, {}).get("final_action"),
                            "overridden": decisions_by_agent.get(agent_id, {}).get("overridden", False),
                            "policy_error": getattr(policies[agent_id], "last_error", None),
                            "recovery": getattr(policies[agent_id], "last_recovery", None),
                            "code_checks": (policies[agent_id].code_checks.snapshot()
                                            if hasattr(policies[agent_id], "code_checks") else None),
                            "context_messages": len(getattr(policies[agent_id], '_conversation_history', [])),
                            # CodePolicy가 이번 step에 stuck으로 코드를 재생성했으면 {"step", "reason"}
                            "replan": getattr(policies[agent_id], "last_replan", None),
                        },
                    }
                    for agent_id in task_descriptions
                ],
            }
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
            f.flush()  # Make completed steps available to the live viewer immediately.
            for agent in record['agents']:
                emit_debug('agent_action', agent['agent'], position=agent['position'], decision=agent['decision'])
            for message in record['messages']:
                emit_debug('message', message=message)
            for event in record['events']:
                emit_debug('environment_event', detail=event)

            errors = {a: p.last_error for a, p in policies.items() if getattr(p, "last_error", None)}
            replans = {a: p.last_replan["reason"] for a, p in policies.items() if getattr(p, "last_replan", None)}
            suffix = (f"  replans={replans}" if replans else "") + (f"  errors={errors}" if errors else "")
            print(f"step {step}/{steps}: cleared={record['cleared']}{suffix}")

            if record["cleared"]:
                print(f"\nSUCCESS at step {step}: all objectives achieved.")
                break
            # trap이 발동해 문이 영구 봉인되면 그 문의 objective는 더 이상 달성 불가 - 남은 step을 낭비하지 않음.
            # 봉인된 문이 이미 열린 적 있거나 objective와 무관하면 아직 클리어 가능하므로 계속 진행
            if env.failure is not None and any(
                objective.get("door_id") in env.failure["sealed_doors"]
                and clear_step(env.event_log.entries, [objective]) is None
                for objective in objectives
            ):
                print(f"\nFAILED at step {step}: {env.failure.get('reason', 'trap')} "
                      f"({env.failure['object_id']}); sealed {env.failure['sealed_doors']}.")
                break

    # 회차 점수: manifest는 maci_judge.py가 step 단위로 읽으므로 같은 파일에 섞지 않고 옆에 따로 저장
    score = score_episode(env, max_steps=steps, objectives=objectives)
    score["code_checks"] = {aid: p.code_checks.snapshot() for aid, p in policies.items()
                            if hasattr(p, "code_checks")}
    score_path = os.path.splitext(log_path)[0] + ".score.json"
    with open(score_path, "w", encoding="utf-8") as f:
        json.dump(score, f, ensure_ascii=False, indent=2, default=str)
    agent_scores = "  ".join(f"{a}={v['score']}" for a, v in score["agents"].items())
    print(f"\nScore: total={score['total']}  team={score['team']['score']}  {agent_scores}")
    print(f"Wrote score: {score_path}")
    print(f"Wrote code checks: {checks_path}")
    context_path = os.path.splitext(log_path)[0] + '.context.json'
    with open(context_path, 'w', encoding='utf-8') as context_file:
        json.dump({aid: getattr(p, '_conversation_history', []) for aid, p in policies.items()},
                  context_file, ensure_ascii=False, indent=2)
    emit_debug('episode_finished', cleared=score['team']['cleared'], failure=env.failure, total=score['total'])


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", default="upstage/solar-pro4")
    parser.add_argument("--steps", type=int, default=40)
    parser.add_argument("--base-url", default="https://openrouter.ai/api/v1")
    parser.add_argument("--api-key-file", default="key.txt", help="API key file (relative paths use the project directory)")
    parser.add_argument("--reasoning-effort", default=None, help="passed through as extra_params.reasoning_effort (e.g. 'low' for Groq gpt-oss models)")
    parser.add_argument("--out", default=None, help="manifest.jsonl output path (default: benchmark_runs/<timestamp>.jsonl)")
    parser.add_argument("--map-seed", type=int, default=None, help="mapgen으로 이 시드의 무작위 맵을 만들어 사용 (기본 GenConfig)")
    parser.add_argument("--map-file", default=None, help="저장된 맵 JSON(python -m mapgen --save로 생성)을 사용")
    parser.add_argument("--environment", choices=("map", "sequence_rooms"), default="map")
    parser.add_argument("--sequence-seed", type=int, default=42)
    parser.add_argument("--pads-per-room", type=int, default=5)
    parser.add_argument("--presses-per-room", type=int, default=3)
    parser.add_argument("--max-resets", type=int, default=None, help="허용 리셋 횟수 (생략하면 제한 없음)")
    parser.add_argument('--debug', action='store_true', help='실시간 상세 로그 출력 및 .debug.jsonl 저장')
    parser.add_argument("--policy", choices=POLICY_CHOICES, default="code",
                        help="code(기본, LLM이 정책 코드 작성 - API 키 필요) 또는 API 키 없이 실행 확인용 규칙 기반 정책")
    args = parser.parse_args()
    if args.steps < 1:
        parser.error("--steps must be at least 1")
    if args.environment == "sequence_rooms" and (args.map_file or args.map_seed is not None):
        parser.error("sequence_rooms cannot be combined with --map-file or --map-seed")
    if not 1 <= args.presses_per_room <= args.pads_per_room <= 5:
        parser.error("need 1 <= presses-per-room <= pads-per-room <= 5")
    if args.max_resets is not None and args.max_resets < 0:
        parser.error("--max-resets must be nonnegative")

    map_spec = None
    if args.map_file:
        map_spec = MapSpec.load(args.map_file)
    elif args.map_seed is not None:
        map_spec = generate_map(args.map_seed)

    api_key = read_secret(args.api_key_file) if args.policy == "code" else ""
    extra_params = {"reasoning_effort": args.reasoning_effort} if args.reasoning_effort else {}

    out_path = args.out
    if not out_path:
        os.makedirs(RUNS_DIR, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = os.path.join(RUNS_DIR, f"{timestamp}.jsonl")

    run_episode(args.model, args.base_url, api_key, extra_params, args.steps, out_path, map_spec, args.policy,
                args.environment, args.sequence_seed, args.pads_per_room, args.presses_per_room, args.max_resets, args.debug)
    print(f"\nWrote manifest: {out_path}")
    print(f"Score it with: python maci_judge.py {out_path}")


if __name__ == "__main__":
    main()
