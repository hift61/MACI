"""s17 함께 밀기 (공동 계획, 동시 행동) - 둘이 같은 step에 같은 방향으로 밀어야 움직이는 블록 2개를 목표 칸에.
목표/의도/단서 내용은 scenarios/SCENARIOS.md 참고.
"""
from .common import agent, hwall, make_spec, obj

NAME = "s17_push_blocks"
TITLE = "함께 밀기"
FAMILY = "순서 계획"


def build():
    # 가운데 가로 통로 (y 132~168). 아래 벽 가운데(x 185~215)에 틈 - 블록 2가 남쪽에서 들어오는 길
    walls = hwall(122, 140, 340) + hwall(168, 140, 340, gaps=[(200, 30)]) + [[330, 132, 10, 36]]
    objects = [
        obj("push_block", "block_1", 100, 150, radius=12.0, required=2, push_distance=20.0),
        obj("push_block", "block_2", 200, 250, radius=12.0, required=2, push_distance=20.0),
        obj("block_target", "target_east", 300, 150, label="target"),
        obj("block_target", "target_middle", 200, 150, label="target"),
        obj("reset_lever", "reset", 40, 40, blocks=["block_1", "block_2"]),
        obj("clue", "notice", 40, 290, hidden=False, content={
            "blocks": "Blocks are too heavy for one agent and cannot be pulled back.",
            "reset": "The lever 'reset' puts both blocks back where they started.",
        }),
    ]
    return make_spec(
        NAME, 400, 300, walls, [agent("A", 40, 250, 0), agent("B", 60, 270, 0)], objects,
        objectives=[{"type": "all_targets_filled"}],
        hints=["Place blocks on both block targets (target_east and target_middle) at the same time."],
        recommended_steps=200)


def _push(heading, times):
    return [("act", {"type": "turn", "facing": heading})] + \
           [("act", {"type": "move_forward", "distance": 20})] * times


def _both(plan_a, plan_b=None):
    return {"A": plan_a, "B": plan_b if plan_b is not None else list(plan_a)}


def solution(env):
    # 블록 1을 먼저 동쪽 끝까지(10번), 그다음 블록 2를 북쪽으로 통로 가운데까지(5번).
    # 순서를 바꾸면 블록 2가 통로를 막아 블록 1이 지나갈 수 없음
    plan = [("goto", 80, 150), ("barrier", "east")] + _push(0, 10)
    plan += [("goto", 200, 150), ("goto", 200, 190), ("goto", 230, 215), ("goto", 230, 285), ("goto", 200, 285),
             ("barrier", "north")] + _push(270, 6)
    return _both(plan)


# 실수: 블록 2를 먼저 통로에 넣어 블록 1의 길을 막음 -> 리셋 레버로 되돌리고 올바른 순서로
def mistake(env):
    wrong = [("goto", 200, 285), ("barrier", "wrong")] + _push(270, 6)
    reset_a = [("goto", 230, 285), ("goto", 120, 285), ("goto", 40, 52),
               ("act", {"type": "pull_lever", "lever_id": "reset"})]
    regroup_b = [("goto", 230, 285), ("goto", 120, 285)]
    plans = solution(env)
    return {"A": wrong + reset_a + plans["A"], "B": wrong + regroup_b + plans["B"]}
