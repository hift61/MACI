import json
from dataclasses import asdict, dataclass, field, fields
from token_usage import (CONTEXT_PENALTY_CAP, CONTEXT_PENALTY_DIVISOR, CONTEXT_PENALTY_END, CONTEXT_PENALTY_START,
                         TOKEN_ALLOWANCE, TOKEN_PENALTY_CAP, TOKEN_PENALTY_PER_1000, context_penalty)

# 한 회차(episode)가 끝난 Environment의 event_log/decision_log를 읽어 점수를 매김.
#   개인 점수: 각 에이전트가 일으킨 이벤트(물체 목격, 도움이 되는 동작 등)마다 부여
#   단체 점수: 클리어 여부와 클리어 시간으로 팀 전체에 부여
#   총점 = 개인 점수 합 + 단체 점수
# 같은 점수 항목을 반복해서 쌓는 것(레버를 계속 당기기, 판을 밟았다 내렸다 하기, 같은 문을 두 사람이 번갈아 열기)을
# 막기 위해 개인 가점은 팀 전체에서 (이벤트 종류, 대상 오브젝트) 조합마다 한 번만 줌. 그 첫 이벤트에 함께 이름이
# 오른 에이전트(함께 든 협력 물품, 함께 밟은 동기화 판)는 모두 받음. 감점은 매번 적용하되
# 잘못된 실행 감점(invalid action, 코드 오류, 헛된 시도)은 종류별 하한(cap)까지만 깎음.
# 가중치는 실질적 성공 중심: 탐색/중간 조작(목격, 레버, 문 열림, 판 밟기)은 작게,
# 과제를 실제로 진척시킨 성공(패널 풀기, 동시 진입, 배달 완료, 단계 완료, 넘겨주기, 클리어)은 크게.

# 시도로 세는 상호작용 action type -> 그 시도가 성공했을 때 같은 step에 남는 이벤트 종류
# (press_button은 별도 이벤트가 없어 연결된 문의 상태 변화로 판정)
ATTEMPT_EFFECTS = {
    "pick_up": {"item_picked_up"},
    "drop": {"item_dropped"},
    "use_key": {"door_unlocked", "chest_opened"},  # chest_opened: 시나리오 맵의 상자
    "press_button": {"door_unlocked", "door_locked", "number_accepted",  # number_accepted: sequence_rooms 번호판
                     "keypad_input"},  # keypad_input: 시나리오 맵의 패널 버튼 (scenarios/engine.py)
    "pull_lever": {"lever_pulled"},
}


