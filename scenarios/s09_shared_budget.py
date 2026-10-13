"""s09 공동 예산 (작업 분배) - 숨은 체크포인트 8곳을 누가 가든 다 방문. 팀 총 이동거리로 평가.
좌표 목록(survey)은 주지 않음: 시작 위치 바로 옆의 C2 한 곳만 알려 주고, 나머지는 탐색과 점수 피드백
(관찰의 reward - 체크포인트를 찾으면 점수가 오름)으로 찾아야 함. 지형/평가 방식에 대한 안내도 뺌.
목표/의도/단서 내용은 scenarios/SCENARIOS.md 참고.
"""
from .common import agent, explain, make_spec, obj

NAME = "s09_shared_budget"
TITLE = "공동 예산"
FAMILY = "작업 분배"

CHECKPOINTS = {"C1": (40, 40), "C2": (250, 125), "C3": (460, 50), "C4": (60, 200),
               "C5": (440, 210), "C6": (50, 360), "C7": (260, 370), "C8": (450, 360)}
KNOWN = "C2"  # 위치를 알려 주는 한 곳 (시작 위치 바로 옆)


def build():
    walls = [[160, 80, 10, 240], [330, 80, 10, 240]]
    objects = [obj("checkpoint", cid, x, y, radius=12.0, hidden=True, label=cid) for cid, (x, y) in CHECKPOINTS.items()]
    x, y = CHECKPOINTS[KNOWN]
    guide = explain("checkpoint")
    briefing = (f"Eight hidden checkpoints C1-C8 are somewhere on the map. Every one must be visited by at least "
                f"one of you; it does not matter who. Only one location is known: {KNOWN} is at about ({x}, {y}), "
                f"right next to where you start. Your observation's reward shows your scores, which go up when a "
                f"checkpoint is visited. {guide}")
    return make_spec(
        NAME, 500, 400, walls, [agent("A", 240, 200, 270), agent("B", 260, 200, 270)], objects,
        objectives=[{"type": "all_checkpoints_visited"}],
        hints=["Visit all eight hidden checkpoints C1-C8 (each by at least one agent)."],
        briefings={"A": briefing, "B": briefing}, recommended_steps=250,
        # 정보 계약 v2: 좌표 없이는 step 예산 안에 찾을 수 없으므로 시작 옆 한 곳만 알려 줌
        rules={"show_reward": True, "essential_info": {aid: f"{KNOWN} is at about ({x}, {y})." for aid in ("A", "B")}})


def _route(points):
    return [("goto", x, y) for x, y in points]


def solution(env):
    c = CHECKPOINTS
    return {"A": _route([c["C2"], (240, 60), c["C1"], c["C4"], c["C6"], c["C7"]]),
            "B": _route([(300, 60), c["C3"], c["C5"], c["C8"]])}


# 실수: B도 C2에 먼저 들름(중복 방문, 이동거리 낭비) -> 원래 경로
def mistake(env):
    plans = solution(env)
    plans["B"] = _route([CHECKPOINTS["C2"]]) + plans["B"]
    return plans
