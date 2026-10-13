"""s06 짧은 무전 (통신 규약) - 10자/5 step 제한 무전으로 상대 방 4x4 패널의 순서를 서로 전달. 단계형 3단계.
  같은 무전 제한 아래 코드 길이만 2 -> 4 -> 6칸으로 늘어남 (3단계가 원래 s06과 같은 난이도)
목표/의도/단서 내용은 scenarios/SCENARIOS.md 참고.
"""
from .common import STAGED_OBJECTIVES, agent, make_spec, obj, stage

NAME = "s06_short_radio"
TITLE = "짧은 무전"
FAMILY = "통신 규약"

RADIO = {"message_max_chars": 10, "message_interval": 5}
ROOM_X0 = {"A": 0, "B": 230}
CODES = {  # 단계 -> 각 방 패널의 정답 (그 정답은 '다른 방' 단서에 적혀 있음)
    1: {"A": ["r3c2", "r1c4"], "B": ["r2c1", "r4c3"]},
    2: {"A": ["r1c2", "r4c4", "r2c1", "r3c3"], "B": ["r4c1", "r2c2", "r3c4", "r1c3"]},
    3: {"A": ["r2c3", "r4c1", "r1c4", "r3c2", "r2c2", "r4c4"],
        "B": ["r1c1", "r3c3", "r2c4", "r4c2", "r1c3", "r3c1"]},
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


def _stage(n):
    objects = []
    for room in ("A", "B"):
        other = "B" if room == "A" else "A"
        objects.append(obj("keypad", f"panel_{room}{n}", ROOM_X0[room] + 105, 200, code=CODES[n][room],
                           mode="sequence", label="4x4 panel"))
        for r in range(1, 5):
            for c in range(1, 5):
                x, y = cell_pos(room, f"r{r}c{c}")
                objects.append(obj("keypad_button", f"{room}{n}_r{r}c{c}", x, y, panel=f"panel_{room}{n}",
                                   label=f"r{r}c{c}"))
        length = len(CODES[n][other])
        objects.append(obj("clue", f"clue_{room}{n}", ROOM_X0[room] + (170 if room == "A" else 30), 235,
                           hidden=False, content={
                               "about": f"This code opens panel_{other}{n}.",
                               "code": f"Press these {length} buttons of panel_{other}{n} in order: "
                                       f"{describe(CODES[n][other])}",
                               "panel": "Panel buttons are labelled r<row>c<column> (r1 = top row, c1 = left "
                                        "column).",
                               "radio": "Messages here are limited to 10 characters and one message every 5 "
                                        "steps.",
                           }))
    length = len(CODES[n]["A"])
    return stage(f"{length}-button codes", f"Open panel_A{n} and panel_B{n}.",
                 [{"type": "keypad_solved", "panel_id": f"panel_A{n}"},
                  {"type": "keypad_solved", "panel_id": f"panel_B{n}"}], objects)


def build():
    walls = [[210, 0, 20, 260]]
    return make_spec(
        NAME, 440, 260, walls, [agent("A", 105, 220, 270), agent("B", 335, 220, 270)], [],
        objectives=STAGED_OBJECTIVES,
        hints=["Clear all three stages; each stage ends when both rooms' panels of that stage are solved."],
        rules={**RADIO, "stages": [_stage(n) for n in (1, 2, 3)]}, recommended_steps=300)


def _presses(room, n, labels):
    plan = []
    for label in labels:
        x, y = cell_pos(room, label)
        plan += [("goto", x, y), ("act", {"type": "press_button", "button_id": f"{room}{n}_{label}"})]
    return plan


def solution(env):
    return {room: [item for n in (1, 2, 3) for item in [("stage", n)] + _presses(room, n, CODES[n][room])]
            for room in ("A", "B")}


# 실수(3단계): A가 첫 칸을 잘못 누름(패널 초기화) -> 정답
def mistake(env):
    plans = {room: [] for room in ("A", "B")}
    for n in (1, 2, 3):
        for room in ("A", "B"):
            wrong = _presses("A", 3, ["r1c1"]) if (n, room) == (3, "A") else []
            plans[room] += [("stage", n)] + wrong + _presses(room, n, CODES[n][room])
    return plans