@dataclass
class ScoreConfig:
    token_allowance: int = TOKEN_ALLOWANCE
    token_penalty_per_1000: float = TOKEN_PENALTY_PER_1000
    token_penalty_cap: float = TOKEN_PENALTY_CAP          # 출력 토큰 감점의 에이전트당 하한
    # 긴 context 감점: 압축 후 실제로 보낸 prompt가 start를 넘는 LLM 요청마다 (min(prompt, end) - start)^2 / divisor
    context_penalty_start: int = CONTEXT_PENALTY_START
    context_penalty_end: int = CONTEXT_PENALTY_END
    context_penalty_divisor: float = CONTEXT_PENALTY_DIVISOR
    context_penalty_cap: float = CONTEXT_PENALTY_CAP      # 긴 context 감점의 에이전트당 하한
    # ---- 개인 점수 (대상 오브젝트마다 한 번) ----
    seen_points: float = 0.1                    # 물체를 처음 목격 (탐색은 협력이 아니므로 작게)
    seen_points_by_type: dict = field(default_factory=lambda: {"clue": 0.5})  # 종류별로 다르게 줄 때
    pickup_points: float = 1.0                  # normal 물품/열쇠 습득
    coop_pickup_points: float = 10.0            # coop 물품 습득 (함께 들어준 에이전트도 같은 점수)
    lever_points: float = 0.5                   # 레버 당기기 (중간 조작)
    door_unlock_points: float = 1.5             # 문 열기 (압력판이면 밟고 있던 전원, 중간 조작)
    plate_points: float = 0.5                   # 압력판에 올라서기
    portal_points: float = 0.2                  # 포탈 사용
    number_points: float = 3.0                  # 번호판을 순서에 맞게 누름 (sequence_rooms)
    handoff_points: float = 5.0                 # 상대의 올바른 입력 바로 다음 차례를 이어받아 맞게 입력
    level_points: float = 25.0                  # 단계 완료 (curriculum, 단계형 시나리오 맵)
    # 시나리오 맵(scenarios/) 이벤트. bonus_collected는 아이템마다 정해진 points를 그대로 줌
    delivery_points: float = 8.0                # 아이템을 회수함(receptacle)에 배달
    delivery_complete_points: float = 15.0      # 회수함이 목표 개수를 채움 (마지막 배달자)
    checkpoint_points: float = 3.0              # 체크포인트 첫 방문
    keypad_points: float = 25.0                 # 패널 풀기 (마지막 입력자)
    sync_points: float = 20.0                   # 동시 진입 성공 (함께 밟은 전원)
    cargo_handoff_points: float = 8.0           # 화물을 상대에게 넘겨줌 (넘긴 쪽과 받은 쪽)
    chest_points: float = 8.0                   # 상자 열기
    block_push_points: float = 3.0              # 블록을 함께 밀어 움직임 (함께 민 전원, 블록마다 한 번)
    process_points: float = 6.0                 # 가공기(station)에서 가공 완료 (넣은 에이전트)
    # ---- 개인 감점 (매번) ----
    trap_penalty: float = -30.0                 # trap 발동
    sequence_reset_penalty: float = -3.0        # 번호판을 틀리게/동시에 눌러 전체 순서를 리셋시킴
    invalid_action_penalty: float = -1.0        # 형식이 틀린/알 수 없는 행동, 없는 수신자에게 메시지
    invalid_action_penalty_cap: float = -10.0
    code_failure_penalty: float = -1.0          # 제출 검사에서 거부되거나 실행에 실패한 정책 코드 1회당
    code_failure_penalty_cap: float = -15.0
    failed_attempt_penalty: float = -0.5        # 상태를 바꾸지 못한 상호작용 시도 1회당
    failed_attempt_penalty_cap: float = -10.0
    # ---- 단체 점수 ----
    clear_bonus: float = 60.0                   # 클리어하면
    time_bonus_max: float = 20.0                # 1 step 만에 클리어하면 전부, max_steps에 클리어하면 0에 가깝게 선형 감소

    @classmethod
    def from_dict(cls, data: dict) -> "ScoreConfig":
        known = {f.name for f in fields(cls)}
        unknown = sorted(set(data) - known)
        if unknown:
            raise ValueError(f"unknown score weights: {unknown}")
        return cls(**data)

    @classmethod
    def load(cls, path) -> "ScoreConfig":
        with open(path, encoding="utf-8") as file:
            return cls.from_dict(json.load(file))

    def to_dict(self) -> dict:
        return asdict(self)


# event: EventLog 항목 하나 -> 그 이벤트의 대상 오브젝트 id (중복 가점 판정 키)
def _target_of(event: dict):
    if event['type'] == 'level_completed':
        return event['level']
    for key in ("object_id", "door_id", "lever_id", "plate_id", "portal_id", "panel_id", "group", "receptacle_id",
                "zone_id"):
        if key in event:
            return event[key]
    return None


