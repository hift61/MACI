"""s19 뜨거운 화물 (시간 예측, 인계) - 한 사람이 오래 들 수 없고 들면 느려지는 화물을 이어 달리기로 배달.
목표/의도/단서 내용은 scenarios/SCENARIOS.md 참고.
"""
import math

from .common import agent, make_spec, obj

NAME = "s19_hot_cargo"
TITLE = "뜨거운 화물"
FAMILY = "시간 예측"

ORIGIN, DOCK = (40, 280), (440, 40)
HOLD_LIMIT, CARRY_SPEED = 10, 10.0


def build():
    walls = [[150, 0, 10, 150], [300, 170, 10, 150]]  # 직선 경로를 크게 막지 않는 가림벽 (시야 가림)
    objects = [
        obj("cargo", "cargo", *ORIGIN, hold_limit=HOLD_LIMIT, carry_speed=CARRY_SPEED, label="overheating cargo"),
        obj("receptacle", "dock", *DOCK, accepts=["cargo"], target=1, radius=20.0, label="cooling dock"),
        obj("clue", "notice", 80, 300, hidden=False, content={
            "heat": "The cargo overheats: one agent can keep it only for a limited time, then it jumps back to "
                    "where it started. It counts again only when a different agent picks it up.",
            "weight": "Carrying the cargo slows you down.",
        }),
    ]
    return make_spec(
        NAME, 480, 320, walls, [agent("A", 60, 260, 0), agent("B", 80, 290, 0)], objects,
        objectives=[{"type": "delivery_complete", "receptacle_id": "dock"}],
        hints=["Deliver the cargo to the receptacle 'dock' (north-east corner)."],
        recommended_steps=200)


def _relay_points(legs=8):
    return [(ORIGIN[0] + (DOCK[0] - ORIGIN[0]) * k / legs, ORIGIN[1] + (DOCK[1] - ORIGIN[1]) * k / legs)
            for k in range(legs + 1)]


def solution(env):
    points = _relay_points()
    heading = math.degrees(math.atan2(DOCK[1] - ORIGIN[1], DOCK[0] - ORIGIN[0])) % 360
    leg = math.dist(points[0], points[1])
    moves = math.ceil(leg / CARRY_SPEED)
    plans = {"A": [], "B": []}
    for k in range(len(points) - 1):
        carrier = "A" if k % 2 == 0 else "B"
        (sx, sy), (ex, ey) = points[k], points[k + 1]
        on_ground = lambda e, x=sx, y=sy: "cargo" in e.objects and math.dist((e.objects["cargo"]["x"],
                                                                               e.objects["cargo"]["y"]), (x, y)) < 3
        plans[carrier] += [("goto", sx, sy), ("until", on_ground),
                           ("act", {"type": "pick_up", "object_id": "cargo"}),
                           ("act", {"type": "turn", "facing": heading})]
        plans[carrier] += [("act", {"type": "move_forward", "distance": leg / moves})] * moves
        plans[carrier] += [("act", {"type": "drop", "object_id": "cargo"})]
    return plans


# 실수: A가 혼자 계속 들고 가다 화물이 원위치로 돌아감 -> 이어 달리기
def mistake(env):
    plans = solution(env)
    alone = [("act", {"type": "pick_up", "object_id": "cargo"}), ("act", {"type": "turn", "facing": 329})] + \
            [("act", {"type": "move_forward", "distance": 10})] * 11
    plans["A"] = [("goto", *ORIGIN)] + alone + plans["A"]
    plans["B"] = [("until", lambda e: any(ev["type"] == "cargo_spoiled" for ev in e.event_log.entries))] + plans["B"]
    return plans
