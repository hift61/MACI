"""시나리오 파일들이 같이 쓰는 맵 조립 도구 (Environment에 의존하지 않음)."""
import dataclasses

from mapgen.spec import MapSpec

# 모든 시나리오 과제 설명 뒤에 붙는 공통 안내
COMMON_RULES = (
    "Nothing in this map can make the task permanently impossible: mistakes only cost time "
    "(panels clear, pads push you back, doors close again). Other agents are invisible to you."
)


# 관찰 type별 설명. 지금은 같은 내용이 시스템 프롬프트(policy.py _OBSERVATION_DOC "Object roles")에 공통으로
# 들어가므로 맵 안내문에는 넣지 않음 (explain()은 예전 맵/외부 코드 호환용으로만 남김)
OBJECT_HELP = {
    "goal_zone": "goal_zone: a rectangle centred on (x, y) with the given width/height.",
    "switch_plate": "switch_plate: while ANY agent stands within its radius, every door in its 'opens' list is "
                    "unlocked; when nobody stands on any plate for a door, that door locks again.",
    "latch_lever": "lever with \"latch\": true: pull_lever opens its linked doors permanently.",
    "switch_lever": "lever with \"cooldown\": after a pull it cannot be pulled again until step 'ready_at_step'.",
    "keypad": "keypad: a code panel. Press its buttons (type 'button' with fields 'panel' and 'label') with "
              "press_button; 'entered' shows the labels entered so far and 'attempts' counts finished tries.",
    "display": "display: a screen whose 'content' is updated by the machine it belongs to.",
    "sync_pad": "sync_pad: pads of the same 'group' must all be entered (walked onto) close together in time. "
                "'armed' false means the pad currently ignores entries.",
    "receptacle": "receptacle: drop an item whose id starts with one of 'accepts' within its radius to deliver "
                  "it ('delivered' counts deliveries, 'target' is the goal).",
    "checkpoint": "checkpoint: visited (and stays visited) as soon as any agent comes within its radius. Hidden "
                  "checkpoints only show up when you are within about 15 units.",
    "bonus_item": "item with \"bonus\": true: picking it up gives YOU personal points; it disappears at step "
                  "'expires_at' if nobody takes it.",
    "push_block": "block: a heavy solid block (radius 'radius'). It moves 'push_distance' units only when at "
                  "least 'required' agents walk into it in the SAME step while facing the same direction "
                  "(within 30 degrees); it moves in that direction. One agent alone cannot move it. Blocks stop "
                  "at walls and cannot be pulled.",
    "block_target": "block_target: becomes 'filled' while the centre of any block is within its radius.",
    "reset_lever": "lever with \"reset\": true: pull_lever puts the blocks listed in 'blocks' back where they started.",
    "station": "station: drop an item whose id starts with 'input' within its radius; after 'process_steps' "
               "steps a new item whose id starts with 'output' appears at (out_x, out_y). It works on one item "
               "at a time ('busy_until' = step when the current work ends, 'queued' = items waiting).",
    "cargo": "item with \"cargo\": true: whoever carries it moves at most 'carry_speed' units per step. One agent "
             "may only keep it until step 'drop_by_step' (hold_limit steps after picking it up); after that it "
             "jumps back to its starting place. The count restarts only when a DIFFERENT agent picks it up.",
    "weighted_item": "Items here have hidden weights; you can only learn them by putting them on a scale.",
    "scale": "scale: 'reading' is the total weight of items lying within its radius. A scale with a goal shows "
             "only 'empty', 'too light', 'too heavy' or 'balanced'.",
    "capacity_zone": "capacity_zone: a rectangle centred on (x, y) that holds at most 'capacity' agents. If more "
                     "agents are inside at the end of a step, everyone inside is put back where they were before "
                     "entering.",
    "chest": "chest: a locked box. use_key with a key whose 'unlocks' is the chest's id (within about 15 units) "
             "opens it; its contents then appear right next to it.",
    "coin": "item with \"coin\": true: every coin you are still carrying when the episode ends is worth 'value' "
            "personal points. Dropping coins into a receptacle spends them.",
    "marker": "marker: a floor sign with a 'label'. It does nothing by itself.",
}


def explain(*kinds: str) -> str:
    return "Object guide: " + " ".join(OBJECT_HELP[k] for k in kinds)


def obj(kind: str, object_id: str, x: float, y: float, **params) -> dict:
    return {"kind": kind, "id": object_id, "x": x, "y": y, "params": params}


def agent(agent_id: str, x: float, y: float, facing: float = 0.0) -> dict:
    return {"id": agent_id, "x": x, "y": y, "facing": facing}


# 가로 벽 (y ~ y+t). gaps: [(가운데 x, 폭), ...] 위치는 비워 둠 (문을 끼울 자리)
def hwall(y: float, x0: float, x1: float, gaps=(), t: float = 10) -> list:
    return _segments(x0, x1, gaps, lambda a, b: [a, y, b - a, t])