# 이벤트 하나가 agent_id에게 주는 (점수, 사유). 점수 대상이 아니면 None
def _individual_points(event: dict, config: ScoreConfig):
    event_type = event["type"]
    if event_type == 'level_completed':
        return config.level_points, '단계 완료'
    if event_type == "object_seen":
        return config.seen_points_by_type.get(event["object_type"], config.seen_points), "목격"
    if event_type == "item_picked_up":
        if event["category"] == "coop":
            return config.coop_pickup_points, "coop 물품 습득"
        if event["category"] == "trap":
            return None  # trap은 trap_triggered에서 감점
        return config.pickup_points, "물품 습득"
    if event_type == "lever_pulled":
        return config.lever_points, "레버 당김"
    if event_type == "door_unlocked":
        return config.door_unlock_points, "문 열림"
    if event_type == "plate_entered":
        return config.plate_points, "압력판 진입"
    if event_type == "portal_used":
        return config.portal_points, "포탈 사용"
    if event_type == "trap_triggered":
        return config.trap_penalty, "함정 발동"
    if event_type == "number_accepted":
        return config.number_points, "번호 순서 입력"
    if event_type == "sequence_reset":
        return config.sequence_reset_penalty, "순서 리셋"
    if event_type == "invalid_action":
        return config.invalid_action_penalty, "잘못된 행동"
    if event_type == "bonus_collected":
        return event["points"], "보너스 획득"
    if event_type == "item_delivered":
        return config.delivery_points, "배달"
    if event_type == "checkpoint_visited":
        return config.checkpoint_points, "체크포인트 방문"
    if event_type == "keypad_solved":
        return config.keypad_points, "패널 해결"
    if event_type == "sync_success":
        return config.sync_points, "동시 진입 성공"
    if event_type == "delivery_complete":
        return config.delivery_complete_points, "배달 목표 달성"
    if event_type == "cargo_handoff":
        return config.cargo_handoff_points, "화물 넘겨주기"
    if event_type == "chest_opened":
        return config.chest_points, "상자 열기"
    if event_type == "block_moved":
        return config.block_push_points, "블록 함께 밀기"
    if event_type == "item_processed":
        return config.process_points, "가공 완료"
    return None


# 상호작용 시도 중 같은 step에 그 에이전트가 일으킨 대응 이벤트가 없는 것(=헛된 시도)을 셈.
# 반환: (전체 시도 수, 헛된 시도 수, 헛된 시도 목록 [(step, agent_id, action_type)])
def _attempts(env):
    attempts, failures = 0, []
    for decision in env.decision_log.entries:
        action_type = (decision["final_action"] or {}).get("type")
        if action_type not in ATTEMPT_EFFECTS:
            continue
        attempts += 1
        effects = ATTEMPT_EFFECTS[action_type]
        succeeded = any(
            e["type"] in effects and decision["agent_id"] in e["agent_ids"]
            for e in env.event_log.filter(step=decision["step"])
        )
        if not succeeded:
            failures.append((decision["step"], decision["agent_id"], action_type))
    return attempts, len(failures), failures


def count_attempts(env) -> tuple[int, int]:
    attempts, failed, _ = _attempts(env)
    return attempts, failed


# objective: EventLog 항목과 비교할 조건 dict. 항목에 objective의 모든 키/값이 그대로 있으면 충족
# (예: {"type": "door_unlocked", "door_id": "gate"})
def _matches(event: dict, objective: dict) -> bool:
    return all(event.get(key) == value for key, value in objective.items())


# 모든 objective가 한 번씩 충족된 step (각 objective가 처음 충족된 step 중 가장 늦은 것).
# 하나라도 아직 충족되지 않았으면 None. 회차 도중 조기 종료 판정에도 사용
def clear_step(events: list[dict], objectives: list[dict]):
    steps = []
    for objective in objectives:
        step = next((e["step"] for e in events if _matches(e, objective)), None)
        if step is None:
            return None
        steps.append(step)
    return max(steps) if steps else None


# 같은 policy 객체를 공유하는 에이전트끼리 묶음 (중앙집중 모드에서는 모델 하나가 전원을 조종).
# 토큰/코드 오류는 정책 단위로 생기므로 묶음 단위로 계산해 구성원에게 똑같이 나눔
def _policy_groups(env) -> list[tuple[object, list[str]]]:
    groups: dict[int, tuple[object, list[str]]] = {}
    for agent_id, agent in env.agents.items():
        groups.setdefault(id(agent.policy), (agent.policy, []))[1].append(agent_id)
    return list(groups.values())


