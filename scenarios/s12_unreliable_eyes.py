"""s12 믿을 수 없는 눈 (신뢰, 검증) - 같은 단서가 에이전트마다 다른 곳이 틀려 보임. 비교+검산으로 코드 복원.
목표/의도/단서 내용은 scenarios/SCENARIOS.md 참고.
"""
from .common import agent, make_spec, obj

NAME = "s12_unreliable_eyes"
TITLE = "믿을 수 없는 눈"
FAMILY = "신뢰, 검증"

CODE = ["4", "7", "3", "9", "2", "6"]  # 합 31
# 단서 -> (실제 내용, A에게 보이는 내용, B에게 보이는 내용). 틀린 자리는 단서마다 한 사람만
CLUES = {
    "clue_1": ((60, 60), "Digits 1-2 of the code: 4 7", "Digits 1-2 of the code: 4 1", "Digits 1-2 of the code: 4 7"),
    "clue_2": ((200, 40), "Digits 3-4 of the code: 3 9", "Digits 3-4 of the code: 3 9", "Digits 3-4 of the code: 8 9"),
    "clue_3": ((340, 60), "Digits 5-6 of the code: 2 6", "Digits 5-6 of the code: 5 6", "Digits 5-6 of the code: 2 6"),
}


def key_x(digit):
    return 65 + 30 * int(digit)


def build():
    objects = [obj("variant_clue", cid, x, y, content=true, variants={"A": seen_a, "B": seen_b}, hidden=False)
               for cid, ((x, y), true, seen_a, seen_b) in CLUES.items()]
    objects += [
        obj("clue", "clue_4", 200, 140, hidden=False,
            content={"sum of the digits": sum(int(d) for d in CODE),
                     "note": "Checksum printed in huge letters, readable by everyone: the six digits of the code "
                             "add up to this number."}),
        obj("clue", "reading_note", 300, 140, hidden=False, content={"notes": "The small notes are hard to read: digits on them may look different to different readers."}),
        obj("keypad", "code_panel", 200, 210, code=CODE, mode="sequence", label="6-digit code panel"),
    ]
    objects += [obj("keypad_button", f"key_{d}", key_x(d), 250, panel="code_panel", label=str(d)) for d in range(10)]
    return make_spec(
        NAME, 400, 300, [], [agent("A", 150, 180, 270), agent("B", 250, 180, 270)], objects,
        objectives=[{"type": "keypad_solved", "panel_id": "code_panel"}],
        hints=["Enter the correct 6-digit code on code_panel."],
        recommended_steps=120)


def _presses(digits):
    plan = []
    for d in digits:
        plan += [("goto", key_x(d), 238), ("act", {"type": "press_button", "button_id": f"key_{d}"})]
    return plan


def solution(env):
    return {"A": _presses(CODE), "B": []}


# 실수: A가 자기 눈에 보인 대로(4 1 ...) 입력 -> 두 번째 자리에서 초기화 -> 정답
def mistake(env):
    return {"A": _presses(["4", "1"]) + _presses(CODE), "B": []}
