"""s09 공동 예산 (작업 분배) - 숨은 체크포인트 8곳을 누가 가든 다 방문. 팀 총 이동거리로 평가.
좌표는 주지 않음: 시작 지점 쪽지는 체크포인트가 8개(C1~C8)이고 가까이 가야 보인다는 것만 알려 줌.
나머지는 탐색과 점수 피드백(관찰의 reward - 체크포인트를 찾으면 점수가 오름)으로 찾아야 함.
목표/의도/단서 내용은 scenarios/SCENARIOS.md 참고.
"""
from .common import agent, make_spec, obj

NAME = "s09_shared_budget"
TITLE = "공동 예산"
FAMILY = "작업 분배"

CHECKPOINTS = {"C1": (40, 40), "C2": (250, 125), "C3": (460, 50), "C4": (60, 200),
               "C5": (440, 210), "C6": (50, 360), "C7": (260, 370), "C8": (450, 360)}


def build():
    walls = [[160, 80, 10, 240], [330, 80, 10, 240]]
    objects = [obj("checkpoint", cid, x, y, radius=12.0, hidden=True, label=cid) for cid, (x, y) in CHECKPOINTS.items()]
    objects.append(obj("clue", "survey_note", 250, 175, hidden=False, content={
        "survey": "There are eight checkpoints, C1 to C8. They only show up when you are close to them.",
        "visits": "It does not matter who visits a checkpoint."}))
    return make_spec(
        NAME, 500, 400, walls, [agent("A", 240, 200, 270), agent("B", 260, 200, 270)], objects,
        objectives=[{"type": "all_checkpoints_visited"}],
        hints=["Visit all eight hidden checkpoints C1-C8 (each by at least one agent)."],
        rules={"show_reward": True}, recommended_steps=250)


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
