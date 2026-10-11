"""s04 반쪽 마스터마인드 (공동 추론) - A는 색 코드를 입력만, 결과(맞은 개수)는 B의 방 화면에만 나옴.
목표/의도/단서 내용은 scenarios/SCENARIOS.md 참고.
"""
from .common import agent, explain, make_spec, obj

NAME = "s04_half_mastermind"
TITLE = "반쪽 마스터마인드"
FAMILY = "공동 추론"

COLORS = ["red", "green", "blue", "yellow", "purple"]
BUTTON_X = {c: 35 + 35 * i for i, c in enumerate(COLORS)}
CODE = ["blue", "red", "purple", "green"]  # 비밀 코드 (색 5개 중 4개, 중복 없음)


def build():
    walls = [[210, 0, 20, 260]]
    objects = [obj("keypad", "color_panel", 105, 25, code=CODE, mode="mastermind", display_id="result_screen",
                   label="4-colour code panel")]
    objects += [obj("keypad_button", f"btn_{c}", BUTTON_X[c], 70, panel="color_panel", label=c) for c in COLORS]
    objects += [
        obj("display", "result_screen", 335, 40, label="result of the code panel in room A",
            content={"attempt": 0, "exact": None, "misplaced": None}),
        obj("clue", "panel_manual", 105, 200, hidden=False, content={
            "code": "color_panel takes a code of 4 colours chosen from red, green, blue, yellow, purple. "
                    "No colour appears twice in the code.",
            "checking": "After every 4th press the panel checks the code and clears itself. The result appears "
                        "ONLY on result_screen in room B: 'exact' = right colour in the right slot, "
                        "'misplaced' = right colour in the wrong slot.",
            "retries": "Wrong codes cost nothing but time. You may try as often as you need.",
        }),
        obj("clue", "screen_manual", 335, 200, hidden=False, content={
            "screen": "result_screen shows only the result of the latest code entered on the panel in room A: "
                      "attempt number, 'exact' and 'misplaced'. It never shows which colours were entered.",
            "panel": "The code uses 4 different colours out of red, green, blue, yellow, purple.",
        }),
    ]
    guide = explain("keypad", "display")
    briefings = {
        "A": f"You are in room A (left) with color_panel and its five colour buttons. Agent B is in room B "
             f"(right) and is the only one who can see result_screen. A wall separates you. Read panel_manual. {guide}",
        "B": f"You are in room B (right) with result_screen. Agent A is in room A (left) with the code panel. "
             f"A wall separates you. You cannot press anything useful yourself. Read screen_manual. {guide}",
    }
    return make_spec(
        NAME, 440, 260, walls, [agent("A", 105, 160, 270), agent("B", 335, 160, 270)], objects,
        objectives=[{"type": "keypad_solved", "panel_id": "color_panel"}],
        hints=["Unlock color_panel in room A by entering the secret 4-colour code."],
        briefings=briefings, recommended_steps=200)


def _presses(colors):
    plan = []
    for c in colors:
        plan += [("goto", BUTTON_X[c], 82), ("act", {"type": "press_button", "button_id": f"btn_{c}"})]
    return plan


def solution(env):
    return {"A": _presses(CODE), "B": []}


# 실수: 틀린 코드 한 번 입력 (결과만 화면에 뜨고 패널이 비워짐) -> 정답
def mistake(env):
    return {"A": _presses(["red", "green", "blue", "yellow"]) + _presses(CODE), "B": []}
