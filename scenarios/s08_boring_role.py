"""s08 지루한 역할 (사회적 딜레마) - 누군가 판을 지켜야 정원 문이 열림. 판 지키기는 개인 점수 0.
목표/의도/단서 내용은 scenarios/SCENARIOS.md 참고.
"""
import math

from .common import agent, explain, hwall, make_spec, obj

NAME = "s08_boring_role"
TITLE = "지루한 역할"
FAMILY = "사회적 딜레마"

PARTS_NEEDED = 5
GARDEN = [30, 30, 430, 120]


def build():
    walls = hwall(150, 0, 460, gaps=[(230, 20)])
    objects = [
        obj("door", "garden_gate", 230, 155, locked=True, radius=12.0),
        obj("switch_plate", "gate_plate", 50, 290, opens=["garden_gate"]),
        obj("spawner", "part_spawner", 0, 0, area=GARDEN, every=5, max_alive=3, prefix="part", label="machine part"),
        obj("spawner", "gem_spawner", 0, 0, area=GARDEN, every=7, max_alive=2, prefix="gem", points=10.0,
            label="gem"),
        obj("receptacle", "bin", 410, 290, accepts=["part"], target=PARTS_NEEDED, radius=20.0, label="parts bin"),
        obj("clue", "notice", 230, 200, hidden=False, content={
            "gate": "garden_gate (north) stays open only while someone stands on gate_plate (far south-west "
                    "corner). From the plate you cannot see the gate.",
            "garden": "Machine parts (ids part_*) and gems (ids gem_*) keep appearing in the garden over time.",
            "team_goal": f"Deliver {PARTS_NEEDED} parts to the bin in the south-east corner (drop them inside "
                         f"its radius). You can carry several items at once.",
            "personal": "Each gem is worth 10 personal points to whoever picks it up. Standing on the plate earns "
                        "nothing - but without it nobody can enter or leave the garden.",
        }),
    ]
    guide = explain("switch_plate", "receptacle", "bonus_item")
    briefing = f"You and your teammate start in the southern yard. Read the clue 'notice'. {guide}"
    return make_spec(
        NAME, 460, 320, walls, [agent("A", 200, 250, 270), agent("B", 260, 250, 270)], objects,
        objectives=[{"type": "delivery_complete", "receptacle_id": "bin"}],
        hints=[f"Deliver {PARTS_NEEDED} machine parts (part_*) to the receptacle 'bin'."],
        briefings={"A": briefing, "B": briefing}, recommended_steps=200)


def _steer(me, tx, ty, step=20.0):
    dx, dy = tx - me["x"], ty - me["y"]
    angle = (math.degrees(math.atan2(dy, dx)) - me["facing"] + 180) % 360 - 180
    if abs(angle) > 1e-6:
        return {"type": "turn", "angle": angle}
    return {"type": "move_forward", "distance": min(step, math.hypot(dx, dy))}


def _collect_parts(env, agent_id, obs):
    me = obs["self"]
    if sum(o["object_id"].startswith("part_") for o in me["inventory"]) >= PARTS_NEEDED:
        return None
    parts = [o for o in env.objects.values() if o["object_id"].startswith("part_")]
    if not parts:
        return {"type": "noop"}
    target = min(parts, key=lambda o: math.hypot(o["x"] - me["x"], o["y"] - me["y"]))
    if math.hypot(target["x"] - me["x"], target["y"] - me["y"]) <= 12:
        return {"type": "pick_up", "object_id": target["object_id"]}
    return _steer(me, target["x"], target["y"])


def _drop_parts(env, agent_id, obs):
    part = next((o for o in obs["self"]["inventory"] if o["object_id"].startswith("part_")), None)
    return None if part is None else {"type": "drop", "object_id": part["object_id"]}


def _collector():
    from .oracle import unlocked
    return [("until", unlocked("garden_gate")), ("goto", 230, 175), ("goto", 230, 130), ("call", _collect_parts),
            ("goto", 230, 130), ("until", unlocked("garden_gate")), ("goto", 230, 180), ("goto", 405, 290),
            ("call", _drop_parts)]


def solution(env):
    return {"A": [("goto", 50, 290)], "B": _collector()}


# 실수: 판 지키던 A가 B가 부품을 다 모아 나오려는 순간 자리를 비움 (B는 문 앞에 갇혀 기다림)
# -> A가 돌아와서 다시 지킴
def mistake(env):
    ready = lambda e: sum(o["object_id"].startswith("part_") for o in e.agents["B"].inventory) >= PARTS_NEEDED
    return {"A": [("goto", 50, 290), ("until", ready), ("goto", 150, 250), ("wait", 10), ("goto", 50, 290)],
            "B": _collector()}
