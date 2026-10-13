"""s13 엇갈린 증언 (신뢰·검증 + 정보 분할) - MAP_GUIDE.md 기준으로 만든 단계형 맵. 축 B + C.
두 방에 같은 코드를 '다르게 틀리게' 적은 쪽지가 하나씩 있다. 패널(입력)은 A의 방에만, 채점 화면은 B의 방에만 있다.
쪽지가 틀릴 수 있다는 것, 두 쪽지가 같은 코드라는 것, 화면이 패널의 결과라는 것은 알려 주지 않는다.
  1단계: 3자리. 각 쪽지에 틀린 자리 1개, 두 방 모두 합계 쪽지. 패널은 틀리면 바로 비워짐(sequence)
  2단계: 4자리. 각 쪽지에 틀린 자리 1개, 합계 없음. 패널은 4자리를 다 넣어야 채점, 결과는 B 방 화면에만(mastermind)
  3단계: 5자리. 각 쪽지에 틀린 자리 2개씩(서로 다른 자리), 합계 쪽지 + B 방 채점 화면 (합계로 후보 4개 -> 채점으로 결정)
"""
from .common import STAGED_OBJECTIVES, agent, make_spec, obj, stage

NAME = "s13_crossed_testimony"
TITLE = "엇갈린 증언"
FAMILY = "신뢰, 검증"

WALL_X = 210
DIGIT_X = {d: 22 + 18 * d for d in range(10)}  # A 방의 숫자 버튼 0~9 (y=60)
STAGES = {  # 단계 -> (정답, A 방 쪽지, B 방 쪽지, 합계 쪽지 여부, 패널 방식)
    1: ([5, 2, 8], [5, 7, 8], [5, 2, 6], True, "sequence"),
    2: ([3, 9, 1, 6], [3, 9, 7, 6], [8, 9, 1, 6], False, "mastermind"),
    3: ([4, 7, 3, 9, 2], [4, 0, 4, 9, 2], [4, 7, 3, 8, 9], True, "mastermind"),
}


def _digits(values):
    return " ".join(str(v) for v in values)


def _stage(n):
    code, reading_a, reading_b, checksum, mode = STAGES[n]
    panel, screen = f"panel_{n}", f"screen_{n}"
    objects = [obj("keypad", panel, 105, 25, code=[str(d) for d in code], mode=mode, display_id=screen)]
    objects += [obj("keypad_button", f"k{n}_{d}", x, 60, panel=panel, label=str(d)) for d, x in DIGIT_X.items()]
    objects += [
        obj("display", screen, 330, 40, content={}),
        obj("clue", f"note_{n}a", 150, 210, hidden=False, content={"code": _digits(reading_a)}),
        obj("clue", f"note_{n}b", 300, 210, hidden=False, content={"code": _digits(reading_b)}),
    ]
    if checksum:
        objects += [obj("clue", f"sum_{n}a", 40, 230, hidden=False, content={"sum": sum(code)}),
                    obj("clue", f"sum_{n}b", 410, 230, hidden=False, content={"sum": sum(code)})]
    return stage(f"{len(code)} digits", f"Open {panel}.", [{"type": "keypad_solved", "panel_id": panel}], objects)


def build():
    walls = [[WALL_X, 0, 20, 260]]
    briefings = {"A": "You are in the left room. Agent B is in the right room behind a wall.",
                 "B": "You are in the right room. Agent A is in the left room behind a wall."}
    return make_spec(
        NAME, 440, 260, walls, [agent("A", 60, 200, 270), agent("B", 380, 120, 180)], [],
        objectives=STAGED_OBJECTIVES, hints=["Open the panel of every stage."],
        briefings=briefings, rules={"stages": [_stage(n) for n in (1, 2, 3)]}, recommended_steps=280)


def _presses(n, digits):
    plan = []
    for d in digits:
        plan += [("goto", DIGIT_X[d], 72), ("act", {"type": "press_button", "button_id": f"k{n}_{d}"})]
    return plan


def solution(env):
    return {"A": [item for n in (1, 2, 3) for item in [("stage", n)] + _presses(n, STAGES[n][0])], "B": []}


# 실수: 3단계에서 합계만 맞는 다른 후보(4 0 3 9 9)를 먼저 넣음 -> B 화면에 결과만 남고 패널이 비워짐 -> 정답
def mistake(env):
    plan = []
    for n in (1, 2, 3):
        plan += [("stage", n)] + (_presses(3, [4, 0, 3, 9, 9]) if n == 3 else []) + _presses(n, STAGES[n][0])
    return {"A": plan, "B": []}
