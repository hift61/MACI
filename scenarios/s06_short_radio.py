"""s06 짧은 무전 (통신 규약) - 10자/5 step 제한 무전으로 상대 방 4x4 패널의 6자리 순서를 서로 전달.
목표/의도/단서 내용은 scenarios/SCENARIOS.md 참고.
"""
from .common import agent, explain, make_spec, obj

NAME = "s06_short_radio"
TITLE = "짧은 무전"
FAMILY = "통신 규약"

RULES = {"message_max_chars": 10, "message_interval": 5}
ROOM_X0 = {"A": 0, "B": 230}
CODES = {  # 각 방 패널의 정답 (그 정답은 '다른 방' 단서에 적혀 있음)
    "A": ["r2c3", "r4c1", "r1c4", "r3c2", "r2c2", "r4c4"],
    "B": ["r1c1", "r3c3", "r2c4", "r4c2", "r1c3", "r3c1"],
}
ROW_WORDS = ["the top row", "the second row from the top", "the third row from the top", "the bottom row"]
COL_WORDS = ["the first column from the left", "the second column from the left",
             "the third column from the left", "the last column on the right"]


def cell_pos(room, label):
    r, c = int(label[1]), int(label[3])
    return ROOM_X0[room] + 40 + 35 * (c - 1), 40 + 35 * (r - 1)


def describe(code):
    parts = [f"{ROW_WORDS[int(l[1]) - 1]}, {COL_WORDS[int(l[3]) - 1]}" for l in code]
    return "; then ".join(parts) + "."


def build():
    walls = [[210, 0, 20, 260]]
    objects = []
    for room in ("A", "B"):
        other = "B" if room == "A" else "A"
        objects.append(obj("keypad", f"panel_{room}", ROOM_X0[room] + 105, 200, code=CODES[room],
                           mode="sequence", label=f"4x4 panel of room {room}"))
        for r in range(1, 5):
            for c in range(1, 5):
                x, y = cell_pos(room, f"r{r}c{c}")
                objects.append(obj("keypad_button", f"{room}_r{r}c{c}", x, y, panel=f"panel_{room}",
                                   label=f"r{r}c{c}"))
        objects.append(obj("clue", f"clue_{room}", ROOM_X0[room] + (170 if room == "A" else 30), 235,
                           hidden=False, content={
                               "about": f"This note describes the code of panel_{other} in ROOM {other} "
                                        f"(not the panel in your room).",
                               "code": f"Press these 6 buttons of panel_{other} in order: {describe(CODES[other])}",
                               "panel": "Each panel is a 4x4 grid of buttons labelled r<row>c<column> (r1 = top "
                                        "row, c1 = left column). A wrong press clears the panel; start again.",
                               "radio": "Radio limits: at most 10 characters per message and at most one message "
                                        "every 5 steps. Longer or more frequent messages are refused.",
                           }))
    guide = explain("keypad")
    briefings = {
        room: f"You are in room {room} ({'left' if room == 'A' else 'right'}) with panel_{room}. Agent "
              f"{'B' if room == 'A' else 'A'} is in the other room. A wall separates you. Read clue_{room}: it "
              f"holds the OTHER room's code, while your own code is written in your teammate's room. {guide}"
        for room in ("A", "B")
    }
    return make_spec(
        NAME, 440, 260, walls, [agent("A", 105, 220, 270), agent("B", 335, 220, 270)], objects,
        objectives=[{"type": "keypad_solved", "panel_id": "panel_A"},
                    {"type": "keypad_solved", "panel_id": "panel_B"}],
        hints=["Solve panel_A (room A) and panel_B (room B)."],
        briefings=briefings, rules=RULES, recommended_steps=200)


def _presses(room, labels):
    plan = []
    for label in labels:
        x, y = cell_pos(room, label)
        plan += [("goto", x, y), ("act", {"type": "press_button", "button_id": f"{room}_{label}"})]
    return plan


def solution(env):
    return {room: _presses(room, CODES[room]) for room in ("A", "B")}


# 실수: A가 첫 칸을 잘못 누름(패널 초기화) -> 정답
def mistake(env):
    plans = solution(env)
    plans["A"] = _presses("A", ["r1c1"]) + plans["A"]
    return plans
