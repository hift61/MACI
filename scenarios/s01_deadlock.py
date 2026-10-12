"""s01 교착 상태 (순서 계획) - 각자의 압력판이 '상대 방' 문을 열어 주는 대칭 교착.
목표/의도/단서 내용은 scenarios/SCENARIOS.md 참고.
"""
from .common import agent, explain, hwall, make_spec, obj

NAME = "s01_deadlock"
TITLE = "교착 상태"
FAMILY = "순서 계획"


def build():
    walls = [[200, 0, 40, 180]] + hwall(180, 0, 200, gaps=[(100, 20)]) + hwall(180, 240, 440, gaps=[(340, 20)])
    clue = lambda me, other: {
        f"plate_{me}": f"Standing on plate_{me} (this room) holds open door_{other} - the door of room {other}, "
                       f"NOT your own door.",
        f"door_{me}": f"Your door door_{me} opens only while someone stands on plate_{other} in room {other}, "
                      f"or forever once lever release_{me} in the courtyard is pulled.",
        "courtyard": "release_A and release_B are levers in the courtyard just below the two rooms.",
    }
    objects = [
        obj("door", "door_A", 100, 185, locked=True, radius=12.0),
        obj("door", "door_B", 340, 185, locked=True, radius=12.0),
        obj("switch_plate", "plate_A", 30, 30, opens=["door_B"]),
        obj("switch_plate", "plate_B", 410, 30, opens=["door_A"]),
        obj("latch_lever", "release_A", 200, 285, doors=["door_A"]),
        obj("latch_lever", "release_B", 240, 285, doors=["door_B"]),
        obj("goal_zone", "courtyard", 220, 245, width=440, height=110, label="courtyard"),
        obj("clue", "clue_A", 150, 30, content=clue("A", "B"), hidden=False),
        obj("clue", "clue_B", 290, 30, content=clue("B", "A"), hidden=False),
    ]
    guide = explain("switch_plate", "latch_lever", "goal_zone")
    briefings = {
        "A": f"You start locked in room A (top-left). Agent B is locked in room B (top-right). "
             f"Read clue_A in your room. {guide}",
        "B": f"You start locked in room B (top-right). Agent A is locked in room A (top-left). "
             f"Read clue_B in your room. {guide}",
    }
    return make_spec(
        NAME, 440, 300, walls, [agent("A", 100, 120, 270), agent("B", 340, 120, 270)], objects,
        objectives=[{"type": "team_assembled", "zone_id": "courtyard"}],
        hints=["Both agents must stand inside the goal_zone 'courtyard' at the same time."],
        briefings=briefings, recommended_steps=120)


def solution(env):
    from .oracle import unlocked
    return {
        "A": [("goto", 30, 30), ("until", lambda e: e.objects["door_A"].get("latched")),
              ("goto", 100, 170), ("goto", 100, 240)],
        "B": [("until", unlocked("door_B")), ("goto", 340, 170), ("goto", 340, 230),
              ("goto", 200, 271), ("act", {"type": "pull_lever", "lever_id": "release_A"}), ("goto", 220, 240)],
    }


# 실수: 둘 다 자기 판을 밟았다가 동시에 내려와 문 앞에서 막힘 -> 역할을 정해 다시 (B가 지킴)
def mistake(env):
    from .oracle import unlocked
    return {
        "A": [("goto", 30, 30), ("at_step", 15), ("goto", 100, 170), ("at_step", 35),
              ("until", unlocked("door_A")), ("goto", 100, 230), ("goto", 240, 271),
              ("act", {"type": "pull_lever", "lever_id": "release_B"}), ("goto", 220, 240)],
        "B": [("goto", 410, 30), ("at_step", 15), ("goto", 340, 170), ("at_step", 35), ("goto", 410, 30),
              ("until", lambda e: e.objects["door_B"].get("latched")), ("goto", 340, 170), ("goto", 340, 240)],
    }
