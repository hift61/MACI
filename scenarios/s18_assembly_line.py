"""s18 조립 라인 (작업 분배, 흐름) - 원석 -> 주괴 -> 톱니바퀴가 유리벽 창구를 세 번 건너는 생산 라인.
목표/의도/단서 내용은 scenarios/SCENARIOS.md 참고.
"""
from .common import agent, explain, make_spec, obj

NAME = "s18_assembly_line"
TITLE = "조립 라인"
FAMILY = "작업 분배"

GEARS_NEEDED = 3
WEST, EAST = (224, 150), (236, 150)  # 창구(유리벽) 양쪽에서 물건을 내려놓는 자리


def build():
    glass = [[225, 0, 10, 300]]
    objects = [
        obj("spawner", "ore_vein", 0, 0, area=[30, 30, 190, 270], every=6, max_alive=2, prefix="ore",
            label="raw ore"),
        obj("station", "smelter", 290, 90, input="ore", output="ingot", process_steps=3, out_x=290, out_y=112,
            label="smelter: ore -> ingot"),
        obj("station", "press", 160, 210, input="ingot", output="gear", process_steps=3, out_x=160, out_y=232,
            label="press: ingot -> gear"),
        obj("receptacle", "dock", 370, 230, accepts=["gear"], target=GEARS_NEEDED, radius=20.0,
            label="shipping dock"),
        obj("clue", "work_order", 200, 30, hidden=False, content={
            "goal": f"Ship {GEARS_NEEDED} gears: drop them on the shipping dock in the EAST area.",
            "recipe": "ore (appears in the WEST area) -> smelter (EAST area) makes an ingot -> press (WEST area) "
                      "makes a gear -> dock (EAST area).",
            "counter": "A glass wall separates the two areas. Nobody can cross it, but an item dropped right "
                       "against the glass can be picked up from the other side (pick_up works within about 15 units).",
            "machines": "Each machine handles one item at a time and needs 3 steps per item.",
        }),
    ]
    guide = explain("station", "receptacle")
    briefings = {
        "A": f"You work in the WEST area (ore and the press are here). Agent B works in the EAST area behind the "
             f"glass (smelter and dock). Read the clue 'work_order' (visible from both sides). {guide}",
        "B": f"You work in the EAST area (the smelter and the dock are here). Agent A works in the WEST area "
             f"behind the glass (ore and the press). Read the clue 'work_order' (visible from both sides). {guide}",
    }
    return make_spec(
        NAME, 460, 300, [], [agent("A", 110, 150, 0), agent("B", 340, 150, 180)], objects,
        objectives=[{"type": "delivery_complete", "receptacle_id": "dock"}],
        hints=[f"Deliver {GEARS_NEEDED} gears to the receptacle 'dock' (east area)."],
        briefings=briefings, rules={"glass_walls": glass}, recommended_steps=300)


def _a_cycle(oracle):
    near_counter = (210, 120, 245, 180)
    return [("call", oracle.fetch("ore")), ("goto", *WEST), ("call", oracle.drop_prefix("ore")),
            ("until", oracle.lying("ingot", near_counter)), ("call", oracle.fetch("ingot", region=near_counter)),
            ("goto", 160, 198), ("call", oracle.drop_prefix("ingot")),
            ("until", oracle.lying("gear", (140, 220, 180, 245))), ("call", oracle.fetch("gear")),
            ("goto", *WEST), ("call", oracle.drop_prefix("gear"))]


def _b_cycle(oracle):
    near_counter = (210, 120, 245, 180)
    return [("until", oracle.lying("ore", near_counter)), ("call", oracle.fetch("ore", region=near_counter)),
            ("goto", 290, 102), ("call", oracle.drop_prefix("ore")),
            ("until", oracle.lying("ingot", (270, 100, 310, 125))), ("call", oracle.fetch("ingot")),
            ("goto", *EAST), ("call", oracle.drop_prefix("ingot")),
            ("until", oracle.lying("gear", near_counter)), ("call", oracle.fetch("gear", region=near_counter)),
            ("goto", 370, 242), ("call", oracle.drop_prefix("gear"))]


def solution(env):
    from . import oracle
    return {"A": [step for _ in range(GEARS_NEEDED) for step in _a_cycle(oracle)],
            "B": [step for _ in range(GEARS_NEEDED) for step in _b_cycle(oracle)]}


# 실수: A가 원석을 창구가 아닌 엉뚱한 곳에 두고 B가 기다림 -> 다시 집어서 창구로
def mistake(env):
    from . import oracle
    plans = solution(env)
    plans["A"] = [("call", oracle.fetch("ore")), ("goto", 150, 60), ("call", oracle.drop_prefix("ore")),
                  ("wait", 4)] + plans["A"]
    return plans
