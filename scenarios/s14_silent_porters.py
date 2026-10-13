"""s14 말없는 운반 (몸 조율 + 보이지 않는 동역학) - MAP_GUIDE.md 기준으로 만든 단계형 맵. 축 A + E.
상자는 2인용(coop)이지만 그 사실도, 들고 움직이는 규칙도, dock이 무엇인지도 알려 주지 않는다. 목표만 준다.
  1단계: 열린 바닥의 상자를 dock으로 (둘이 함께 들고, 서로 15 이내를 유지하며 움직여야 함을 스스로 알아냄)
  2단계: 벽을 돌아가는 꺾인 통로로 운반 (같은 step에 같은 회전/전진을 맞춰야 함)
  3단계: 상자가 경로를 숨긴 채 스스로 돌아다님 + dock 앞 문이 정해진 주기로만 열림 (매복 + 문 타이밍 + 함께 통과)
"""
from .common import STAGED_OBJECTIVES, agent, make_spec, obj, stage, vwall

NAME = "s14_silent_porters"
TITLE = "말없는 운반"
FAMILY = "몸 조율"

LOOP_3 = [[60, 60], [160, 60], [160, 200], [60, 200]]  # 3단계 상자 순환 경로 (관찰에서 숨김)
DOOR_3 = {"period": 16, "open_steps": 8, "phase": 0}    # 3단계 문 일정 (관찰에서 숨김)
STAGE_WALLS = {1: [], 2: [[220, 0, 20, 230]], 3: vwall(300, 0, 320, gaps=[(160, 24)])}


def _coop(item_id, x, y):
    return obj("item", item_id, x, y, category="coop", required_agents=2)


def _dock(n, x, y):
    return obj("receptacle", f"dock_{n}", x, y, accepts=[f"crate_{n}"], target=1, radius=20.0)


STAGE_STARTS = {2: {"A": [60, 160, 0], "B": [170, 290, 270]}}  # 2단계는 둘 다 상자 쪽에서 시작 (운반에 집중)


def _stage(n, objects):
    return stage(f"stage {n}", f"Deliver crate_{n} to dock_{n}.",
                 [{"type": "delivery_complete", "receptacle_id": f"dock_{n}"}], objects, walls=STAGE_WALLS[n],
                 agents=STAGE_STARTS.get(n))


def build():
    stages = [
        _stage(1, [_coop("crate_1", 230, 160), _dock(1, 410, 290)]),
        _stage(2, [_coop("crate_2", 100, 80), _dock(2, 360, 80)]),
        _stage(3, [obj("mover", "crate_3", 60, 60, waypoints=LOOP_3, speed=4.0, object_type="item", loop=True,
                       extra={"category": "coop", "required_agents": 2, "_hide_path": True}),
                   obj("periodic_door", "gate_3", 305, 160, radius=12.0, **DOOR_3),
                   _dock(3, 390, 160)]),
    ]
    briefings = {"A": "You start on the left side of a hall.", "B": "You start in the top-right corner of a hall."}
    return make_spec(
        NAME, 460, 320, [], [agent("A", 60, 160, 0), agent("B", 400, 60, 180)], [],
        objectives=STAGED_OBJECTIVES, hints=["Deliver the crate of every stage to its dock."],
        briefings=briefings, rules={"stages": stages}, recommended_steps=570)


def _both_near(item_id, radius=14.0):
    import math

    def check(env):
        item = env.objects.get(item_id)
        return item is not None and all(math.hypot(a.x - item["x"], a.y - item["y"]) <= radius
                                        for a in env.agents.values())
    return check


def _carry(n, start, waypoints, item):
    from .oracle import carry_legs
    legs = carry_legs(start, waypoints)
    return {"A": [("barrier", f"pick{n}"), ("act", {"type": "pick_up", "object_id": item}),
                  ("barrier", f"carry{n}")] + legs + [("act", {"type": "drop", "object_id": item})],
            "B": [("barrier", f"pick{n}"), ("barrier", f"carry{n}")] + legs}


def _stage_plans():
    from .oracle import carry_legs, unlocked
    one = _carry(1, (230, 172), [(405, 280)], "crate_1")
    one = {"A": [("stage", 1), ("goto", 230, 172)] + one["A"],
           "B": [("stage", 1), ("goto", 300, 100), ("goto", 230, 172)] + one["B"]}
    two = _carry(2, (100, 92), [(100, 275), (360, 275), (360, 95)], "crate_2")
    two = {"A": [("stage", 2), ("goto", 100, 92)] + two["A"],
           "B": [("stage", 2), ("goto", 100, 92)] + two["B"]}
    # 3단계: 상자 경로 위 (160, 130)에서 함께 매복 -> 문 앞까지 운반 -> 문이 열리면 함께 통과
    to_door = carry_legs((160, 130), [(280, 160)])
    through = carry_legs((280, 160), [(385, 160)])
    three = {
        "A": [("stage", 3), ("goto", 160, 130), ("until", _both_near("crate_3")),
              ("act", {"type": "pick_up", "object_id": "crate_3"}), ("barrier", "carry3")] + to_door
             + [("until", unlocked("gate_3"))] + through + [("act", {"type": "drop", "object_id": "crate_3"})],
        # B는 dock 쪽에서 시작하므로 먼저 주기 문을 지나 상자 쪽으로 건너감
        "B": [("stage", 3), ("goto", 330, 160), ("until", unlocked("gate_3")), ("goto", 270, 160), ("goto", 160, 130),
              ("until", lambda e: "crate_3" not in e.objects), ("barrier", "carry3")] + to_door
             + [("until", unlocked("gate_3"))] + through,
    }
    return one, two, three


def _join(*parts):
    return {aid: [item for part in parts for item in part[aid]] for aid in ("A", "B")}


def solution(env):
    return _join(*_stage_plans())


# 실수(1단계): A가 혼자 상자를 들려고 함(pickup_blocked) -> B가 온 뒤 함께
def mistake(env):
    one, two, three = _stage_plans()
    one["A"] = [("stage", 1), ("goto", 230, 172), ("act", {"type": "pick_up", "object_id": "crate_1"})] + one["A"][1:]
    return _join(one, two, three)