# env: 회차가 끝난 Environment
# max_steps: 이 회차에 허용된 최대 step 수 (시간 보너스 계산용)
# objectives: 클리어 조건 목록 (형식은 _matches 참고). 전부 충족된 step이 클리어 시간
# 반환: {"agents": {agent_id: {"score", "items", ...}}, "team": {...}, "individual_total", "total"}
def score_episode(env, max_steps: int, objectives: list[dict], config: ScoreConfig = None) -> dict:
    config = config or ScoreConfig()

    agents = {agent_id: {"score": 0.0, "items": []} for agent_id in env.agents}
    penalty_totals: dict[tuple[str, str], float] = {}

    def add(agent_id, step, reason, target, points, cap=None, category=None):
        if cap is not None:
            used = penalty_totals.get((agent_id, category), 0.0)
            points = max(points, cap - used)
            if points >= 0:
                return
            penalty_totals[(agent_id, category)] = used + points
        agents[agent_id]["score"] += points
        agents[agent_id]["items"].append({"step": step, "reason": reason, "target": target, "points": points})

    caps = {"invalid_action": config.invalid_action_penalty_cap}
    awarded: set = set()
    last_accepted_by = None  # 현재 시도에서 마지막으로 맞게 입력한 에이전트 (순서 이어받기 판정)
    for event in env.event_log.entries:
        if event["type"] in ("sequence_reset", "level_started"):
            last_accepted_by = None
        if event["type"] == "number_accepted":
            presser = event["agent_ids"][0] if event["agent_ids"] else None
            if presser in agents and last_accepted_by not in (None, presser):
                key = (presser, "handoff", event.get("order"))
                if key not in awarded and config.handoff_points > 0:
                    awarded.add(key)
                    add(presser, event["step"], "순서 이어받기", event.get("object_id"), config.handoff_points)
            last_accepted_by = presser
        result = _individual_points(event, config)
        if result is None:
            continue
        points, reason = result
        # 가점은 팀 전체에서 (종류, 대상)마다 첫 이벤트에만. 그 이벤트에 오른 에이전트는 모두 받음
        key = (event["type"], _target_of(event))
        if points > 0:
            if key in awarded:
                continue
            awarded.add(key)
        for agent_id in event["agent_ids"]:
            if agent_id not in agents:
                continue
            cap = caps.get(event["type"])
            add(agent_id, event["step"], reason, _target_of(event), points, cap, event["type"] if cap is not None else None)

    # 시나리오 맵: 회차가 끝날 때 남은 것으로 주는 개인 점수 (예: 들고 있는 동전) - scenarios/engine.py final_points
    for agent_id, entries in (env.final_points() if hasattr(env, "final_points") else {}).items():
        for points, reason, target in entries:
            if agent_id in agents:
                add(agent_id, env.step_count, reason, target, points)

    attempts, failed, failures = _attempts(env)
    # 동기화 판(sync_pad)도 시도로 셈: 판에 들어가는 것은 move_forward라 ATTEMPT_EFFECTS로는 잡히지 않음.
    # 동시 진입 판정 한 번에 걸린 에이전트마다 시도 1회 (성공에 참여 + 실패로 밀려남). 판이 꺼진 동안 판 위에서
    # 기다리던 에이전트는 진입이 등록되지 않지만 실패하면 함께 밀려나므로, 진입 수로 세면 실패가 시도보다 많아짐.
    # 밀려난 에이전트마다 헛된 시도 1회
    sync_failures = [(e["step"], agent_id, "sync_pad")
                     for e in env.event_log.entries if e["type"] == "sync_fail" for agent_id in e["agent_ids"]]
    sync_successes = sum(len(e["agent_ids"]) for e in env.event_log.entries if e["type"] == "sync_success")
    attempts += sync_successes + len(sync_failures)
    failed += len(sync_failures)
    failures = failures + sync_failures
    failed_by_agent: dict[str, int] = {}
    for step, agent_id, action_type in failures:
        if agent_id not in agents:
            continue
        failed_by_agent[agent_id] = failed_by_agent.get(agent_id, 0) + 1
        add(agent_id, step, "헛된 상호작용 시도", action_type, config.failed_attempt_penalty,
            config.failed_attempt_penalty_cap, "failed_attempt")

    for policy, members in _policy_groups(env):
        usage = getattr(policy, 'token_usage', {}) if policy is not None else {}
        # 에이전트의 추론 요약(reasoning_summary)은 출력 토큰 감점에 넣지 않음
        output_tokens = max(0, usage.get('completion_tokens', 0) - usage.get('reasoning_summary_tokens', 0))
        allowance = config.token_allowance * len(members)
        penalty = round(max(0, output_tokens - allowance) / 1000 * config.token_penalty_per_1000 / len(members), 2)
        prompts = getattr(policy, 'prompt_history', []) if policy is not None else []
        long_requests = [p for p in prompts if p > config.context_penalty_start]
        context_total = sum(context_penalty(p, config.context_penalty_start, config.context_penalty_end,
                                            config.context_penalty_divisor) for p in long_requests)
        checks = getattr(policy, 'code_checks', None) if policy is not None else None
        counts = checks.snapshot() if checks is not None else {}
        code_failures = counts.get('compile_failures', 0) + counts.get('execution_failures', 0)
        for agent_id in members:
            agents[agent_id]['token_usage'] = dict(usage, **({'shared_with': members} if len(members) > 1 else {}))
            token_points = max(-penalty, config.token_penalty_cap)
            agents[agent_id]['token_penalty'] = token_points
            if token_points:
                add(agent_id, env.step_count, '과도한 토큰 소비', 'LLM', token_points)
            share = round(context_total / len(members), 2)
            context_points = max(-share, config.context_penalty_cap)
            agents[agent_id]['context_penalty'] = context_points
            agents[agent_id]['long_context_requests'] = len(long_requests)
            if context_points:
                add(agent_id, env.step_count, f'긴 context 요청 {len(long_requests)}회', 'LLM', context_points)
            agents[agent_id]['code_failures'] = code_failures
            # 감점에는 넣지 않고 보고만 함 (도구 호출 실패, 제출 거절)
            agents[agent_id]['tool_call_failures'] = counts.get('tool_call_failures', 0)
            agents[agent_id]['submission_rejections'] = counts.get('submission_rejections', 0)
            if code_failures:
                points = code_failures * config.code_failure_penalty / len(members)
                add(agent_id, env.step_count, f'코드 오류 {code_failures}회', 'LLM', points,
                    config.code_failure_penalty_cap, 'code_failure')
            agents[agent_id]['failed_attempts'] = failed_by_agent.get(agent_id, 0)
            agents[agent_id]['invalid_actions'] = sum(
                1 for e in env.event_log.entries if e['type'] == 'invalid_action' and agent_id in e['agent_ids'])

    cleared_at = clear_step(env.event_log.entries, objectives)
    cleared = cleared_at is not None
    clear_bonus = config.clear_bonus if cleared else 0.0
    time_bonus = 0.0
    if cleared:
        time_bonus = config.time_bonus_max * max(0.0, 1 - (cleared_at - 1) / max_steps)
    team_score = clear_bonus + time_bonus

    for agent in agents.values():
        agent["score"] = round(agent["score"], 2)
    individual_total = round(sum(a["score"] for a in agents.values()), 2)
    return {
        "agents": agents,
        "team": {
            **({'level_state': env.level_state()} if hasattr(env, 'level_state') else {}),
            "cleared": cleared,
            "clear_step": cleared_at,
            "clear_bonus": clear_bonus,
            "time_bonus": round(time_bonus, 2),
            "attempts": attempts,                 # 상호작용 행동 + 동시 진입 판정에 걸린 에이전트 수
            "failed_attempts": failed,            # 효과 없는 상호작용 + 동시 진입 실패로 밀려남
            "sync_failures": len(sync_failures),
            "score": round(team_score, 2),
            # 시나리오 맵이면 이동거리/판 지킨 시간/보너스/메시지 손실 등 지표 (점수 합계에는 안 들어감)
            **({"metrics": env.scenario_metrics()} if hasattr(env, "scenario_metrics") else {})
        },
        "individual_total": individual_total,
        "total": round(individual_total + team_score, 2)
    }
