"""s02 징검다리 교대 (순서 계획) - 문 5개를 '한 명이 판을 밟아 주고 한 명이 넘어가기'로 번갈아 통과.
목표/의도/단서 내용은 scenarios/SCENARIOS.md 참고.
"""
from .common import agent, explain, make_spec, obj, vwall

NAME = "s02_leapfrog"
TITLE = "징검다리 교대"
FAMILY = "순서 계획"

WALL_X = [90, 170, 250, 330, 410]  # 각 문이 끼인 세로 벽의 왼쪽 x (두께 10)


def build():
    walls, objects = [], []
    for i, x in enumerate(WALL_X, start=1):
        walls += vwall(x, 0, 200, gaps=[(100, 20)])
        objects += [
            obj("door", f"d{i}", x + 5, 100, locked=True, radius=12.0),
            obj("switch_plate", f"b{i}", x - 30, 25, opens=[f"d{i}"]),   # 문 앞쪽(지나오는 쪽) 판
            obj("switch_plate", f"f{i}", x + 40, 175, opens=[f"d{i}"]),  # 문 뒤쪽(건너간 쪽) 판
        ]
    objects += [
        obj("goal_zone", "exit", 470, 100, width=100, height=200, label="exit hall"),
        obj("clue", "manual", 20, 180, hidden=False, content={
            "doors": "Doors d1..d5 stand in a row from left to right. Each door d_i is held open by EITHER of "
                     "two switch plates: b_i on the near side (before the door) or f_i on the far side.",
            "catch": "Every plate is far from its door, so nobody can stand on a plate and walk through its "
                     "door at the same time. The exit hall lies beyond d5.",
        }),
    ]
    guide = explain("switch_plate", "goal_zone")
    briefing = (f"You and your teammate start together in the leftmost section. Read the clue 'manual'. "
                f"You cannot see your teammate, and from a plate you usually cannot see its door. {guide}")
    return make_spec(
        NAME, 520, 200, walls, [agent("A", 30, 80, 0), agent("B", 30, 120, 0)], objects,
        objectives=[{"type": "team_assembled", "zone_id": "exit"}],
        hints=["Both agents must stand inside the goal_zone 'exit' (beyond door d5) at the same time."],
        briefings={"A": briefing, "B": briefing}, recommended_steps=200)


def solution(env):
    from .oracle import near, unlocked
    plans = {"A": [], "B": []}
    for i, x in enumerate(WALL_X, start=1):
        holder, passer = ("A", "B") if i % 2 else ("B", "A")
        plans[holder] += [
            ("goto", x - 30, 25),
            ("until", lambda e, p=passer, fx=x + 40: near(e, p, fx, 175)),
            ("goto", x - 20, 100), ("until", unlocked(f"d{i}")), ("goto", x + 30, 100),
        ]
        plans[passer] += [
            ("goto", x - 20, 100), ("until", unlocked(f"d{i}")), ("goto", x + 30, 100), ("goto", x + 40, 175),
            ("until", lambda e, h=holder, gx=x + 20: e.agents[h].x > gx),
        ]
    plans["A"].append(("goto", 470, 90))
    plans["B"].append(("goto", 470, 110))
    return plans


# 실수: 아무도 판을 밟지 않은 채 둘 다 d1 앞에서 기다림 -> 그다음 정상 교대
def mistake(env):
    plans = solution(env)
    plans["A"] = [("goto", 70, 95), ("wait", 6)] + plans["A"]
    plans["B"] = [("goto", 70, 105), ("wait", 6)] + plans["B"]
    return plans
