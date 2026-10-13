"""s23 열쇠 상자 연쇄 (물류 계획) - 열쇠와 상자가 두 구역에 엇갈려 있고, 유리 창구로만 주고받음.
목표/의도/단서 내용은 scenarios/SCENARIOS.md 참고.
"""
from .common import agent, explain, make_spec, obj

NAME = "s23_key_chests"
TITLE = "열쇠 상자 연쇄"
FAMILY = "작업 분배"

WEST, EAST = (224, 150), (236, 150)  # 창구 양쪽 내려놓는 자리
# 상자 -> (x, y, 내용물). 내용물은 열리기 전까지 안 보임
CHESTS = {
    "chest_a1": (100, 240, [{"kind": "key", "id": "key_b2", "unlocks": "chest_b2"}]),
    "chest_a2": (180, 60, [{"kind": "item", "id": "scepter"}]),
    "chest_b1": (300, 240, [{"kind": "key", "id": "key_a2", "unlocks": "chest_a2"}]),
    "chest_b2": (400, 240, [{"kind": "item", "id": "crown"}]),
}


def build():
    walls = [[225, 0, 10, 120], [225, 180, 10, 120]]
    glass = [[225, 120, 10, 60]]  # 가운데 유리 창구 (보이고, 물건을 넘겨받을 수 있음)
    objects = [obj("chest", cid, x, y, contents=contents, label="locked chest") for cid, (x, y, contents) in CHESTS.items()]
    objects += [
        obj("key", "key_b1", 60, 60, unlocks="chest_b1"),
        obj("key", "key_a1", 400, 60, unlocks="chest_a1"),
        obj("receptacle", "altar", 60, 150, accepts=["crown", "scepter"], target=2, radius=20.0, label="altar"),
    ]
    note = {
        "goal": "Place BOTH the crown and the scepter on the altar (WEST area).",
        "chests": "Each chest opens with the key whose 'unlocks' field names it. What is inside only appears "
                  "once the chest is opened. Keys are used up when they open a chest.",
        "counter": "A solid wall separates the WEST and EAST areas, except for a glass window in the middle. You "
                   "cannot cross it, but an item dropped right against the window can be picked up from the "
                   "other side.",
    }
    objects += [obj("clue", "note_west", 30, 290, content=note, hidden=False),
                obj("clue", "note_east", 430, 290, content=note, hidden=False)]
    guide = explain("chest", "receptacle")
    briefings = {
        "A": f"You are in the WEST area. Agent B is in the EAST area. Read note_west. {guide}",
        "B": f"You are in the EAST area. Agent A is in the WEST area. Read note_east. {guide}",
    }
    return make_spec(
        NAME, 460, 300, walls, [agent("A", 120, 150, 0), agent("B", 340, 150, 180)], objects,
        objectives=[{"type": "delivery_complete", "receptacle_id": "altar"}],
        hints=["Deliver the crown and the scepter to the receptacle 'altar'."],
        briefings=briefings, rules={"glass_walls": glass}, recommended_steps=200)


def _pick(object_id):
    return ("act", {"type": "pick_up", "object_id": object_id})


def _drop(object_id):
    return ("act", {"type": "drop", "object_id": object_id})


def _open(chest_id, key_id):
    x, y, _ = CHESTS[chest_id]
    return [("goto", x, y - 12 if y > 150 else y + 12), ("act", {"type": "use_key", "key_id": key_id})]


def _at_window(object_id, side):
    x0, x1 = (215, 226) if side == "west" else (234, 245)
    return lambda e: object_id in e.objects and x0 <= e.objects[object_id]["x"] <= x1


def solution(env):
    return {
        "A": [("goto", 60, 72), _pick("key_b1"), ("goto", *WEST), _drop("key_b1"),
              ("until", _at_window("key_a1", "east")), _pick("key_a1"), *_open("chest_a1", "key_a1"),
              _pick("key_b2"), ("goto", *WEST), _drop("key_b2"),
              ("until", _at_window("key_a2", "east")), _pick("key_a2"), *_open("chest_a2", "key_a2"),
              _pick("scepter"), ("goto", *WEST), ("until", _at_window("crown", "east")), _pick("crown"),
              ("goto", 60, 160), _drop("crown"), _drop("scepter")],
        "B": [("goto", 400, 72), _pick("key_a1"), ("goto", *EAST), _drop("key_a1"),
              ("until", _at_window("key_b1", "west")), _pick("key_b1"), *_open("chest_b1", "key_b1"),
              _pick("key_a2"), ("goto", *EAST), _drop("key_a2"),
              ("until", _at_window("key_b2", "west")), _pick("key_b2"), *_open("chest_b2", "key_b2"),
              _pick("crown"), ("goto", *EAST), _drop("crown")],
    }


# 실수: B가 key_a1(A용 열쇠)로 자기 상자를 열려다 실패하고 시간을 버림 -> 정답
def mistake(env):
    plans = solution(env)
    plans["B"] = [("goto", 400, 72), _pick("key_a1"), *_open("chest_b1", "key_a1"), ("wait", 3)] + plans["B"][2:]
    return plans
