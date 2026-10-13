"""s16 원격 조종 미로 (실시간 원격 협조) - 유리벽 밖 B가 레버로 미로 문을 바꿔 A를 통과시킴.
목표/의도/단서 내용은 scenarios/SCENARIOS.md 참고.
"""
from .common import agent, explain, make_spec, obj, vwall

NAME = "s16_remote_maze"
TITLE = "원격 조종 미로"
FAMILY = "실시간 원격 협조"

CELL_WALLS = [56, 112, 168, 224]  # 미로 칸을 나누는 유리벽 x (두께 8, 가운데에 문)
# 숨은 배선: 문 -> (연결된 레버, parity). 연결 레버 중 ON 개수 % 2 == parity면 열림.
# 네 문이 동시에 열리는 레버 조합은 없음 -> A가 지나가는 동안 B가 설정을 바꿔야 함
WIRING = {
    "D1": (["L1", "L4"], 1),
    "D2": (["L1", "L2"], 1),
    "D3": (["L2", "L3", "L4"], 1),
    "D4": (["L3"], 0),
}
LEVER_Y = {"L1": 60, "L2": 120, "L3": 180, "L4": 240}


def build():
    glass = [[280, 0, 8, 300]]
    for x in CELL_WALLS:
        glass += vwall(x, 0, 300, gaps=[(150, 20)], t=8)
    objects = [obj("logic_door", door, x + 4, 150, levers=levers, parity=parity)
               for (door, (levers, parity)), x in zip(WIRING.items(), CELL_WALLS)]
    objects += [obj("switch_lever", lid, 330, y, cooldown=0) for lid, y in LEVER_Y.items()]
    objects += [
        obj("goal_zone", "goal", 256, 150, width=48, height=300, label="maze exit", agents=["A"]),
        obj("clue", "maze_note", 28, 250, hidden=False, content={
            "you": "You are inside a glass maze of five cells in a row (west to east). The exit cell is the "
                   "easternmost one. Doors D1-D4 separate the cells.",
            "levers": "You cannot reach the levers. Agent B, in the control room east of the glass, can switch "
                      "the doors. Glass blocks movement but not sight.",
        }),
        obj("clue", "control_note", 400, 280, hidden=False, content={
            "levers": "Levers L1-L4 are secretly wired to the maze doors D1-D4. Pulling a lever flips every door "
                      "it is wired to (open <-> closed). The wiring is not written anywhere - watch the doors.",
            "warning": "It may be impossible to have all four doors open at the same time.",
            "goal": "Agent A must reach the easternmost maze cell. You can see the whole maze through the glass, "
                    "but you cannot see agent A.",
        }),
    ]
    briefings = {
        "A": "You start in the westernmost cell of a glass maze (west part of the map). Agent B is in a control "
             "room east of the glass and is the only one who can switch the doors. Read maze_note. "
             + explain("goal_zone"),
        "B": "You are in the control room (east part of the map) with levers L1-L4. Agent A is inside the glass "
             "maze to the west. You can see through the glass far enough to watch every door. Read control_note. "
             + explain("switch_lever", "goal_zone"),
    }
    b_agent = {**agent("B", 380, 150, 180), "view_radius": 320}
    return make_spec(
        NAME, 420, 300, [], [agent("A", 28, 150, 0), b_agent], objects,
        objectives=[{"type": "team_assembled", "zone_id": "goal"}],
        hints=["Agent A must reach the goal_zone 'goal' (the easternmost maze cell)."],
        briefings=briefings, rules={"glass_walls": glass}, recommended_steps=150)


def _pull(lever):
    return [("goto", 330, LEVER_Y[lever] + 12), ("act", {"type": "pull_lever", "lever_id": lever})]


def solution(env):
    from .oracle import unlocked
    both = lambda a, b: (lambda e: unlocked(a)(e) and unlocked(b)(e))
    return {
        # L1 ON: D1, D2, D4 열림 -> A가 셋째 칸까지. L2 ON: D3 열림(D2는 닫힘) -> A가 출구까지
        "A": [("until", both("D1", "D2")), ("goto", 140, 150), ("until", both("D3", "D4")), ("goto", 256, 150)],
        "B": _pull("L1") + [("until", lambda e: e.agents["A"].x > 125)] + _pull("L2"),
    }


# 실수: B가 L3을 당겨 엉뚱한 문을 바꿨다가 되돌림 -> 정답
def mistake(env):
    plans = solution(env)
    plans["B"] = _pull("L3") + _pull("L3") + plans["B"]
    return plans
