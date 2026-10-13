"""s05 확인의 문제 (통신 규약) - 메시지가 사라지거나 늦게 오는 상황에서 '같은 step'에 판 밟기.
무전이 불안정하다는 사실은 단서에 없음 (에이전트가 직접 알아채야 함).
목표/의도/단서 내용은 scenarios/SCENARIOS.md 참고.
"""
from .common import agent, make_spec, obj

NAME = "s05_lossy_sync"
TITLE = "확인의 문제"
FAMILY = "통신 규약"

RULES = {"message_loss": 0.35, "message_delay": [0, 2], "seed": 11}


def build():
    walls = [[210, 0, 20, 240]]
    manual = {
        # 무전 상태(손실/지연)는 알려 주지 않음 - 메시지가 사라지거나 늦는다는 것을 스스로 알아채야 함
        "pads": "pad_A and pad_B must be entered in the SAME step. Entering means moving onto a pad from "
                "outside its radius.",
        "failure": "If only one pad is entered, whoever stands on a pad is pushed back and both pads ignore "
                   "entries for a few steps.",
        "clock": "Every observation contains the shared step number (self.step).",
    }
    objects = [
        obj("sync_pad", "pad_A", 105, 60, group="sync", tolerance=0, return_x=105, return_y=110, cooldown=3),
        obj("sync_pad", "pad_B", 335, 60, group="sync", tolerance=0, return_x=335, return_y=110, cooldown=3),
        obj("clue", "manual_A", 40, 200, content=manual, hidden=False),
        obj("clue", "manual_B", 400, 200, content=manual, hidden=False),
    ]
    return make_spec(
        NAME, 440, 240, walls, [agent("A", 105, 180, 270), agent("B", 335, 180, 270)], objects,
        objectives=[{"type": "sync_success", "group": "sync"}],
        hints=["Enter pad_A and pad_B in exactly the same step."],
        rules=RULES, recommended_steps=150)


def _enter_at(pad_x, step):
    return [("goto", pad_x, 80), ("face", 270), ("at_step", step), ("act", {"type": "move_forward", "distance": 20})]


def solution(env):
    return {"A": _enter_at(105, 20), "B": _enter_at(335, 20)}


# 실수: A가 혼자 먼저 밟음 -> 밀려나고 판이 3 step 꺼짐 -> 약속한 step에 다시
def mistake(env):
    return {"A": _enter_at(105, 8) + _enter_at(105, 24), "B": _enter_at(335, 24)}
