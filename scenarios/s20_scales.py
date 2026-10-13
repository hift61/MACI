"""s20 저울 맞추기 (공동 추론) - 숨은 무게의 상자를 각자 방 저울로 재고, 합쳐서 금고 저울을 정확히 맞춤.
목표/의도/단서 내용은 scenarios/SCENARIOS.md 참고.
"""
from .common import agent, hwall, make_spec, obj

NAME = "s20_scales"
TITLE = "저울 맞추기"
FAMILY = "공동 추론"

TARGET = 23
# 상자 -> (x, y, 무게). 한 방의 상자만으로는 23을 만들 수 없음
CRATES = {
    "crate_a1": (40, 60, 3), "crate_a2": (80, 60, 7), "crate_a3": (120, 60, 5), "crate_a4": (160, 60, 9),
    "crate_b1": (280, 60, 4), "crate_b2": (320, 60, 6), "crate_b3": (360, 60, 8), "crate_b4": (400, 60, 2),
}


def build():
    walls = [[220, 0, 20, 210]] + hwall(200, 0, 220, gaps=[(110, 40)]) + hwall(200, 240, 460, gaps=[(350, 40)])
    objects = [obj("weighted_item", cid, x, y, weight=w, label="crate") for cid, (x, y, w) in CRATES.items()]
    objects += [
        obj("scale", "scale_A", 110, 150, radius=15.0, label="test scale"),
        obj("scale", "scale_B", 350, 150, radius=15.0, label="test scale"),
        obj("scale", "vault_scale", 230, 280, radius=20.0, target=TARGET, label="vault scale"),
        obj("clue", "vault_note", 230, 230, hidden=False, content={
            "target weight of vault_scale": TARGET,
            "vault": "vault_scale balances when the crates lying on it weigh exactly this target in total. It "
                     "never shows numbers.",
            "test_scales": "A test scale shows the exact total weight of the crates lying on it.",
            "crates": "Crate weights are hidden.",
        }),
    ]
    return make_spec(
        NAME, 460, 320, walls, [agent("A", 110, 120, 270), agent("B", 350, 120, 270)], objects,
        objectives=[{"type": "scale_balanced", "scale_id": "vault_scale"}],
        hints=[f"Make vault_scale read 'balanced' (crates on it weigh exactly {TARGET})."],
        recommended_steps=200)


def _pick(cid):
    x, y, _ = CRATES[cid]
    return [("goto", x, y + 12), ("act", {"type": "pick_up", "object_id": cid})]


def _drop(cid):
    return [("act", {"type": "drop", "object_id": cid})]


def solution(env):
    # 9 (a4) + 8 (b3) + 6 (b2) = 23
    return {
        "A": _pick("crate_a4") + [("goto", 110, 180), ("goto", 110, 230), ("goto", 222, 280)] + _drop("crate_a4"),
        "B": _pick("crate_b2") + _pick("crate_b3") + [("goto", 350, 180), ("goto", 350, 230),
                                                      ("goto", 238, 280)] + _drop("crate_b2") + _drop("crate_b3"),
    }


# 실수: A가 상자 둘(7 + 9)을 올려 무게 초과 -> 하나(crate_a2)를 다시 집어 냄
def mistake(env):
    plans = solution(env)
    plans["A"] = (_pick("crate_a2") + _pick("crate_a4") + [("goto", 110, 180), ("goto", 110, 230),
                                                         ("goto", 222, 280)] + _drop("crate_a2") + _drop("crate_a4")
                  + [("until", lambda e: e.objects["vault_scale"]["reading"] == "too heavy"),
                     ("act", {"type": "pick_up", "object_id": "crate_a2"})])
    return plans
