"""s03 나눠 보는 실험 (공동 추론) - 숨은 배선(XOR)으로 문 4개를 여는 레버 6개, 문 상태는 각자 절반만 보임.
목표/의도/단서 내용은 scenarios/SCENARIOS.md 참고.
"""
from .common import agent, explain, hwall, make_spec, obj

NAME = "s03_split_experiment"
TITLE = "나눠 보는 실험"
FAMILY = "공동 추론"

# 숨은 배선: 문 -> 연결된 레버 (연결된 레버 중 ON 개수가 홀수면 열림). 관찰에는 안 보임
WIRING = {
    "G1": ["L1", "L4", "L5"],
    "G2": ["L2", "L6"],
    "G3": ["L3", "L4"],
    "G4": ["L1", "L2", "L5", "L6"],
}
LEVERS = {"L1": (50, 30), "L2": (105, 30), "L3": (160, 30), "L4": (280, 30), "L5": (335, 30), "L6": (390, 30)}
GATES = {"G1": (105, 110), "G2": (105, 140), "G3": (335, 110), "G4": (335, 140)}


def build():
    walls = [[210, 0, 20, 145]]
    walls += hwall(105, 0, 210, gaps=[(105, 20)]) + hwall(135, 0, 210, gaps=[(105, 20)])
    walls += hwall(105, 230, 440, gaps=[(335, 20)]) + hwall(135, 230, 440, gaps=[(335, 20)])
    objects = [obj("switch_lever", lid, x, y, cooldown=3) for lid, (x, y) in LEVERS.items()]
    objects += [obj("logic_door", gid, x, y, levers=WIRING[gid], parity=1) for gid, (x, y) in GATES.items()]
    note = {
        "wiring": "Each of the six levers (L1-L3 in room A, L4-L6 in room B) is secretly wired to some of the "
                  "four gates G1-G4. Pulling a lever flips every gate it is wired to (open <-> closed).",
        "rule": "A gate is open exactly when an ODD number of the levers wired to it are ON. All levers start OFF.",
        "view": "G1 and G2 are in room A, G3 and G4 in room B. You can only watch the gates in your own room.",
        "cooldown": "After a pull, a lever needs 3 steps before it can be pulled again (field ready_at_step).",
    }
    objects += [
        obj("clue", "wiring_note_A", 180, 70, content=note, hidden=False),
        obj("clue", "wiring_note_B", 410, 70, content=note, hidden=False),
        obj("goal_zone", "exit", 220, 202, width=440, height=115, label="exit hall"),
    ]
    guide = explain("switch_lever", "goal_zone")
    briefings = {
        "A": f"You are in room A (left) with levers L1-L3 and gates G1, G2 (G2 lies beyond G1). Agent B is in "
             f"room B (right) with L4-L6 and gates G3, G4. A wall separates the rooms. Read wiring_note_A. {guide}",
        "B": f"You are in room B (right) with levers L4-L6 and gates G3, G4 (G4 lies beyond G3). Agent A is in "
             f"room A (left) with L1-L3 and gates G1, G2. A wall separates the rooms. Read wiring_note_B. {guide}",
    }
    return make_spec(
        NAME, 440, 260, walls, [agent("A", 105, 70, 270), agent("B", 335, 70, 270)], objects,
        objectives=[{"type": "team_assembled", "zone_id": "exit"}],
        hints=["Both agents must stand in the goal_zone 'exit' (below both rooms) at the same time."],
        briefings=briefings, recommended_steps=150)


def solution(env):
    from .oracle import unlocked
    both = lambda a, b: (lambda e: unlocked(a)(e) and unlocked(b)(e))
    return {
        "A": [("goto", 105, 42), ("act", {"type": "pull_lever", "lever_id": "L2"}), ("goto", 105, 92),
              ("until", both("G1", "G2")), ("goto", 105, 170)],
        "B": [("goto", 280, 42), ("act", {"type": "pull_lever", "lever_id": "L4"}), ("goto", 335, 92),
              ("until", both("G3", "G4")), ("goto", 335, 170)],
    }


# 실수: A가 L1을 당겼다가(G1, G4가 뒤집힘) 대기시간 3 step을 기다려 되돌림 -> 정답
def mistake(env):
    plans = solution(env)
    plans["A"] = [("goto", 50, 42), ("act", {"type": "pull_lever", "lever_id": "L1"}), ("wait", 3),
                  ("act", {"type": "pull_lever", "lever_id": "L1"})] + plans["A"]
    return plans
