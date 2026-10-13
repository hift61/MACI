"""시나리오 파일들이 같이 쓰는 맵 조립 도구 (Environment에 의존하지 않음)."""
from mapgen.spec import MapSpec

# 모든 시나리오 과제 설명 뒤에 붙는 공통 안내
COMMON_RULES = (
    "Nothing in this map can make the task permanently impossible: mistakes only cost time "
    "(panels clear, pads push you back, doors close again). Other agents are invisible to you."
)


# 관찰 type별 설명 (CodePolicy 시스템 프롬프트에는 기존 물체만 설명돼 있으므로 과제 설명에 덧붙임)
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
STAGE_RULES = ("This map has several stages that must be cleared in order; observation 'stage' shows the current "
               "stage number, title and briefing. Clearing a stage removes its objects, puts both agents back at "
               "their start positions and loads the next stage. Your memory and conversation carry over.")


def make_spec(name: str, width: int, height: int, walls: list, agents: list, objects: list,
              objectives: list, hints: list, briefings: dict, rules: dict = None,
              recommended_steps: int = 150, seed: int = 0) -> MapSpec:
    return MapSpec(
        seed=seed, width=width, height=height, walls=walls, agents=agents, objects=objects,
        objectives=objectives, puzzles=[name], hints=hints,
        config={"recommended_steps": recommended_steps, "source": f"scenarios/{name}.py"},
        scenario=name, rules=dict(rules or {}),
        briefings={aid: text + "\n" + COMMON_RULES for aid, text in briefings.items()},
    )