# 세로 벽 (x ~ x+t). gaps: [(가운데 y, 폭), ...]
def vwall(x: float, y0: float, y1: float, gaps=(), t: float = 10) -> list:
    return _segments(y0, y1, gaps, lambda a, b: [x, a, t, b - a])


def _segments(start, end, gaps, make):
    walls, cursor = [], start
    for center, width in sorted(gaps):
        if center - width / 2 > cursor:
            walls.append(make(cursor, center - width / 2))
        cursor = center + width / 2
    if end > cursor:
        walls.append(make(cursor, end))
    return walls


# 단계형 맵의 단계 하나 (scenarios/engine.py "단계" 참고). objects/walls/agents는 그 단계에만 쓰임
def stage(title: str, briefing: str, objectives: list, objects: list, walls: list = None, agents: dict = None) -> dict:
    result = {"title": title, "briefing": briefing, "objectives": objectives, "objects": objects}
    if walls is not None:
        result["walls"] = walls
    if agents is not None:
        result["agents"] = agents
    return result


STAGED_OBJECTIVES = [{"type": "all_stages_completed"}]
# 단계 규칙은 시스템 프롬프트(observation "stage" 설명)로 옮김. 예전 맵/외부 코드 호환용으로만 남김
STAGE_RULES = ("This map has several stages that must be cleared in order; observation 'stage' shows the current "
               "stage number, title and briefing. Clearing a stage removes its objects, puts both agents back at "
               "their start positions and loads the next stage. Your memory and conversation carry over.")


# 정보 전달 원칙 (모든 맵 공통, MAP_HOWTO.md 6장)
#   - 물체의 역할: 시스템 프롬프트(policy.py _OBSERVATION_DOC)에 공통으로 있음 -> 맵에서 다시 설명하지 않음
#   - 과제 설명: 목표 문장(objectives -> environment_prompt.objective_description)과 COMMON_RULES만.
#     위치, 역할 분담, 맵 배치, 전략은 쓰지 않음 (briefings 인자는 예전 맵 호환용, 주지 않는 것이 기본)
#   - 단계 안내(stage briefing): 그 단계의 목표만
#   - 단서(clue)/화면(display): 퍼즐 자료(CLUE_DATA_KEYS 키) + 장치 작동을 직접적, 구체적으로 알려 주는 힌트(다른 키).
#     힌트 없는 버전(without_clue_hints)은 힌트 키를 지움. 현재 상태, 위치/배치, 해결 순서 지시는 어느 버전에도 쓰지 않음
# 힌트 없는 버전(<이름>_nohint): 단서에서 장치 규칙 문장을 지우고 퍼즐 자료만 남김.
# 단서 content(dict)의 키 중 아래 키만 퍼즐 자료로 보고 남김. 문자열 content(variant_clue 등)는 자료로 보고 그대로 둠.
# 남는 내용이 없는 단서는 맵에서 뺌. 새 맵에서 자료 키를 새로 쓰면 여기에 추가할 것
CLUE_DATA_KEYS = {"code", "copy of the code", "sum of the digits", "checkpoints", "target weight of vault_scale"}
NOHINT_SUFFIX = "_nohint"


def _strip_clue_hints(objects: list) -> list:
    result = []
    for o in objects:
        content = o["params"].get("content")
        if o["kind"] in ("clue", "variant_clue") and isinstance(content, dict):
            data = {k: v for k, v in content.items() if k in CLUE_DATA_KEYS}
            if not data:
                continue
            o = {**o, "params": {**o["params"], "content": data}}
        result.append(o)
    return result


def without_clue_hints(spec: MapSpec) -> MapSpec:
    """같은 맵의 힌트 없는 버전. 물체, 목표, 정답은 같고 단서의 규칙 문장만 없음"""
    rules = dict(spec.rules or {})
    if "stages" in rules:
        rules["stages"] = [{**st, "objects": _strip_clue_hints(st["objects"])} for st in rules["stages"]]
    name = (spec.scenario or "map") + NOHINT_SUFFIX
    return dataclasses.replace(spec, objects=_strip_clue_hints(spec.objects), rules=rules, scenario=name,
                               config={**spec.config, "clue_hints": False})


def make_spec(name: str, width: int, height: int, walls: list, agents: list, objects: list,
              objectives: list, hints: list, briefings: dict = None, rules: dict = None,
              recommended_steps: int = 150, seed: int = 0) -> MapSpec:
    briefings = briefings or {}
    return MapSpec(
        seed=seed, width=width, height=height, walls=walls, agents=agents, objects=objects,
        objectives=objectives, puzzles=[name], hints=hints,
        config={"recommended_steps": recommended_steps, "source": f"scenarios/{name}.py"},
        scenario=name, rules=dict(rules or {}),
        briefings={a["id"]: (briefings[a["id"]] + "\n" if briefings.get(a["id"]) else "") + COMMON_RULES
                   for a in agents},
    )
