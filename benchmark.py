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
    python benchmark.py --environment sequence_rooms --controller central --model upstage/solar-pro4  # LLM 하나가 A/B 모두 조종
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import threading
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
ENVIRONMENT_DIR = os.path.join(HERE, "enviroment")
if ENVIRONMENT_DIR not in sys.path:
    sys.path.insert(0, ENVIRONMENT_DIR)  # enviroment/*.py use flat sibling imports (from policy import ...)

from enviroment import Environment  # noqa: E402
from policy import (REASONING_SUMMARY_FIELD, CentralCodePolicy, CodePolicy, agent_reasoning_params, HybridPolicy, NoopPolicy, PolicyGaveUp,  # noqa: E402
                    RandomPolicy, ToolUsePolicy)
from scoring import ScoreConfig, clear_step, score_episode  # noqa: E402
import providers  # noqa: E402
from context_memory import ContextMemory, ContextConfig  # noqa: E402
from mapgen import MapSpec, generate_map  # noqa: E402
from mapgen.builder import build_environment  # noqa: E402
from world_core import GameMap  # noqa: E402
from sequence_rooms import build_sequence_rooms  # noqa: E402
from blind_code import build_blind_code  # noqa: E402
from curriculum import build_curriculum  # noqa: E402
from environment_prompt import PROMPT_CONTRACT, environment_description  # noqa: E402

RUNS_DIR = os.path.join(HERE, "benchmark_runs")
# 점수 가중치 파일. 있으면 기본값(scoring.ScoreConfig) 대신 사용하고, 사용한 값은 score.json에 함께 저장
SCORE_CONFIG_PATH = os.path.join(HERE, "scoring_weights.json")
# decentralized: 에이전트마다 LLM 하나 (메시지로 협력) / central: LLM 하나가 모든 에이전트를 조종
CONTROLLER_CHOICES = ("decentralized", "central")


def load_score_config(path: str | None = None) -> ScoreConfig:
    path = path or (SCORE_CONFIG_PATH if os.path.isfile(SCORE_CONFIG_PATH) else None)
    return ScoreConfig.load(path) if path else ScoreConfig()


# 에이전트 설명에 붙는 감점 안내 (실제 채점에 쓰는 가중치에서 만듦)
# 비용 규칙 한 줄 (정보 계약 v2에서는 --disclose-costs일 때만 에이전트에게 알림. 채점은 알리든 말든 같음)
def penalty_description(config: ScoreConfig) -> str:
    return (f" Costs: output tokens beyond {config.token_allowance:,} per agent cost "
            f"{config.token_penalty_per_1000:g} point per 1,000 (at most {-config.token_penalty_cap:g}); each request "
            f"whose prompt exceeds {config.context_penalty_start:,} tokens costs (prompt-{config.context_penalty_start:,})^2/"
            f"{config.context_penalty_divisor:,.0f} points (at most {-config.context_penalty_cap:g} in total); "
            f"invalid actions {config.invalid_action_penalty:g}, "
            f"failing code {config.code_failure_penalty:g}, no-effect interactions {config.failed_attempt_penalty:g} each.")


# 중앙집중 모드에서 모델 하나가 받는 과제 설명: 에이전트별 설명을 모두 담음
def central_task_description(task_descriptions: dict[str, str]) -> str:
    parts = [f"You control all agents at once: {', '.join(task_descriptions)}. "
             "Below is each agent's own task description, written from that agent's point of view."]
    parts += [f"[Agent {aid}]\n{text}" for aid, text in task_descriptions.items()]
    return "\n\n".join(parts)


def is_local_endpoint(base_url):
    return urlparse(base_url).hostname in ('127.0.0.1', 'localhost', '::1')


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


def build_episode(reveal_goal: bool = True, clue_hints: bool = True):
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
    # 장치 수준 힌트 (위치, 전략은 쓰지 않음 - scenarios/common.py 정보 전달 원칙과 같음)
    # clue_hints=False면 힌트 단서를 두지 않음 (힌트 없는 버전, scenarios/common.py without_clue_hints와 같음)
    if clue_hints:
        hint = {"hint": "The gate opens only while every plate linked to it is occupied at the same time."}
        env.add_clue("hint_a", x=70, y=440, content=hint, hidden=False)
        env.add_clue("hint_b", x=430, y=60, content=hint, hidden=False)

    env.add_agent("A", x=40, y=460)
    env.add_agent("B", x=460, y=40)

    task_descriptions = {aid: environment_description(aid, list(env.agents), 500, 500)
                              + (" Goal: unlock door 'gate'." if reveal_goal else '')
                         for aid in env.agents}
    return env, task_descriptions


