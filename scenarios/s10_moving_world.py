"""s10 움직이는 세계 (시간 예측) - 주기가 다른 두 문이 함께 열리는 미래 시점을 추론해 동시에 통과.
목표/의도/단서 내용은 scenarios/SCENARIOS.md 참고.
"""
from .common import agent, explain, hwall, make_spec, obj

NAME = "s10_moving_world"
TITLE = "움직이는 세계"
FAMILY = "시간 예측"

# 문이 열리는 step: (step + phase) % period < open_steps
SCHEDULE = {"gate_A": {"period": 7, "open_steps": 2, "phase": 0},
            "gate_B": {"period": 5, "open_steps": 2, "phase": 3}}
ROOM_X = {"A": 105, "B": 335}


def is_open(gate, step):
    s = SCHEDULE[gate]
    return (step + s["phase"]) % s["period"] < s["open_steps"]


def build():
    walls = [[210, 0, 20, 260]] + hwall(100, 0, 210, gaps=[(105, 20)]) + hwall(100, 230, 440, gaps=[(335, 20)])
    manual = {
        "gate": "The gate in front of you opens and closes by itself on a fixed repeating schedule. The other "
                "room's gate follows a DIFFERENT schedule that only your teammate can watch.",
        "pads": "Behind each gate is a sync_pad (pad_A, pad_B). Both pads must be entered within 1 step of each "
                "other. A lone entry pushes that agent back out in front of the gate and disables both pads "
                "for 3 steps.",
        "tip": "Gates only stay open for a short time, so be right in front of your gate when it opens. Every "
               "observation contains the shared step number (self.step).",
    }
    objects = []
    for room, x in ROOM_X.items():
        objects += [
            obj("periodic_door", f"gate_{room}", x, 105, radius=12.0, **SCHEDULE[f"gate_{room}"]),
            obj("sync_pad", f"pad_{room}", x, 70, group="crossing", tolerance=1, return_x=x, return_y=135, cooldown=3),
            obj("clue", f"manual_{room}", x - 65 if room == "A" else x + 65, 220, content=manual, hidden=False),
        ]
    guide = explain("sync_pad")
    briefings = {
        room: f"You are in room {room} ({'left' if room == 'A' else 'right'}), south of gate_{room}. Agent "
              f"{'B' if room == 'A' else 'A'} is in the other room behind a wall. Read manual_{room}. {guide}"
        for room in ROOM_X
    }
    return make_spec(
        NAME, 440, 260, walls, [agent("A", 105, 200, 270), agent("B", 335, 200, 270)], objects,
        objectives=[{"type": "sync_success", "group": "crossing"}],
        hints=["Enter pad_A and pad_B (behind the two timed gates) within 1 step of each other."],
        briefings=briefings, recommended_steps=150)


# step T, T+1에 앞으로 20씩 두 번 -> T+1에 판 진입 (T, T+1 모두 자기 문이 열려 있어야 함)
def _cross(x, step):
    move = {"type": "move_forward", "distance": 20}
    return [("goto", x, 120), ("face", 270), ("at_step", step), ("act", move), ("act", move)]


def solution(env):
    # 두 문이 T와 T+1에 모두 열려 있는 T: 7, 42, 77, ... (주기 35). 관찰할 시간을 두고 42를 고름
    return {"A": _cross(ROOM_X["A"], 42), "B": _cross(ROOM_X["B"], 42)}


# 실수: A가 자기 문만 보고 step 14에 혼자 통과 -> 밀려남 -> 42에 함께
def mistake(env):
    return {"A": _cross(ROOM_X["A"], 14) + _cross(ROOM_X["A"], 42), "B": _cross(ROOM_X["B"], 42)}
