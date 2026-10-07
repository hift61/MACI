from dataclasses import dataclass, field

# 한 회차(episode)가 끝난 Environment의 event_log/decision_log를 읽어 점수를 매김.
#   개인 점수: 각 에이전트가 일으킨 이벤트(물체 목격, 도움이 되는 동작 등)마다 부여
#   단체 점수: 클리어 여부, 클리어 시간, 헛된 시도 횟수로 팀 전체에 부여
#   총점 = 개인 점수 합 + 단체 점수
# 같은 점수 항목을 반복해서 쌓는 것(레버를 계속 당기기, 판을 밟았다 내렸다 하기)을 막기 위해
# 개인 가점은 (에이전트, 이벤트 종류, 대상 오브젝트) 조합마다 한 번만 줌. 감점은 매번 적용.

# 시도로 세는 상호작용 action type -> 그 시도가 성공했을 때 같은 step에 남는 이벤트 종류
# (press_button은 별도 이벤트가 없어 연결된 문의 상태 변화로 판정)
ATTEMPT_EFFECTS = {
    "pick_up": {"item_picked_up"},
    "drop": {"item_dropped"},
    "use_key": {"door_unlocked"},
    "press_button": {"door_unlocked", "door_locked", "number_accepted"},  # number_accepted: sequence_rooms 번호판
    "pull_lever": {"lever_pulled"},
}


@dataclass
class ScoreConfig:
    # ---- 개인 점수 (대상 오브젝트마다 한 번) ----
    seen_points: float = 1.0                    # 물체를 처음 목격
    seen_points_by_type: dict = field(default_factory=lambda: {"clue": 3.0})  # 종류별로 다르게 줄 때
    pickup_points: float = 3.0                  # normal 물품/열쇠 습득
    coop_pickup_points: float = 8.0             # coop 물품 습득 (함께 들어준 에이전트도 같은 점수)
    lever_points: float = 3.0                   # 레버 당기기
    door_unlock_points: float = 10.0            # 문 열기 (압력판이면 밟고 있던 전원)
    plate_points: float = 2.0                   # 압력판에 올라서기
    portal_points: float = 1.0                  # 포탈 사용
    number_points: float = 2.0                  # 번호판을 순서에 맞게 누름 (sequence_rooms)
    # ---- 개인 감점 (매번) ----
    trap_penalty: float = -30.0                 # trap 발동
    sequence_reset_penalty: float = -3.0        # 번호판을 틀리게 눌러 전체 순서를 리셋시킴 (sequence_rooms)
    # ---- 단체 점수 ----
    clear_bonus: float = 50.0                   # 클리어하면
    time_bonus_max: float = 30.0                # 1 step 만에 클리어하면 전부, max_steps에 클리어하면 0에 가깝게 선형 감소
    failed_attempt_penalty: float = -1.0        # 상태를 바꾸지 못한 상호작용 시도 1회당
    failed_attempt_penalty_cap: float = -20.0   # 헛된 시도 감점 하한


# event: EventLog 항목 하나 -> 그 이벤트의 대상 오브젝트 id (중복 가점 판정 키)
def _target_of(event: dict):
    for key in ("object_id", "door_id", "lever_id", "plate_id", "portal_id"):
        if key in event:
            return event[key]
    return None


# 이벤트 하나가 agent_id에게 주는 (점수, 사유). 점수 대상이 아니면 None
def _individual_points(event: dict, config: ScoreConfig):
    event_type = event["type"]
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
    return None


# 상호작용 시도 중 같은 step에 그 에이전트가 일으킨 대응 이벤트가 없는 것(=헛된 시도)을 셈
def count_attempts(env) -> tuple[int, int]:
    attempts = failed = 0
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
            failed += 1
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


# env: 회차가 끝난 Environment
# max_steps: 이 회차에 허용된 최대 step 수 (시간 보너스 계산용)
# objectives: 클리어 조건 목록 (형식은 _matches 참고). 전부 충족된 step이 클리어 시간
# 반환: {"agents": {agent_id: {"score", "items"}}, "team": {...}, "individual_total", "total"}
def score_episode(env, max_steps: int, objectives: list[dict], config: ScoreConfig = None) -> dict:
    config = config or ScoreConfig()

    agents = {agent_id: {"score": 0.0, "items": []} for agent_id in env.agents}
    awarded: set = set()
    for event in env.event_log.entries:
        result = _individual_points(event, config)
        if result is None:
            continue
        points, reason = result
        for agent_id in event["agent_ids"]:
            if agent_id not in agents:
                continue
            key = (agent_id, event["type"], _target_of(event))
            if points > 0:
                if key in awarded:
                    continue
                awarded.add(key)
            agents[agent_id]["score"] += points
            agents[agent_id]["items"].append({
                "step": event["step"],
                "reason": reason,
                "target": _target_of(event),
                "points": points
            })

    cleared_at = clear_step(env.event_log.entries, objectives)
    cleared = cleared_at is not None
    clear_bonus = config.clear_bonus if cleared else 0.0
    time_bonus = 0.0
    if cleared:
        time_bonus = config.time_bonus_max * max(0.0, 1 - (cleared_at - 1) / max_steps)
    attempts, failed = count_attempts(env)
    attempt_penalty = max(config.failed_attempt_penalty_cap, failed * config.failed_attempt_penalty) if failed else 0.0
    team_score = clear_bonus + time_bonus + attempt_penalty

    individual_total = sum(a["score"] for a in agents.values())
    return {
        "agents": agents,
        "team": {
            "cleared": cleared,
            "clear_step": cleared_at,
            "clear_bonus": clear_bonus,
            "time_bonus": round(time_bonus, 2),
            "attempts": attempts,
            "failed_attempts": failed,
            "attempt_penalty": attempt_penalty,
            "score": round(team_score, 2)
        },
        "individual_total": individual_total,
        "total": round(individual_total + team_score, 2)
    }