# 기본 맵(build_episode)의 클리어 조건: gate가 열린 순간 (형식은 scoring._matches 참고)
GATE_OBJECTIVES = [{"type": "door_unlocked", "door_id": "gate"}]


# map_spec이 있으면 mapgen으로 만든 맵, 없으면 기본 압력판 맵(build_episode)으로 진행
# --policy 선택지. code만 LLM(API 키 필요)을 쓰고, 나머지는 API 키 없이 파이프라인 전체(맵/로그/
# 채점)가 도는지 확인하는 용도의 규칙 기반 정책
POLICY_CHOICES = ("code", "hybrid", "tooluse", "random", "noop")


def make_policy(kind: str, model: str, description: str, base_url: str, api_key: str, extra_params: dict,
                interact_radius: float, env_change_cap: int = 0):
    if kind in ('code', 'hybrid'):
        # Keep old command lines usable, but every LLM run must submit reusable code.
        policy = CodePolicy(model=model, task_description=description, base_url=base_url,
                            api_key=api_key, extra_params=extra_params, env_change_cap=env_change_cap)
        if is_local_endpoint(base_url):
            policy.client = policy.client.with_options(timeout=60, max_retries=0)
        return policy
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
                max_resets: int | None = None, debug: bool = False, reveal_goal: bool = True,
                reward_visible: bool = False, context_max_tokens: int = 64_000,
                solo_agent: str | None = None, controller: str = "decentralized",
                score_config: ScoreConfig | None = None, policy_factory=None, env_change_cap: int = 0,
                disclose_costs: bool = False,
                clue_hints: bool = True) -> None:
    # policy_factory(agent_id, task_description) -> Policy: 정책을 밖에서 만들어 넣을 때 (예: play.py의 사람 플레이어).
    # 이때 policy_kind는 로그의 model 칸에 남길 이름으로만 쓰임
    if steps < 1:
        raise ValueError("steps must be at least 1")
    if controller not in CONTROLLER_CHOICES:
        raise ValueError(f"unknown controller: {controller!r} (expected one of {CONTROLLER_CHOICES})")
    if controller == "central" and policy_kind not in ("code", "hybrid"):
        raise ValueError("the central controller needs an LLM code policy (--policy code)")
    if controller == "central" and solo_agent is not None:
        raise ValueError("the central controller cannot be combined with a solo-agent run")
    score_config = score_config or ScoreConfig()
    if environment_kind == "curriculum":
        if map_spec is not None:
            raise ValueError('curriculum cannot be combined with a map')
        env, task_descriptions, objectives = build_curriculum(
            seed=sequence_seed, max_turns=steps, reveal_goal=reveal_goal)
    elif environment_kind == "blind_code":
        if map_spec is not None:
            raise ValueError('blind_code cannot be combined with a map')
        env, task_descriptions, objectives = build_blind_code(
            seed=sequence_seed, max_turns=steps, reveal_goal=reveal_goal)
    elif environment_kind == "sequence_rooms":
        if map_spec is not None:
            raise ValueError("sequence_rooms cannot be combined with a map")
        env, task_descriptions, objectives = build_sequence_rooms(
            seed=sequence_seed, pads_per_room=pads_per_room, presses_per_room=presses_per_room,
            max_turns=steps, max_resets=max_resets, reveal_goal=reveal_goal)
    elif environment_kind != "map":
        raise ValueError(f"unknown environment: {environment_kind}")
    elif map_spec is not None:
        clue_hints = clue_hints and (map_spec.config or {}).get("clue_hints", True)  # _nohint 맵 파일이면 False로 기록
        if not clue_hints:  # 힌트 없는 버전: 단서의 규칙 문장을 지우고 퍼즐 자료만 남김
            from scenarios.common import without_clue_hints
            map_spec = without_clue_hints(map_spec)
        env, task_descriptions, objectives = build_environment(map_spec, reveal_goal=reveal_goal)
        # 시나리오 맵이 점수를 관찰 피드백으로 주도록 정했으면 (rules.show_reward) 그대로 따름
        reward_visible = reward_visible or bool((getattr(map_spec, "rules", None) or {}).get("show_reward"))
    else:
        env, task_descriptions = build_episode(reveal_goal=reveal_goal, clue_hints=clue_hints)
        objectives = GATE_OBJECTIVES

    if solo_agent is not None and solo_agent not in env.agents:
        raise ValueError(f'Unknown solo agent: {solo_agent}')

    if reward_visible:
        def reward_for(agent_id):
            score = score_episode(env, max_steps=steps, objectives=objectives, config=score_config)
            return {'individual_score': score['agents'][agent_id]['score'],
                    'team_score': score['team']['score'], 'total_score': score['total']}
        env.reward_provider = reward_for
    reward_description = (
        ' observation.reward holds your cumulative individual_score, team_score and total_score.'
        if reward_visible else '')
    env_change_description = (
        f" Notable changes around you (newly seen objects, object state changes, inventory changes, notices, or an "
        f"invalid/no-effect action result) also trigger an LLM review, at most {env_change_cap} times per episode; "
        "you may keep your current code in such a review." if env_change_cap > 0 else "")
    task_descriptions = {aid: description + reward_description
                              + (penalty_description(score_config) if disclose_costs else '')
                              + env_change_description
                         for aid, description in task_descriptions.items()}

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
    compression_path = os.path.splitext(log_path)[0] + '.context_compressions.jsonl'
    archive_path = os.path.splitext(log_path)[0] + '.context_archive.jsonl'
    observation_path = os.path.splitext(log_path)[0] + '.observations.jsonl'
    # 에이전트 LLM이 응답마다 내놓은 추론(프로바이더가 돌려준 경우). tool_call_ids로 대화 이력의 응답과 이어짐
    reasoning_path = os.path.splitext(log_path)[0] + '.agent_reasoning.jsonl'
    for path in (compression_path, archive_path, observation_path, reasoning_path):
        with open(path, 'w', encoding='utf-8'):
            pass
    context_lock = threading.Lock()

    def write_context(path, agent_id, record):
        with context_lock, open(path, 'a', encoding='utf-8') as destination:
            destination.write(json.dumps({'agent': agent_id, **record}, ensure_ascii=False) + '\n')

    def save_snapshot(step, observations):
        with open(observation_path, 'a', encoding='utf-8') as destination:
            for aid, observation in observations.items():
                destination.write(json.dumps({'step': step, 'agent': aid,
                                              'observation': observation}, ensure_ascii=False, default=str) + '\n')
            destination.flush()

    env.snapshot_sink = save_snapshot

    central = None
    if controller == "central":
        central = CentralCodePolicy(model, central_task_description(task_descriptions), list(env.agents),
                                    base_url=base_url, api_key=api_key, extra_params=extra_params)
        if is_local_endpoint(base_url):
            central.client = central.client.with_options(timeout=60, max_retries=0)
        central._context_memory = ContextMemory(ContextConfig(max_tokens=context_max_tokens, show_costs=disclose_costs))
        central.context_memory.sink = lambda event: write_context(compression_path, 'central', event)
        central.conversation_history.sink = lambda message: write_context(archive_path, 'central', {'message': message})
        central.conversation_history.reasoning_sink = lambda record: write_context(
            reasoning_path, 'central', {'step': env.step_count, **record})
        central.code_checks.sink = lambda event: write_check('central', event)
        central.debug_sink = lambda event, details: emit_debug(event, 'central', **details)
        env.joint_policy = central
    for agent_id, description in task_descriptions.items():
        if central is not None:
            policies[agent_id] = central
            env.agents[agent_id].set_policy(central)
            continue
        if solo_agent == agent_id:
            description += (' This is a single-active-agent control run. Other agents '
                            'always take noop actions and will not assist or reply.')
        policies[agent_id] = (NoopPolicy() if solo_agent is not None and agent_id != solo_agent else
                              policy_factory(agent_id, description) if policy_factory is not None else
                              make_policy(policy_kind, model, description, base_url, api_key, extra_params,
                                          env.interact_radius, env_change_cap))
        if hasattr(policies[agent_id], 'client'):
            policies[agent_id]._context_memory = ContextMemory(ContextConfig(max_tokens=context_max_tokens,
                                                                             show_costs=disclose_costs))
            policies[agent_id].context_memory.sink = lambda event, aid=agent_id: write_context(compression_path, aid, event)
            policies[agent_id].conversation_history.sink = lambda message, aid=agent_id: write_context(archive_path, aid, {'message': message})
            policies[agent_id].conversation_history.reasoning_sink = lambda record, aid=agent_id: write_context(
                reasoning_path, aid, {'step': env.step_count, **record})
        checks = getattr(policies[agent_id], "code_checks", None)
        if checks is not None:
            checks.sink = lambda event, aid=agent_id: write_check(aid, event)
        policies[agent_id].debug_sink = lambda event, details, aid=agent_id: emit_debug(event, aid, **details)
        env.agents[agent_id].set_policy(policies[agent_id])

    # Observer-only state; this is never added to the agents' observations.
    def snapshot():
        return {"width": env.game_map.map_width, "height": env.game_map.map_height,
                "walls": env._walls(), "objects": list(env.objects.values()),
                **({'level_state': env.level_state()} if hasattr(env, 'level_state') else {})}

    os.makedirs(os.path.dirname(os.path.abspath(log_path)), exist_ok=True)
    scene_path = os.path.splitext(log_path)[0] + ".scene.json"
    with open(scene_path, "w", encoding="utf-8") as scene:
        json.dump({"environment": environment_kind, "world": snapshot(), "reveal_goal": reveal_goal,
                   "clue_hints": clue_hints,
                   "reward_visible": reward_visible,
                   "controller": controller,
                   "score": score_episode(env, max_steps=steps, objectives=objectives, config=score_config),
                   "agents": [{"agent": aid, "position": [a.x, a.y], "facing": a.facing}
                              for aid, a in env.agents.items()]}, scene, ensure_ascii=False)

    stopped = None
    with open(log_path, "w", encoding="utf-8") as f:
        for step in range(1, steps + 1):
            emit_debug('step_started', next_step=step)
            try:
                env.step()
            except PolicyGaveUp as exc:
                # 코드 복구가 계속 실패하면(예: context 한도 초과) 무한히 기다리지 않고 미완료로 끝냄
                print(f"\nSTOPPED at step {step}: {exc}", flush=True)
                emit_debug('policy_gave_up', error=str(exc))
                stopped = str(exc)
                break

            decisions_by_agent = {d["agent_id"]: d for d in env.decision_log.filter(step=step)}
            step_messages = [m for m in env.message_log.entries if m["step"] == step]

            record = {
                "step": step,
                "task": dict(task_descriptions),
                "map_seed": sequence_seed if environment_kind in ("sequence_rooms", "blind_code", "curriculum") else (map_spec.seed if map_spec is not None else None),
                "environment": environment_kind,
                "reveal_goal": reveal_goal,
                "clue_hints": clue_hints,
                "reward_visible": reward_visible,
                "solo_agent": solo_agent,
                "controller": controller,
                "prompt_contract": PROMPT_CONTRACT,
                "disclose_costs": disclose_costs,
                "agent_reasoning": (((extra_params or {}).get("extra_body") or {}).get("reasoning", {}).get("effort")
                                    or (extra_params or {}).get("reasoning_effort")),
                "api_host": urlparse(base_url).hostname,
                "route": (((extra_params or {}).get("extra_body") or {}).get("provider") or {}).get("only"),
                "reasoning_summary": bool((extra_params or {}).get(REASONING_SUMMARY_FIELD)),
                "configured_steps": steps,
                "world": snapshot(),
                "failure": env.failure,
                "objectives": objectives,
                "cleared": clear_step(env.event_log.entries, objectives) is not None,
                "messages": step_messages,
                "events": env.event_log.filter(step=step),
                "score": score_episode(env, max_steps=steps, objectives=objectives, config=score_config),
                "agents": [
                    {
                        "agent": agent_id,
                        "model": ('noop' if solo_agent is not None and agent_id != solo_agent else
                                  model if policy_kind in ("code", "hybrid") else policy_kind),
                        "position": [env.agents[agent_id].x, env.agents[agent_id].y],
                        "facing": env.agents[agent_id].facing,
                        "spatial_state": env.agents[agent_id].spatial_state(),
                        # 진행 정체 지표 (기록만): 마지막 진행/새 발견 이후 step 수, 같은 행동 연속 횟수
                        "progress": env.progress_status(agent_id) if hasattr(env, "progress_status") else None,
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
                            "context_compression": (policies[agent_id].context_stats
                                                    if hasattr(policies[agent_id], 'client') else None),
                            "code_turns": getattr(policies[agent_id], 'code_turns', 0),
                            "next_review_step": getattr(policies[agent_id], 'next_review_step', None),
                            "message_interrupt": getattr(policies[agent_id], 'last_message_interrupt', None),
                            "token_usage": getattr(policies[agent_id], 'token_usage', {}),
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
    score = score_episode(env, max_steps=steps, objectives=objectives, config=score_config)
    score["code_checks"] = {aid: p.code_checks.snapshot() for aid, p in policies.items()
                            if hasattr(p, "code_checks")}
    score["controller"] = controller
    score["stopped"] = stopped
    score["score_config"] = score_config.to_dict()
    score_path = os.path.splitext(log_path)[0] + ".score.json"
    with open(score_path, "w", encoding="utf-8") as f:
        json.dump(score, f, ensure_ascii=False, indent=2, default=str)
    agent_scores = "  ".join(f"{a}={v['score']}" for a, v in score["agents"].items())
    print(f"\nScore: total={score['total']}  team={score['team']['score']}  {agent_scores}")
    print(f"Wrote score: {score_path}")
    print(f"Wrote code checks: {checks_path}")
    context_path = os.path.splitext(log_path)[0] + '.context.json'
    with open(context_path, 'w', encoding='utf-8') as context_file:
        json.dump({aid: getattr(getattr(p, '_conversation_history', []), 'archive',
                              getattr(p, '_conversation_history', [])) for aid, p in policies.items()},
                  context_file, ensure_ascii=False, indent=2)
    with open(os.path.splitext(log_path)[0] + '.working_context.json', 'w', encoding='utf-8') as file:
        json.dump({aid: getattr(p, '_conversation_history', []) for aid, p in policies.items()},
                  file, ensure_ascii=False, indent=2)
    emit_debug('episode_finished', cleared=score['team']['cleared'], failure=env.failure, total=score['total'])


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", default="upstage/solar-pro4")
    parser.add_argument("--steps", type=int, default=40)
    providers.add_arguments(parser)
    parser.add_argument("--no-reasoning-summary", action="store_true",
                        help="do not ask agents for a reasoning summary with each answer (by default they write one; "
                             "it is saved to <out>.agent_reasoning.jsonl, kept out of the conversation, and not "
                             "counted toward the output-token penalty)")
    parser.add_argument("--agent-reasoning", choices=("low", "medium", "high"), default=None,
                        help="turn on the agent LLM's reasoning and stop forcing tool calls (tool_choice=auto) so "
                             "models such as Anthropic's can think; the reasoning is saved to <out>.agent_reasoning.jsonl. "
                             "Changes behavior and cost, so compare only with runs that used the same setting")
    parser.add_argument("--reasoning-effort", default=None, help="passed through as extra_params.reasoning_effort (e.g. 'low' for Groq gpt-oss models)")
    parser.add_argument("--route", default=None,
                        help="OpenRouter only: comma-separated provider endpoints to pin, no fallback "
                             "(e.g. openai/flex for OpenAI's half-price flex tier)")
    parser.add_argument("--out", default=None, help="manifest.jsonl output path (default: benchmark_runs/<timestamp>.jsonl)")
    parser.add_argument("--map-seed", type=int, default=None, help="mapgen으로 이 시드의 무작위 맵을 만들어 사용 (기본 GenConfig)")
    parser.add_argument("--map-file", default=None, help="저장된 맵 JSON(python -m mapgen --save로 생성)을 사용")
    parser.add_argument("--environment", choices=("map", "sequence_rooms", "blind_code", "curriculum"), default="map")
    parser.add_argument("--sequence-seed", type=int, default=42)
    parser.add_argument("--pads-per-room", type=int, default=5)
    parser.add_argument("--presses-per-room", type=int, default=3)
    parser.add_argument("--max-resets", type=int, default=None, help="허용 리셋 횟수 (생략하면 제한 없음)")
    parser.add_argument('--debug', action='store_true', help='실시간 상세 로그 출력 및 .debug.jsonl 저장')
    parser.add_argument('--hide-goal', action='store_true', help='에이전트 초기 설명에서 목표 숨기기 (최소 규칙 유지)')
    parser.add_argument('--no-clue-hints', action='store_true',
                        help='단서에서 장치 규칙 문장을 빼고 퍼즐 자료만 남김 (기본 맵과 지도 파일 맵에 적용)')
    parser.add_argument('--show-reward', action='store_true', help='Include cumulative numeric scores in agent observations')
    parser.add_argument('--solo-agent', choices=('A', 'B'), help='Run only this agent; all other agents take noop actions')
    parser.add_argument('--context-max-tokens', type=int, default=64_000,
                        help='Advisory context pressure threshold (UTF-8 byte estimate + output reserve); the model decides whether to compress (default: 64000)')
    parser.add_argument("--controller", choices=CONTROLLER_CHOICES, default="decentralized",
                        help="decentralized: one LLM per agent (messages); central: one LLM controls every agent")
    parser.add_argument("--disclose-costs", action="store_true",
                        help="tell agents the cost rules (token/context/mistake penalties); scoring is the same either way")
    parser.add_argument("--env-change-cap", type=int, default=0,
                        help="re-invoke the LLM when the surroundings change, at most this many times per agent (0: off)")
    parser.add_argument("--score-config", default=None,
                        help="score weight JSON (default: scoring_weights.json if present, else built-in weights)")
    parser.add_argument("--policy", choices=POLICY_CHOICES, default="code",
                        help="code: reusable LLM code required; hybrid: compatibility alias for code; tooluse/random/noop: no API")
    args = parser.parse_args()
    if args.steps < 1:
        parser.error("--steps must be at least 1")
    if args.env_change_cap < 0:
        parser.error("--env-change-cap must be nonnegative")
    if args.context_max_tokens < 1:
        parser.error('--context-max-tokens must be positive')
    if args.environment != "map" and (args.map_file or args.map_seed is not None):
        parser.error("room environments cannot be combined with --map-file or --map-seed")
    if not 1 <= args.presses_per_room <= args.pads_per_room <= 5:
        parser.error("need 1 <= presses-per-room <= pads-per-room <= 5")
    if args.max_resets is not None and args.max_resets < 0:
        parser.error("--max-resets must be nonnegative")
    if args.controller == "central" and (args.policy not in ("code", "hybrid") or args.solo_agent):
        parser.error("--controller central needs --policy code and cannot be combined with --solo-agent")
    try:
        score_config = load_score_config(args.score_config)
    except (OSError, ValueError, TypeError) as exc:
        parser.error(f"--score-config: {exc}")

    map_spec = None
    if args.map_file:
        map_spec = MapSpec.load(args.map_file)
    elif args.map_seed is not None:
        map_spec = generate_map(args.map_seed)

    api_key = providers.read_key(args) if args.policy in ("code", "hybrid") else ""
    args.model = providers.model_name(args, args.model)
    args.base_url = providers.base_url(args)
    extra_params = {"reasoning_effort": args.reasoning_effort} if args.reasoning_effort else {}
    if args.agent_reasoning:
        extra_params.update(providers.reasoning_params(args, args.agent_reasoning, agent_reasoning_params))
    if args.route:
        route = [name.strip() for name in args.route.split(",") if name.strip()]
        extra_params.setdefault("extra_body", {})["provider"] = {"only": route, "allow_fallbacks": False}
    if not args.no_reasoning_summary:
        extra_params[REASONING_SUMMARY_FIELD] = True

    out_path = args.out
    if not out_path:
        os.makedirs(RUNS_DIR, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = os.path.join(RUNS_DIR, f"{timestamp}.jsonl")

    run_episode(args.model, args.base_url, api_key, extra_params, args.steps, out_path, map_spec, args.policy,
                args.environment, args.sequence_seed, args.pads_per_room, args.presses_per_room, args.max_resets, args.debug,
                reveal_goal=not args.hide_goal, reward_visible=args.show_reward,
                context_max_tokens=args.context_max_tokens, solo_agent=args.solo_agent,
                controller=args.controller, score_config=score_config, env_change_cap=args.env_change_cap,
                disclose_costs=args.disclose_costs,
                clue_hints=not args.no_clue_hints)
    print(f"\nWrote manifest: {out_path}")
    print(f"Score it with: python maci_judge.py {out_path}")


if __name__ == "__main__":
    main()
