"""s04 반쪽 마스터마인드 (공동 추론) - A는 색 코드를 입력만, 결과(맞은 개수)는 B의 방 화면에만 나옴. 단계형 3단계.
  1단계 4색 중 3개 (24가지), 2단계 5색 중 4개 (120가지, 원래 s04), 3단계 6색 중 5개 (720가지)
목표/의도/단서 내용은 scenarios/SCENARIOS.md 참고.
"""
from .common import STAGE_RULES, STAGED_OBJECTIVES, agent, explain, make_spec, obj, stage

NAME = "s04_half_mastermind"
TITLE = "반쪽 마스터마인드"
FAMILY = "공동 추론"

ALL_COLORS = ["red", "green", "blue", "yellow", "purple", "orange"]
STAGES = {  # 단계 -> (쓰는 색, 비밀 코드). 코드는 서로 다른 색, 중복 없음
    1: (ALL_COLORS[:4], ["green", "yellow", "red"]),
    2: (ALL_COLORS[:5], ["blue", "red", "purple", "green"]),
    3: (ALL_COLORS[:6], ["orange", "blue", "yellow", "red", "purple"]),
}


def button_x(n, color):
    return 35 + 30 * STAGES[n][0].index(color)


def _stage(n):
    colors, code = STAGES[n]
    palette = ", ".join(colors)
    length = len(code)
    panel, screen = f"color_panel_{n}", f"result_screen_{n}"
    objects = [obj("keypad", panel, 105, 25, code=code, mode="mastermind", display_id=screen,
                   label=f"{length}-colour code panel")]
    objects += [obj("keypad_button", f"btn{n}_{c}", button_x(n, c), 70, panel=panel, label=c) for c in colors]
    objects += [
        obj("display", screen, 335, 40, label="result of the code panel in room A",
            content={"attempt": 0, "exact": None, "misplaced": None}),
        obj("clue", f"panel_manual_{n}", 105, 200, hidden=False, content={
            "code": f"{panel} takes a code of {length} colours chosen from {palette}. No colour appears twice "
                    f"in the code.",
            "checking": f"After every {length}th press the panel checks the code and clears itself. The result "
                        f"appears ONLY on {screen} in room B: 'exact' = right colour in the right slot, "
                        f"'misplaced' = right colour in the wrong slot.",
            "retries": "Wrong codes cost nothing but time. You may try as often as you need.",
        }),
        obj("clue", f"screen_manual_{n}", 335, 200, hidden=False, content={
            "screen": f"{screen} shows only the result of the latest code entered on the panel in room A: "
                      f"attempt number, 'exact' and 'misplaced'. It never shows which colours were entered.",
            "panel": f"The code uses {length} different colours out of {palette}.",
        }),
    ]
    return stage(f"{length} of {len(colors)} colours",
                 f"Solve {panel} in room A: a code of {length} different colours out of {len(colors)}. Room A reads "
                 f"panel_manual_{n}, room B reads screen_manual_{n}.",
                 [{"type": "keypad_solved", "panel_id": panel}], objects)


def build():
    walls = [[210, 0, 20, 260]]
    guide = explain("keypad", "display")
    briefings = {
        "A": f"You are in room A (left) with the colour code panel and its colour buttons. Agent B is in room B "
             f"(right) and is the only one who can see the result screen. A wall separates you. {STAGE_RULES} {guide}",
        "B": f"You are in room B (right) with the result screen. Agent A is in room A (left) with the code panel. "
             f"A wall separates you. You cannot press anything useful yourself. {STAGE_RULES} {guide}",
    }
    return make_spec(
        NAME, 440, 260, walls, [agent("A", 105, 160, 270), agent("B", 335, 160, 270)], [],
        objectives=STAGED_OBJECTIVES,
        hints=["Clear all three stages; each stage ends when that stage's colour panel in room A is solved."],
        briefings=briefings, rules={"stages": [_stage(n) for n in (1, 2, 3)]}, recommended_steps=400)


def _presses(n, colors):
    plan = []
    for c in colors:
        plan += [("goto", button_x(n, c), 82), ("act", {"type": "press_button", "button_id": f"btn{n}_{c}"})]
    return plan


def solution(env):
    return {"A": [item for n in (1, 2, 3) for item in [("stage", n)] + _presses(n, STAGES[n][1])], "B": []}


# 실수(2단계): 틀린 코드 한 번 입력 (결과만 화면에 뜨고 패널이 비워짐) -> 정답
def mistake(env):
    plan = []
    for n in (1, 2, 3):
        plan += [("stage", n)] + (_presses(2, ["red", "green", "blue", "yellow"]) if n == 2 else [])
        plan += _presses(n, STAGES[n][1])
    return {"A": plan, "B": []}
