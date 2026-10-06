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

RUNS_DIR = os.path.join(HERE, "benchmark_runs")


def read_secret(env_var: str, filename: str) -> str:
    """Reads a secret from an env var first, falling back to a local file
    (e.g. key.txt) resolved relative to the current working directory."""
    value = os.environ.get(env_var, "").strip()
    if value:
        return value
    try:
        with open(filename, encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        raise SystemExit(
            f"Missing credential: set the {env_var} environment variable, "
            f"or create {filename} containing just the key."
        )


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
                map_spec: MapSpec = None, policy_kind: str = "code") -> None:
    if map_spec is not None:
        env, task_descriptions, objectives = build_environment(map_spec)
    else:
        env, task_descriptions = build_episode()
        objectives = GATE_OBJECTIVES

    policies = {}
    for agent_id, description in task_descriptions.items():
        policies[agent_id] = make_policy(policy_kind, model, description, base_url, api_key, extra_params,
                                         env.interact_radius)
        env.agents[agent_id].set_policy(policies[agent_id])

    with open(log_path, "w", encoding="utf-8") as f:
        for step in range(1, steps + 1):
            env.step()

            decisions_by_agent = {d["agent_id"]: d for d in env.decision_log.filter(step=step)}
            step_messages = [m for m in env.message_log.entries if m["step"] == step]

            record = {
                "step": step,
                "task": dict(task_descriptions),
                "map_seed": map_spec.seed if map_spec is not None else None,
                "objectives": objectives,
                "cleared": clear_step(env.event_log.entries, objectives) is not None,
                "messages": step_messages,
                "events": env.event_log.filter(step=step),
                "agents": [
                    {
                        "agent": agent_id,
                        "model": model if policy_kind == "code" else policy_kind,
                        "position": [env.agents[agent_id].x, env.agents[agent_id].y],
                        "spatial_state": env.agents[agent_id].spatial_state(),
                        "generated_code": getattr(policies[agent_id], "generated_code", None),
                        "decision": {
                            "action": decisions_by_agent.get(agent_id, {}).get("action"),
                            "final_action": decisions_by_agent.get(agent_id, {}).get("final_action"),
                            "overridden": decisions_by_agent.get(agent_id, {}).get("overridden", False),
                            "policy_error": getattr(policies[agent_id], "last_error", None),
                            # CodePolicy가 이번 step에 stuck으로 코드를 재생성했으면 {"step", "reason"}
                            "replan": getattr(policies[agent_id], "last_replan", None),
                        },
                    }
                    for agent_id in task_descriptions
                ],
            }
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

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
                print(f"\nFAILED at step {step}: trap '{env.failure['object_id']}' triggered by "
                      f"{env.failure['agent_id']} sealed {env.failure['sealed_doors']}.")
                break

    # 회차 점수: manifest는 maci_judge.py가 step 단위로 읽으므로 같은 파일에 섞지 않고 옆에 따로 저장
    score = score_episode(env, max_steps=steps, objectives=objectives)
    score_path = os.path.splitext(log_path)[0] + ".score.json"
    with open(score_path, "w", encoding="utf-8") as f:
        json.dump(score, f, ensure_ascii=False, indent=2, default=str)
    agent_scores = "  ".join(f"{a}={v['score']}" for a, v in score["agents"].items())
    print(f"\nScore: total={score['total']}  team={score['team']['score']}  {agent_scores}")
    print(f"Wrote score: {score_path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", default="upstage/solar-pro4")
    parser.add_argument("--steps", type=int, default=40)
    parser.add_argument("--base-url", default="https://openrouter.ai/api/v1")
    parser.add_argument("--api-key-env", default="OPENROUTER_API_KEY")
    parser.add_argument("--api-key-file", default="key.txt")
    parser.add_argument("--reasoning-effort", default=None, help="passed through as extra_params.reasoning_effort (e.g. 'low' for Groq gpt-oss models)")
    parser.add_argument("--out", default=None, help="manifest.jsonl output path (default: benchmark_runs/<timestamp>.jsonl)")
    parser.add_argument("--map-seed", type=int, default=None, help="mapgen으로 이 시드의 무작위 맵을 만들어 사용 (기본 GenConfig)")
    parser.add_argument("--map-file", default=None, help="저장된 맵 JSON(python -m mapgen --save로 생성)을 사용")
    parser.add_argument("--policy", choices=POLICY_CHOICES, default="code",
                        help="code(기본, LLM이 정책 코드 작성 - API 키 필요) 또는 API 키 없이 실행 확인용 규칙 기반 정책")
    args = parser.parse_args()

    map_spec = None
    if args.map_file:
        map_spec = MapSpec.load(args.map_file)
    elif args.map_seed is not None:
        map_spec = generate_map(args.map_seed)

    api_key = read_secret(args.api_key_env, args.api_key_file) if args.policy == "code" else ""
    extra_params = {"reasoning_effort": args.reasoning_effort} if args.reasoning_effort else {}

    out_path = args.out
    if not out_path:
        os.makedirs(RUNS_DIR, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = os.path.join(RUNS_DIR, f"{timestamp}.jsonl")

    run_episode(args.model, args.base_url, api_key, extra_params, args.steps, out_path, map_spec, args.policy)
    print(f"\nWrote manifest: {out_path}")
    print(f"Score it with: python maci_judge.py {out_path}")


if __name__ == "__main__":
    main()
