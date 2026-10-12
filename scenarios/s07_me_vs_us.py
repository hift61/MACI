"""s07 나 vs 우리 (사회적 딜레마) - 곧 사라지는 개인 보너스 보석 vs 둘이 함께 옮겨야 하는 팀 상자.
목표/의도/단서 내용은 scenarios/SCENARIOS.md 참고.
"""
from .common import agent, explain, make_spec, obj

NAME = "s07_me_vs_us"
TITLE = "나 vs 우리"
FAMILY = "사회적 딜레마"

GEMS = {"gem_1": (30, 30), "gem_2": (430, 30), "gem_3": (30, 290)}
GEM_POINTS, GEM_EXPIRES = 25.0, 40


def build():
    walls = [[150, 70, 10, 90], [300, 70, 10, 90]]
    objects = [
        obj("item", "crate", 230, 150, category="coop", required_agents=2),
        obj("receptacle", "dock", 410, 280, accepts=["crate"], target=1, radius=20.0, label="loading dock"),
    ]
    objects += [obj("bonus_item", gid, x, y, points=GEM_POINTS, expires_at=GEM_EXPIRES) for gid, (x, y) in GEMS.items()]
    objects.append(obj("clue", "notice", 230, 300, hidden=False, content={
        "team_goal": "Deliver the crate to the dock (drop it inside the dock's radius). The crate is a coop item: "
                     "it can only be picked up while BOTH of you stand within about 15 units of it, and its carrier "
                     "cannot move unless the other agent stays within about 15 units.",
        "gems": f"Three gems lie in the far corners. A gem is worth {int(GEM_POINTS)} personal points to whoever "
                f"picks it up, but every gem vanishes at step {GEM_EXPIRES}.",
        "scoring": "Your own score counts gems. The team score counts whether and how fast the crate reaches the dock.",
    }))
    guide = explain("receptacle", "bonus_item")
    briefing = (f"You and your teammate start in the middle of a hall. Read the clue 'notice'. {guide}")
    return make_spec(
        NAME, 460, 320, walls, [agent("A", 215, 250, 270), agent("B", 245, 250, 270)], objects,
        objectives=[{"type": "delivery_complete", "receptacle_id": "dock"}],
        hints=["Deliver the coop item 'crate' to the receptacle 'dock'."],
        briefings={"A": briefing, "B": briefing}, recommended_steps=120)


def _team_carry():
    from .oracle import carry_legs
    legs = carry_legs((230, 162), [(405, 280)])
    return {
        "A": [("goto", 230, 162), ("barrier", "pick"), ("act", {"type": "pick_up", "object_id": "crate"}),
              ("barrier", "carry")] + legs + [("act", {"type": "drop", "object_id": "crate"})],
        "B": [("goto", 230, 162), ("barrier", "pick"), ("barrier", "carry")] + legs,
    }


def solution(env):
    return _team_carry()


# 실수(욕심): A가 먼저 보석을 주우러 갔다 옴 -> B는 상자 옆에서 기다림 -> 함께 운반
def mistake(env):
    plans = _team_carry()
    plans["A"] = [("goto", 30, 290), ("act", {"type": "pick_up", "object_id": "gem_3"})] + plans["A"]
    return plans
