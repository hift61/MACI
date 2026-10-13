"""s01 교착 상태 (순서 계획) - 각자의 압력판이 '상대 방' 문을 열어 주는 대칭 교착. 단계형 3단계.
  1단계 한쪽 교착: B의 문만 잠겨 있음 (A가 판을 지켜 B를 내보내는 연습)
  2단계 대칭 교착: 원래 s01 (해제 레버 위치까지 단서에 있음)
  3단계 어려운 교착: 방 안 벽 때문에 판까지 돌아가야 하고, 해제 레버의 위치는 알려 주지 않음 (반대편 끝에 있음)
목표/의도/단서 내용은 scenarios/SCENARIOS.md 참고.
"""
from .common import STAGE_RULES, STAGED_OBJECTIVES, agent, explain, hwall, make_spec, obj, stage

NAME = "s01_deadlock"
TITLE = "교착 상태"
FAMILY = "순서 계획"

BASE_WALLS = [[200, 0, 40, 180]] + hwall(180, 0, 200, gaps=[(100, 20)]) + hwall(180, 240, 440, gaps=[(340, 20)])
INNER_WALLS = [[0, 95, 150, 10], [290, 95, 150, 10]]  # 3단계: 방 안 칸막이 (판은 칸막이 위쪽)
RELEASE_3 = {"A": (420, 285), "B": (20, 285)}          # 3단계: 해제 레버가 자기 방 반대편 끝에 있음


def _yard(n):
    return obj("goal_zone", f"yard_{n}", 220, 245, width=440, height=110, label="courtyard")


def _stage1():
    objects = [
        obj("door", "door_B1", 340, 185, locked=True, radius=12.0),
        obj("switch_plate", "plate_A1", 30, 30, opens=["door_B1"]),
        _yard(1),
        obj("clue", "clue_A1", 150, 30, hidden=False, content={
            "plate_A1": "Standing on plate_A1 (this room) holds open door_B1 - the door of room B.",
            "your_door": "Your own doorway at the bottom of room A has no door; you can walk out any time."}),
        obj("clue", "clue_B1", 290, 30, hidden=False, content={
            "door_B1": "Your door door_B1 opens only while someone stands on plate_A1 in room A."}),
    ]
    return stage("one-way door", "Only room B is locked this time. Both of you must stand in the courtyard "
                 "(yard_1) below the rooms at the same time.", [{"type": "team_assembled", "zone_id": "yard_1"}],
                 objects)


def _clue2(me, other):
    return {
        f"plate_{me}2": f"Standing on plate_{me}2 (this room) holds open door_{other}2 - the door of room {other}, "
                        f"NOT your own door.",
        f"door_{me}2": f"Your door door_{me}2 opens only while someone stands on plate_{other}2 in room {other}, "
                       f"or forever once lever release_{me}2 in the courtyard is pulled.",
        "courtyard": "release_A2 and release_B2 are levers in the courtyard just below the two rooms.",
    }


def _stage2():
    objects = [
        obj("door", "door_A2", 100, 185, locked=True, radius=12.0),
        obj("door", "door_B2", 340, 185, locked=True, radius=12.0),
        obj("switch_plate", "plate_A2", 30, 30, opens=["door_B2"]),
        obj("switch_plate", "plate_B2", 410, 30, opens=["door_A2"]),
        obj("latch_lever", "release_A2", 200, 285, doors=["door_A2"]),
        obj("latch_lever", "release_B2", 240, 285, doors=["door_B2"]),
        _yard(2),
        obj("clue", "clue_A2", 150, 30, content=_clue2("A", "B"), hidden=False),
        obj("clue", "clue_B2", 290, 30, content=_clue2("B", "A"), hidden=False),
    ]
    return stage("symmetric deadlock", "Both rooms are locked now. Both of you must stand in the courtyard "
                 "(yard_2) at the same time.", [{"type": "team_assembled", "zone_id": "yard_2"}], objects)


def _clue3(me, other):
    return {
        f"plate_{me}3": f"Standing on plate_{me}3 (this room, behind the partition) holds open door_{other}3 - the "
                        f"door of room {other}, NOT your own door.",
        f"door_{me}3": f"Your door door_{me}3 opens only while someone stands on plate_{other}3 in room {other}, "
                       f"or forever once its release lever somewhere outside the rooms is pulled.",
    }


