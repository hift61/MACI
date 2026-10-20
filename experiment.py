"""MACI 최종 벤치마크 실행기: 모델 x 조건 x 시드를 같은 설정으로 반복 실행하고 집계한다.

조건 (--controllers)
  decentralized : 에이전트마다 같은 모델의 LLM이 하나씩. 각자 자기 방만 보고 메시지로 협력
  central       : LLM 하나가 두 에이전트의 관찰을 모두 보고 동시에 조종 (소통이 필요 없는 상한선)
같은 시드·반복 번호끼리 두 조건을 짝지어(paired) 비교하므로 퍼즐 난이도 차이가 상쇄된다.
집계는 로그에서 바로 계산되는 객관 지표만 쓴다 (판정 LLM 없음): 클리어 여부와 step, 리셋 원인,
잘못된 행동, 코드 오류, 메시지 수, 토큰. 성공률에는 Wilson 95% 신뢰구간, 조건 비교에는 정확
McNemar 검정(짝지은 성공/실패의 불일치 쌍에 대한 이항검정)을 쓴다.

같은 --name으로 다시 실행하면 끝난 실행(.score.json 있음)은 건너뛰고 이어서 진행한다. 설정(환경,
번호판 수, step 제한, 점수 가중치)이 처음과 다르면 섞이지 않도록 거부한다.

Usage:
    python experiment.py --name pilot --models openai/gpt-6-luna --seeds 1-8
    python experiment.py --name pilot --models openai/gpt-6-luna,upstage/solar-mini4 --seeds 1-8 --repeats 2
    python experiment.py --name pilot --summarize          # 끝난 실행만 다시 집계
    python experiment.py --name smoke --policy tooluse --controllers decentralized --seeds 1-2   # API 없이 점검
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import traceback
from collections import Counter
from pathlib import Path

import benchmark
import providers

EXPERIMENTS_DIR = Path(benchmark.RUNS_DIR) / "experiments"
# 최종안 기본 프로토콜: 정보 비대칭이 있는 두 방 순서 퍼즐의 축소판 (순서 길이 4, 80 step)
PROTOCOL_DEFAULTS = dict(environment="sequence_rooms", pads_per_room=3, presses_per_room=2, steps=80)


def parse_seeds(text: str) -> list[int]:
    seeds = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            low, high = (int(v) for v in part.split("-", 1))
            if high < low:
                raise ValueError(f"bad seed range: {part}")
            seeds.extend(range(low, high + 1))
        else:
            seeds.append(int(part))
    if not seeds:
        raise ValueError("no seeds given")
    return list(dict.fromkeys(seeds))


def slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-") or "model"


RUN_NAME = re.compile(r"__s-?\d+__r(\d+)\.jsonl$")  # 실행 manifest (옆의 .debug.jsonl 등 부속 파일 제외)


def run_path(out_dir: Path, model: str, controller: str, seed: int, repeat: int) -> Path:
    return out_dir / f"{slug(model)}__{controller}__s{seed}__r{repeat}.jsonl"


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float] | tuple[None, None]:
    if n == 0:
        return None, None
    p = successes / n
    denominator = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denominator
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return max(0.0, center - margin), min(1.0, center + margin)


def mcnemar_exact(only_a: int, only_b: int) -> float:
    """Two-sided exact McNemar p-value from the discordant pair counts."""
    n = only_a + only_b
    if n == 0:
        return 1.0
    k = min(only_a, only_b)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def _unique_usage(agents: dict) -> tuple[dict, int]:
    """Sum token usage and code failures once per policy (central agents share one model)."""
    usage, failures, seen = Counter(), 0, set()
    for agent_id, data in agents.items():
        shared = tuple(data.get("token_usage", {}).get("shared_with") or (agent_id,))
        if shared in seen:
            continue
        seen.add(shared)
        for key, value in data.get("token_usage", {}).items():
            if isinstance(value, int):
                usage[key] += value
        failures += data.get("code_failures", 0)
    return dict(usage), failures


def summarize_run(path: Path) -> dict | None:
    if not path.is_file():
        return None
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not records:
        return None
    score_path = path.with_suffix(".score.json")
    score = json.loads(score_path.read_text(encoding="utf-8")) if score_path.is_file() else None
    first, last = records[0], records[-1]
    events = [event for record in records for event in record.get("events", [])]
    resets = Counter(event.get("reason") or "unknown" for event in events if event["type"] == "sequence_reset")
    usage, code_failures = _unique_usage(score["agents"]) if score else ({}, 0)
    return {
        "run": path.name,
        "model": first["agents"][0]["model"] if first.get("agents") else None,
        "controller": first.get("controller", "decentralized"),
        "seed": first.get("map_seed"),
        "complete": score is not None,
        "cleared": bool(score["team"]["cleared"]) if score else bool(last.get("cleared")),
        "clear_step": score["team"]["clear_step"] if score else None,
        "steps_run": last["step"],
        "resets": sum(resets.values()),
        "resets_wrong_order": resets.get("wrong_order", 0),
        "resets_simultaneous": resets.get("simultaneous_input", 0),
        "invalid_actions": sum(event["type"] == "invalid_action" for event in events),
        "code_failures": code_failures,
        "messages": sum(len(record.get("messages", [])) for record in records),
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "cached_prompt_tokens": usage.get("cached_prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "requests": usage.get("requests", 0),
        "total_score": score["total"] if score else None,
    }


def _mean(values):
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 3) if values else None


def aggregate(rows: list[dict]) -> list[dict]:
    groups: dict[tuple, list[dict]] = {}
    for row in rows:
        if row["complete"]:
            groups.setdefault((row["model"], row["controller"]), []).append(row)
    result = []
    for (model, controller), members in sorted(groups.items()):
        successes = sum(row["cleared"] for row in members)
        low, high = wilson_interval(successes, len(members))
        result.append({
            "model": model, "controller": controller, "runs": len(members), "successes": successes,
            "success_rate": round(successes / len(members), 3),
            "success_ci95": [round(low, 3), round(high, 3)],
            "mean_clear_step": _mean(row["clear_step"] for row in members if row["cleared"]),
            **{f"mean_{key}": _mean(row[key] for row in members) for key in (
                "steps_run", "resets", "resets_wrong_order", "resets_simultaneous", "invalid_actions",
                "code_failures", "messages", "prompt_tokens", "cached_prompt_tokens", "completion_tokens",
                "total_score")},
        })
    return result


def paired_comparison(rows: list[dict], controllers: list[str]) -> list[dict]:
    if len(controllers) < 2:
        return []
    a, b = controllers[0], controllers[1]
    outcomes: dict[tuple, dict] = {}
    for row in rows:
        if row["complete"]:
            repeat = int(RUN_NAME.search(row["run"]).group(1))
            outcomes.setdefault((row["model"], row["seed"], repeat), {})[row["controller"]] = row["cleared"]
    result = []
    for model in sorted({key[0] for key in outcomes}):
        pairs = [v for (m, _, _), v in outcomes.items() if m == model and a in v and b in v]
        counts = Counter((v[a], v[b]) for v in pairs)
        only_a, only_b = counts[(True, False)], counts[(False, True)]
        result.append({
            "model": model, "condition_a": a, "condition_b": b, "pairs": len(pairs),
            "both_cleared": counts[(True, True)], "only_a_cleared": only_a, "only_b_cleared": only_b,
            "neither_cleared": counts[(False, False)],
            "success_rate_difference": round((only_a - only_b) / len(pairs), 3) if pairs else None,
            "mcnemar_exact_p": round(mcnemar_exact(only_a, only_b), 4),
        })
    return result


def write_summary(out_dir: Path, controllers: list[str]) -> dict:
    rows = [summarize_run(path) for path in sorted(out_dir.glob("*.jsonl")) if RUN_NAME.search(path.name)]
    rows = [row for row in rows if row is not None]
    summary = {"runs": rows, "by_condition": aggregate(rows), "paired": paired_comparison(rows, controllers),
               "incomplete_runs": [row["run"] for row in rows if not row["complete"]]}
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    if rows:
        with (out_dir / "summary.csv").open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    return summary


def print_summary(summary: dict) -> None:
    print("\n=== 조건별 결과 ===")
    for row in summary["by_condition"]:
        low, high = row["success_ci95"]
        print(f"{row['model']:<40} {row['controller']:<14} 성공 {row['successes']}/{row['runs']} "
              f"({row['success_rate']:.0%}, 95% CI {low:.0%}~{high:.0%})  평균 리셋 {row['mean_resets']}  "
              f"메시지 {row['mean_messages']}  출력 토큰 {row['mean_completion_tokens']}")
    for row in summary["paired"]:
        print(f"\n[짝 비교] {row['model']}: {row['condition_a']} vs {row['condition_b']}  쌍 {row['pairs']}개  "
              f"둘 다 {row['both_cleared']} / {row['condition_a']}만 {row['only_a_cleared']} / "
              f"{row['condition_b']}만 {row['only_b_cleared']} / 둘 다 실패 {row['neither_cleared']}  "
              f"McNemar p={row['mcnemar_exact_p']}")
    if summary["incomplete_runs"]:
        print(f"\n미완료 실행 {len(summary['incomplete_runs'])}개는 집계에서 제외: {summary['incomplete_runs']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--name", required=True, help="실험 이름 (benchmark_runs/experiments/<name>/에 저장)")
    parser.add_argument("--models", default="openai/gpt-6-luna", help="쉼표로 구분한 모델 목록")
    parser.add_argument("--controllers", default="decentralized,central",
                        help="쉼표로 구분한 조건. 앞의 두 조건으로 짝 비교 (기본: decentralized,central)")
    parser.add_argument("--seeds", default="1-8", help="예: 1-8 또는 1,3,5")
    parser.add_argument("--repeats", type=int, default=1, help="같은 시드·조건 반복 횟수")
    parser.add_argument("--environment", choices=("sequence_rooms", "blind_code", "curriculum", "map"),
                        default=PROTOCOL_DEFAULTS["environment"])
    parser.add_argument("--pads-per-room", type=int, default=PROTOCOL_DEFAULTS["pads_per_room"])
    parser.add_argument("--presses-per-room", type=int, default=PROTOCOL_DEFAULTS["presses_per_room"])
    parser.add_argument("--steps", type=int, default=PROTOCOL_DEFAULTS["steps"])
    parser.add_argument("--policy", choices=("code", "tooluse", "random", "noop"), default="code")
    providers.add_arguments(parser)
    parser.add_argument("--reasoning-effort", default=None)
    parser.add_argument("--score-config", default=None)
    parser.add_argument("--env-change-cap", type=int, default=0, help="주변 환경 변화로 LLM을 다시 부르는 최대 횟수 (0: 끔)")
    parser.add_argument("--summarize", action="store_true", help="실행하지 않고 끝난 결과만 집계")
    parser.add_argument("--dry-run", action="store_true", help="실행 계획만 출력")
    args = parser.parse_args()

    controllers = [c.strip() for c in args.controllers.split(",") if c.strip()]
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    try:
        seeds = parse_seeds(args.seeds)
    except ValueError as exc:
        parser.error(str(exc))
    unknown = sorted(set(controllers) - set(benchmark.CONTROLLER_CHOICES))
    if unknown or not controllers:
        parser.error(f"unknown controllers: {unknown}")
    if args.policy != "code" and "central" in controllers:
        parser.error("the central controller needs --policy code")
    if args.repeats < 1 or args.steps < 1:
        parser.error("--repeats and --steps must be positive")
    if not 1 <= args.presses_per_room <= args.pads_per_room <= 5:
        parser.error("need 1 <= presses-per-room <= pads-per-room <= 5")

    out_dir = EXPERIMENTS_DIR / slug(args.name)
    if args.summarize:
        if not out_dir.is_dir():
            parser.error(f"no experiment at {out_dir}")
        print_summary(write_summary(out_dir, controllers))
        return

    score_config = benchmark.load_score_config(args.score_config)
    protocol = {"environment": args.environment, "pads_per_room": args.pads_per_room,
                "presses_per_room": args.presses_per_room, "steps": args.steps, "policy": args.policy,
                "reasoning_effort": args.reasoning_effort, "score_config": score_config.to_dict(),
                "env_change_cap": args.env_change_cap}
    if args.policy != "code":
        models = [args.policy]
    plan = [(model, controller, seed, repeat) for model in models for seed in seeds
            for repeat in range(1, args.repeats + 1) for controller in controllers]
    todo = [item for item in plan if not run_path(out_dir, *item).with_suffix(".score.json").is_file()]
    print(f"실험 {args.name}: 총 {len(plan)}회 중 남은 실행 {len(todo)}회 -> {out_dir}")
    if args.dry_run:
        for item in todo:
            print("  ", run_path(out_dir, *item).name)
        return

    out_dir.mkdir(parents=True, exist_ok=True)
    protocol_path = out_dir / "experiment.json"
    if protocol_path.is_file():
        saved = json.loads(protocol_path.read_text(encoding="utf-8"))["protocol"]
        if saved != protocol:
            raise SystemExit(f"{protocol_path}의 설정과 다릅니다. 다른 --name을 쓰세요.\n저장: {saved}\n현재: {protocol}")
    else:
        protocol_path.write_text(json.dumps({"protocol": protocol}, ensure_ascii=False, indent=2), encoding="utf-8")

    api_key = providers.read_key(args) if args.policy == "code" else ""
    args.base_url = providers.base_url(args)
    extra_params = {"reasoning_effort": args.reasoning_effort} if args.reasoning_effort else {}
    for index, (model, controller, seed, repeat) in enumerate(todo, 1):
        path = run_path(out_dir, model, controller, seed, repeat)
        print(f"\n[{index}/{len(todo)}] {path.name}", flush=True)
        try:
            benchmark.run_episode(
                providers.model_name(args, model), args.base_url, api_key, extra_params, args.steps, str(path),
                policy_kind=args.policy, environment_kind=args.environment, sequence_seed=seed,
                pads_per_room=args.pads_per_room, presses_per_room=args.presses_per_room,
                controller=controller, score_config=score_config, env_change_cap=args.env_change_cap)
        except Exception:
            # 한 실행의 실패(API 오류 등)로 실험 전체를 멈추지 않음. 다시 실행하면 이 실행부터 재시도
            path.with_suffix(".error.txt").write_text(traceback.format_exc(), encoding="utf-8")
            print(f"실행 실패: {path.with_suffix('.error.txt')}", flush=True)
    print_summary(write_summary(out_dir, controllers))
    print(f"\n집계: {out_dir / 'summary.json'} / {out_dir / 'summary.csv'}")


if __name__ == "__main__":
    main()
