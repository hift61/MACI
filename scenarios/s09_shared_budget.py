"""s09 공동 예산 (작업 분배) - 체크포인트 8곳을 누가 가든 다 방문. 각자 5곳씩만 알고, 팀 총 이동거리로 평가.
목표/의도/단서 내용은 scenarios/SCENARIOS.md 참고.
"""
from .common import agent, explain, make_spec, obj

NAME = "s09_shared_budget"
TITLE = "공동 예산"
FAMILY = "작업 분배"

CHECKPOINTS = {"C1": (40, 40), "C2": (250, 30), "C3": (460, 50), "C4": (60, 200),
               "C5": (440, 210), "C6": (50, 360), "C7": (260, 370), "C8": (450, 360)}
KNOWN = {"A": ["C1", "C2", "C3", "C4", "C6"], "B": ["C3", "C5", "C6", "C7", "C8"]}  # 겹침: C3, C6


def _survey(agent_id):
    return {"survey_of": f"agent {agent_id}",
            "checkpoints": {cid: list(CHECKPOINTS[cid]) for cid in KNOWN[agent_id]},
            "note": "This survey lists only some checkpoints. There are 8 in total (C1-C8)."}


def build():
    walls = [[160, 80, 10, 240], [330, 80, 10, 240]]
    objects = [obj("checkpoint", cid, x, y, radius=12.0, hidden=True, label=cid) for cid, (x, y) in CHECKPOINTS.items()]
    objects.append(obj("variant_clue", "survey", 250, 170, hidden=False,
                       content={"note": "Survey sheet. Each agent's copy lists different checkpoints."},
                       variants={aid: _survey(aid) for aid in KNOWN}))
    guide = explain("checkpoint")
    briefing = (f"You and your teammate start in the middle of the map. Read the clue 'survey' - your copy lists "
                f"only the checkpoints YOU know about (approximate coordinates); your teammate's copy is different. "
                f"Every checkpoint C1-C8 must be visited by at least one of you; it does not matter who. "
                f"Your team is ALSO judged on the total distance both of you walk, so avoid walking twice to the "
                f"same place or both visiting the same checkpoint. {guide}")
    return make_spec(
        NAME, 500, 400, walls, [agent("A", 240, 200, 270), agent("B", 260, 200, 270)], objects,
        objectives=[{"type": "all_checkpoints_visited"}],
        hints=["Visit all eight checkpoints C1-C8 (each by at least one agent)."],
        briefings={"A": briefing, "B": briefing}, recommended_steps=150)


def _route(points):
    return [("goto", x, y) for x, y in points]


def solution(env):
    c = CHECKPOINTS
    return {"A": _route([(240, 60), c["C2"], c["C1"], c["C4"], c["C6"], c["C7"]]),
            "B": _route([(300, 60), c["C3"], c["C5"], c["C8"]])}


# 실수: B도 C2에 먼저 들름(중복 방문, 이동거리 낭비) -> 원래 경로
def mistake(env):
    plans = solution(env)
    plans["B"] = _route([(250, 60), CHECKPOINTS["C2"]]) + plans["B"]
    return plans
