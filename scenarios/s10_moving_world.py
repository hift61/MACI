"""s10 움직이는 세계 (시간 예측) - 주기가 다른 두 문이 함께 열리는 미래 시점을 추론해 동시에 통과.
어려운 버전: 주기 9와 7, 문은 1 step만 열림, 두 판을 정확히 같은 step에 밟아야 함 (공통 시점 18, 81, 144, ...).
목표/의도/단서 내용은 scenarios/SCENARIOS.md 참고.
"""
from .common import agent, explain, hwall, make_spec, obj

NAME = "s10_moving_world"
TITLE = "움직이는 세계"
FAMILY = "시간 예측"

# 문이 열리는 step: (step + phase) % period < open_steps
SCHEDULE = {"gate_A": {"period": 9, "open_steps": 1, "phase": 0},
            "gate_B": {"period": 7, "open_steps": 1, "phase": 3}}
ROOM_X = {"A": 105, "B": 335}
GATE_RADIUS = 6.0  # 문이 1 step만 열리므로 한 번의 전진(20)으로 문 반경을 완전히 지나갈 수 있게 작게 (틈 폭 12)


def is_open(gate, step):
    s = SCHEDULE[gate]
    return (step + s["phase"]) % s["period"] < s["open_steps"]


def build():
    walls = [[210, 0, 20, 260]] + hwall(100, 0, 210, gaps=[(105, 12)]) + hwall(100, 230, 440, gaps=[(335, 12)])
    manual = {
        "gate": "The gate in front of you opens and closes by itself on a fixed repeating schedule. The other "
                "room's gate follows a DIFFERENT schedule that only your teammate can watch.",
        "pads": "Behind each gate is a sync_pad (pad_A, pad_B). Both pads must be entered in exactly the same "
                "step. A lone entry pushes that agent back out in front of the gate and disables both pads "
                "for 3 steps.",
        "tip": "A gate stays open for a single step only, so be right in front of your gate when it opens. Every "
               "observation contains the shared step number (self.step).",
    }
    objects = []
    for room, x in ROOM_X.items():
        objects += [
            obj("periodic_door", f"gate_{room}", x, 105, radius=GATE_RADIUS, **SCHEDULE[f"gate_{room}"]),
            obj("sync_pad", f"pad_{room}", x, 70, group="crossing", tolerance=0, return_x=x, return_y=135, cooldown=3),
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
        hints=["Enter pad_A and pad_B (behind the two timed gates) in exactly the same step."],
        briefings=briefings, recommended_steps=200)


# 문 바로 앞(문 중심에서 7)에서 열리는 step T에 20 전진(문 통과), T+1에 20 전진 -> T+1에 판 진입
def _cross(x, step):
    move = {"type": "move_forward", "distance": 20}
    return [("goto", x, 112), ("face", 270), ("at_step", step), ("act", move), ("act", move)]


def solution(env):
    # 두 문이 같은 step에 열리는 T: 18, 81, 144, ... (주기 63). 관찰할 시간을 두고 81을 고름
    return {"A": _cross(ROOM_X["A"], 81), "B": _cross(ROOM_X["B"], 81)}


# 실수: A가 자기 문만 보고 step 9에 혼자 통과 -> 밀려남 -> 81에 함께
def mistake(env):
    return {"A": _cross(ROOM_X["A"], 9) + _cross(ROOM_X["A"], 81), "B": _cross(ROOM_X["B"], 81)}
