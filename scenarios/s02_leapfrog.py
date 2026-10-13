"""s02 징검다리 교대 (순서 계획) - 문마다 '한 명이 판을 밟아 주고 한 명이 넘어가기'로 번갈아 통과. 단계형 3단계.
  1단계 문 2개, 2단계 문 5개 (원래 s02), 3단계 문 7개 + 문마다 판이 위/아래 구석 중 어디 있는지 섞임
목표/의도/단서 내용은 scenarios/SCENARIOS.md 참고.
"""
from .common import STAGED_OBJECTIVES, agent, make_spec, obj, stage, vwall

NAME = "s02_leapfrog"
TITLE = "징검다리 교대"
FAMILY = "순서 계획"

WIDTH, HEIGHT = 700, 200
DOOR_COUNTS = [2, 5, 7]
FLIPPED_3 = {2, 5, 6}  # 3단계에서 앞쪽 판이 아래, 뒤쪽 판이 위에 있는 문 번호


def wall_x(n):
    return [90 + 80 * i for i in range(DOOR_COUNTS[n - 1])]  # 각 문이 끼인 세로 벽의 왼쪽 x (두께 10)


def plate_y(n, i):
    """(앞쪽 판 y, 뒤쪽 판 y)"""
    return (175, 25) if n == 3 and i in FLIPPED_3 else (25, 175)


def _stage(n):
    walls, objects = [], []
    xs = wall_x(n)
    for i, x in enumerate(xs, start=1):
        near_y, far_y = plate_y(n, i)
        walls += vwall(x, 0, HEIGHT, gaps=[(100, 20)])
        objects += [
            obj("door", f"d{n}_{i}", x + 5, 100, locked=True, radius=12.0),
            obj("switch_plate", f"b{n}_{i}", x - 30, near_y, opens=[f"d{n}_{i}"]),  # 문 앞쪽(지나오는 쪽) 판
            obj("switch_plate", f"f{n}_{i}", x + 40, far_y, opens=[f"d{n}_{i}"]),   # 문 뒤쪽(건너간 쪽) 판
        ]
    exit_left = xs[-1] + 10
    count = len(xs)
    objects += [
        obj("goal_zone", f"exit_{n}", (exit_left + WIDTH) / 2, 100, width=WIDTH - exit_left, height=HEIGHT,
            label="exit hall"),
        obj("clue", f"manual_{n}", 20, 180, hidden=False, content={
            "doors": "Each door here can be held open by either of two plates, one on each side of it.",
            "catch": "No plate is close enough to its door to stand on it and walk through at the same time.",
        }),
    ]
    return stage(f"{count} doors", f"Both of you stand inside exit_{n} at the same time.",
                 [{"type": "team_assembled", "zone_id": f"exit_{n}"}], objects, walls=walls)


def build():
    return make_spec(
        NAME, WIDTH, HEIGHT, [], [agent("A", 30, 80, 0), agent("B", 30, 120, 0)], [],
        objectives=STAGED_OBJECTIVES,
        hints=["Clear all three stages; each stage ends when both agents stand in its exit hall goal_zone."],
        rules={"stages": [_stage(n) for n in (1, 2, 3)]},
        recommended_steps=450)


def _stage_plan(n):
    from .oracle import near, unlocked
    plans = {"A": [("stage", n)], "B": [("stage", n)]}
    for i, x in enumerate(wall_x(n), start=1):
        near_y, far_y = plate_y(n, i)
        holder, passer = ("A", "B") if i % 2 else ("B", "A")
        plans[holder] += [
            ("goto", x - 30, near_y),
            ("until", lambda e, p=passer, fx=x + 40, fy=far_y: near(e, p, fx, fy)),
            ("goto", x - 20, 100), ("until", unlocked(f"d{n}_{i}")), ("goto", x + 30, 100),
        ]
        plans[passer] += [
            ("goto", x - 20, 100), ("until", unlocked(f"d{n}_{i}")), ("goto", x + 30, 100), ("goto", x + 40, far_y),
            ("until", lambda e, h=holder, gx=x + 20: e.agents[h].x > gx),
        ]
    exit_x = (wall_x(n)[-1] + 10 + WIDTH) / 2
    plans["A"].append(("goto", exit_x, 90))
    plans["B"].append(("goto", exit_x, 110))
    return plans


def _join(*parts):
    return {aid: [item for part in parts for item in part[aid]] for aid in ("A", "B")}


def solution(env):
    return _join(*(_stage_plan(n) for n in (1, 2, 3)))


# 실수(2단계): 아무도 판을 밟지 않은 채 둘 다 첫 문 앞에서 기다림 -> 그다음 정상 교대
def mistake(env):
    stage2 = _stage_plan(2)
    stage2["A"] = [("stage", 2), ("goto", 70, 95), ("wait", 6)] + stage2["A"][1:]
    stage2["B"] = [("stage", 2), ("goto", 70, 105), ("wait", 6)] + stage2["B"][1:]
    return _join(_stage_plan(1), stage2, _stage_plan(3))
