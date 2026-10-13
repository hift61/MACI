"""s22 좁은 다리 (병목 자원 협상) - 한 명만 버티는 다리로, 양쪽에서 생기는 상자를 서로 반대편에 배달.
목표/의도/단서 내용은 scenarios/SCENARIOS.md 참고.
"""
from .common import agent, explain, make_spec, obj

NAME = "s22_narrow_bridge"
TITLE = "좁은 다리"
FAMILY = "순서 계획"

PER_SIDE = 3


def build():
    walls = [[200, 0, 60, 135], [200, 165, 60, 135]]  # 강 (가운데 다리 y 135~165만 건널 수 있음)
    objects = [
        obj("capacity_zone", "bridge", 230, 150, width=60, height=30, capacity=1, label="rope bridge"),
        obj("spawner", "west_shed", 0, 0, area=[30, 30, 170, 270], every=10, max_alive=1, prefix="blue",
            label="blue box"),
        obj("spawner", "east_shed", 0, 0, area=[290, 30, 430, 270], every=10, max_alive=1, prefix="red",
            label="red box"),
        obj("receptacle", "east_dock", 420, 150, accepts=["blue"], target=PER_SIDE, radius=20.0,
            label="east dock (blue boxes)"),
        obj("receptacle", "west_dock", 40, 150, accepts=["red"], target=PER_SIDE, radius=20.0,
            label="west dock (red boxes)"),
        obj("clue", "notice_west", 100, 290, hidden=False, content={
            "goal": f"Blue boxes appear on the WEST bank and must go to east_dock; red boxes appear on the EAST "
                    f"bank and must go to west_dock. {PER_SIDE} of each.",
            "bridge": "The rope bridge holds only ONE person. If two people are on it at the end of a step, it "
                      "swings and both are thrown back to where they stepped on.",
            "boxes": "Only one box of each colour lies around at a time; a new one appears a while after it is "
                     "taken.",
        }),
    ]
    objects.append(obj("clue", "notice_east", 360, 290, hidden=False, content=objects[-1]["params"]["content"]))
    guide = explain("capacity_zone", "receptacle")
    briefings = {
        "A": f"You start on the WEST bank. Agent B starts on the EAST bank. A river separates you; the only way "
             f"across is the rope bridge in the middle. Read notice_west. {guide}",
        "B": f"You start on the EAST bank. Agent A starts on the WEST bank. A river separates you; the only way "
             f"across is the rope bridge in the middle. Read notice_east. {guide}",
    }
    return make_spec(
        NAME, 460, 300, walls, [agent("A", 100, 150, 0), agent("B", 360, 150, 180)], objects,
        objectives=[{"type": "delivery_complete", "receptacle_id": "east_dock"},
                    {"type": "delivery_complete", "receptacle_id": "west_dock"}],
        hints=[f"Deliver {PER_SIDE} blue boxes to east_dock and {PER_SIDE} red boxes to west_dock."],
        briefings=briefings, recommended_steps=300)


def _ferry(oracle, prefix, home_x, far_x, dock_x):
    step_in = 190 if home_x < 230 else 270
    step_out = 270 if home_x < 230 else 190
    return [("call", oracle.fetch(prefix)), ("goto", step_in, 150), ("lock", "bridge"), ("goto", step_out, 150),
            ("unlock", "bridge"), ("goto", dock_x, 150), ("call", oracle.drop_prefix(prefix)),
            ("goto", step_out, 150), ("lock", "bridge"), ("goto", step_in, 150), ("unlock", "bridge")]


def solution(env):
    from . import oracle
    return {"A": [s for _ in range(PER_SIDE) for s in _ferry(oracle, "blue", 100, 360, 405)],
            "B": [s for _ in range(PER_SIDE) for s in _ferry(oracle, "red", 360, 100, 55)]}


# 실수: 둘 다 상자를 들고 동시에 다리에 올라 둘 다 튕겨 나감 (두 번) -> 한 명씩
def mistake(env):
    from . import oracle
    plans = solution(env)

    def rush(prefix, x, facing):
        step = [("barrier", f"rush_{n}") for n in (1, 2)]
        return [("call", oracle.fetch(prefix)), ("goto", x, 150), ("act", {"type": "turn", "facing": facing}),
                step[0], ("act", {"type": "move_forward", "distance": 20}), ("goto", x, 150),
                ("act", {"type": "turn", "facing": facing}), step[1], ("act", {"type": "move_forward", "distance": 20})]
    plans["A"] = rush("blue", 190, 0) + plans["A"]
    plans["B"] = rush("red", 270, 180) + plans["B"]
    return plans
