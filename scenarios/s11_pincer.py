"""s11 포위 (시간 예측) - 기둥을 도는 2인용 코어를 둘이 같은 순간 붙잡아 함께 운반.
목표/의도/단서 내용은 scenarios/SCENARIOS.md 참고.
"""
import math

from .common import agent, explain, make_spec, obj

NAME = "s11_pincer"
TITLE = "포위"
FAMILY = "시간 예측"

LOOP = [[330, 60], [330, 260], [130, 260], [130, 60]]  # 코어 순환 경로 (관찰에서 숨김)
SPEED = 12.0


def build():
    walls = [[180, 110, 100, 100]]  # 가운데 기둥 (시야를 가림)
    objects = [
        obj("mover", "core", 130, 60, waypoints=LOOP, speed=SPEED, object_type="item", loop=True,
            extra={"category": "coop", "required_agents": 2, "label": "power core", "_hide_path": True}),
        obj("receptacle", "dock", 420, 295, accepts=["core"], target=1, radius=20.0, label="core dock"),
        obj("clue", "notice", 60, 300, hidden=False, content={
            "core": "The power core (a coop item) keeps moving on its own around the central pillar. Its path "
                    "is not shown; you can only watch where it is while it is in your view.",
            "catch": "It can only be picked up while BOTH of you are within about 15 units of it at the same "
                     "moment. It moves about 12 units per step - faster than you can turn and follow.",
            "deliver": "Once picked up, carry it together to the dock (south-east) and drop it there. If you drop "
                       "it anywhere else it starts running around again.",
        }),
    ]
    guide = explain("receptacle")
    briefing = f"You and your teammate start on opposite sides of a pillar. Read the clue 'notice'. {guide}"
    return make_spec(
        NAME, 460, 320, walls, [agent("A", 60, 160, 0), agent("B", 400, 160, 180)], objects,
        objectives=[{"type": "delivery_complete", "receptacle_id": "dock"}],
        hints=["Catch the moving coop item 'core' together and deliver it to the receptacle 'dock'."],
        briefings={"A": briefing, "B": briefing}, recommended_steps=200)


def _both_near(env, radius=14.0):
    core = env.objects.get("core")
    return core is not None and all(math.hypot(a.x - core["x"], a.y - core["y"]) <= radius for a in env.agents.values())


def solution(env):
    from .oracle import carry_legs
    legs = carry_legs((330, 60), [(415, 290)])
    picked = lambda e: "core" not in e.objects
    return {
        "A": [("goto", 130, 60), ("goto", 330, 60), ("until", _both_near),
              ("act", {"type": "pick_up", "object_id": "core"}),
              ("barrier", "carry")] + legs + [("act", {"type": "drop", "object_id": "core"})],
        "B": [("goto", 330, 60), ("until", picked), ("barrier", "carry")] + legs,
    }


# 실수: A가 혼자 코어를 붙잡으려 함(pickup_blocked) -> 그다음 함께 매복
def mistake(env):
    plans = solution(env)
    alone = lambda e: "core" in e.objects and math.hypot(e.agents["A"].x - e.objects["core"]["x"],
                                                         e.agents["A"].y - e.objects["core"]["y"]) <= 14
    plans["A"] = [("goto", 130, 160), ("goto", 130, 250), ("until", alone),
                  ("act", {"type": "pick_up", "object_id": "core"})] + plans["A"]
    return plans