def _stage3():
    objects = [
        obj("door", "door_A3", 100, 185, locked=True, radius=12.0),
        obj("door", "door_B3", 340, 185, locked=True, radius=12.0),
        obj("switch_plate", "plate_A3", 30, 30, opens=["door_B3"]),
        obj("switch_plate", "plate_B3", 410, 30, opens=["door_A3"]),
        obj("latch_lever", "release_A3", *RELEASE_3["A"], doors=["door_A3"]),
        obj("latch_lever", "release_B3", *RELEASE_3["B"], doors=["door_B3"]),
        _yard(3),
        obj("clue", "clue_A3", 50, 150, content=_clue3("A", "B"), hidden=False),
        obj("clue", "clue_B3", 390, 150, content=_clue3("B", "A"), hidden=False),
    ]
    return stage("hard deadlock", "Both rooms are locked again and each room is split by a partition. Both of you "
                 "must stand in the courtyard (yard_3) at the same time.",
                 [{"type": "team_assembled", "zone_id": "yard_3"}], objects, walls=BASE_WALLS + INNER_WALLS)


def build():
    guide = explain("switch_plate", "latch_lever", "goal_zone")
    briefings = {
        "A": f"You start in room A (top-left). Agent B starts in room B (top-right). Read the clue in your room "
             f"each stage. {STAGE_RULES} {guide}",
        "B": f"You start in room B (top-right). Agent A starts in room A (top-left). Read the clue in your room "
             f"each stage. {STAGE_RULES} {guide}",
    }
    return make_spec(
        NAME, 440, 300, BASE_WALLS, [agent("A", 100, 120, 270), agent("B", 340, 120, 270)], [],
        objectives=STAGED_OBJECTIVES,
        hints=["Clear all three stages; each stage ends when both agents stand in its courtyard goal_zone."],
        briefings=briefings, rules={"stages": [_stage1(), _stage2(), _stage3()]}, recommended_steps=300)


def _stage1_plan():
    from .oracle import unlocked
    return {"A": [("stage", 1), ("goto", 30, 30), ("until", lambda e: e.agents["B"].y > 200),
                  ("goto", 100, 170), ("goto", 100, 240)],
            "B": [("stage", 1), ("until", unlocked("door_B1")), ("goto", 340, 170), ("goto", 340, 240)]}


def _stage2_plan():
    from .oracle import unlocked
    return {"A": [("stage", 2), ("goto", 30, 30), ("until", lambda e: e.objects["door_A2"].get("latched")),
                  ("goto", 100, 170), ("goto", 100, 240)],
            "B": [("stage", 2), ("until", unlocked("door_B2")), ("goto", 340, 170), ("goto", 340, 230),
                  ("goto", 200, 271), ("act", {"type": "pull_lever", "lever_id": "release_A2"}), ("goto", 220, 240)]}


def _stage3_plan():
    from .oracle import unlocked
    lever_x, lever_y = RELEASE_3["A"]
    return {"A": [("stage", 3), ("goto", 175, 120), ("goto", 175, 50), ("goto", 30, 30),
                  ("until", lambda e: e.objects["door_A3"].get("latched")),
                  ("goto", 175, 50), ("goto", 175, 140), ("goto", 100, 170), ("goto", 100, 240)],
            "B": [("stage", 3), ("until", unlocked("door_B3")), ("goto", 340, 170), ("goto", 340, 230),
                  ("goto", lever_x, lever_y - 14), ("act", {"type": "pull_lever", "lever_id": "release_A3"})]}


def _join(*parts):
    return {aid: [item for part in parts for item in part[aid]] for aid in ("A", "B")}


def solution(env):
    return _join(_stage1_plan(), _stage2_plan(), _stage3_plan())


# 실수(2단계): 둘 다 자기 판을 밟았다가 동시에 내려와 문 앞에서 막힘 -> 역할을 정해 다시 (B가 지킴)
def mistake(env):
    from .oracle import unlocked
    stage2 = {
        "A": [("stage", 2), ("goto", 30, 30), ("wait", 6), ("goto", 100, 170), ("wait", 4),
              ("until", unlocked("door_A2")), ("goto", 100, 230), ("goto", 240, 271),
              ("act", {"type": "pull_lever", "lever_id": "release_B2"}), ("goto", 220, 240)],
        "B": [("stage", 2), ("goto", 410, 30), ("wait", 6), ("goto", 340, 170), ("wait", 4), ("goto", 410, 30),
              ("until", lambda e: e.objects["door_B2"].get("latched")), ("goto", 340, 170), ("goto", 340, 240)],
    }
    return _join(_stage1_plan(), stage2, _stage3_plan())
