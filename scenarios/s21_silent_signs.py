"""s21 흔적으로 말하기 (간접 소통) - 메시지 금지. A만 코드를 읽고 B만 패널을 누름. 돌멩이와 매트로 뜻을 전달.
목표/의도/단서 내용은 scenarios/SCENARIOS.md 참고.
"""
from .common import agent, make_spec, obj

NAME = "s21_silent_signs"
TITLE = "흔적으로 말하기"
FAMILY = "간접 소통"

COLORS = ["red", "green", "blue", "yellow", "purple"]
CODE = ["green", "blue", "red", "yellow"]
MAT_X = {c: 120 + 40 * i for i, c in enumerate(COLORS)}   # 마당의 색 매트 (y=160)
BUTTON_X = {c: 260 + 25 * i for i, c in enumerate(COLORS)}  # B만 누를 수 있는 패널 버튼 (y=290)
STONES = [(40, 120), (60, 200), (90, 260), (200, 40), (300, 60), (360, 120), (380, 220), (30, 290),
          (150, 60), (250, 100), (150, 230), (340, 30)]


def build():
    objects = [
        obj("variant_clue", "secret_code", 60, 60, hidden=False,
            content="(The ink is too faint for you to read.)",
            variants={"A": f"Code for color_panel, in this order: {', '.join(CODE)}."}),
        obj("keypad", "color_panel", 310, 265, code=CODE, mode="sequence", operators=["B"],
            label="4-colour panel"),
    ]
    objects += [obj("keypad_button", f"btn_{c}", BUTTON_X[c], 290, panel="color_panel", label=c) for c in COLORS]
    objects += [obj("marker", f"mat_{c}", MAT_X[c], 160, label=f"{c} mat") for c in COLORS]
    objects += [obj("item", f"stone_{i + 1}", x, y) for i, (x, y) in enumerate(STONES)]
    objects.append(obj("clue", "rules", 200, 220, hidden=False, content={
        "silence": "Messages are refused here.",
        "secret_code": "Only agent A can read the faint note secret_code.",
        "panel": "color_panel opens when 4 colours (out of red, green, blue, yellow, purple; none repeated) are "
                 "pressed in the right order.",
        "yard": "Anything dropped stays where it was dropped, and everyone can see it.",
    }))
    return make_spec(
        NAME, 400, 320, [], [agent("A", 100, 100, 270), agent("B", 300, 220, 270)], objects,
        objectives=[{"type": "keypad_solved", "panel_id": "color_panel"}],
        hints=["Unlock color_panel (only agent B can press it; only agent A can read the code)."],
        rules={"message_disabled": True}, recommended_steps=200)


def _press(colors):
    plan = []
    for c in colors:
        plan += [("goto", BUTTON_X[c], 278), ("act", {"type": "press_button", "button_id": f"btn_{c}"})]
    return plan


# 정답 흐름의 예: A가 코드 순서대로 매트에 돌을 1, 2, 3, 4개 올림 -> B가 개수로 순서를 읽고 누름
def solution(env):
    from . import oracle
    plan_a = []
    for order, color in enumerate(CODE, start=1):
        plan_a += [("call", oracle.fetch("stone", count=order, where=lambda o: abs(o["y"] - 160) > 15)),
                   ("goto", MAT_X[color], 160),
                   ("call", oracle.drop_prefix("stone"))]
    signed = lambda e: sum(o["object_id"].startswith("stone") and abs(o["y"] - 160) < 2
                           for o in e.objects.values()) >= 10
    return {"A": plan_a, "B": [("until", signed)] + _press(CODE)}


# 실수: B가 신호를 잘못 읽고(돌이 많은 순서로) 눌러 패널이 초기화됨 -> 다시 읽고 정답
def mistake(env):
    plans = solution(env)
    plans["B"] = plans["B"][:1] + _press(["yellow"]) + plans["B"][1:]
    return plans
