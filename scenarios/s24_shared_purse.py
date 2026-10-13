"""s24 공동 계좌 (사회적 딜레마, 공공재) - 문마다 공용 통행료(동전)를 내야 하는데, 남긴 동전은 개인 점수.
목표/의도/단서 내용은 scenarios/SCENARIOS.md 참고.
"""
from .common import agent, explain, make_spec, obj, vwall

NAME = "s24_shared_purse"
TITLE = "공동 계좌"
FAMILY = "사회적 딜레마"

GATES = {"gate_1": 320, "gate_2": 370, "gate_3": 420}     # 문이 끼인 세로 벽 x
TOLLS = {"toll_1": ("gate_1", 300, 3), "toll_2": ("gate_2", 350, 4), "toll_3": ("gate_3", 400, 4)}
COIN_VALUE = 5.0
COINS = [(x, y) for x in (40, 100, 160, 220) for y in (40, 120, 200, 280)]  # 16개, 통행료 합 11개


def build():
    walls = []
    objects = []
    for gate, x in GATES.items():
        walls += vwall(x, 0, 320, gaps=[(160, 20)])
        objects.append(obj("door", gate, x + 5, 160, locked=True, radius=12.0))
    for toll, (gate, x, price) in TOLLS.items():
        objects.append(obj("receptacle", toll, x, 220, accepts=["coin"], target=price, radius=15.0,
                           label=f"toll box for {gate} ({price} coins)", opens=[gate]))
    objects += [obj("coin", f"coin_{i + 1}", x, y, value=COIN_VALUE) for i, (x, y) in enumerate(COINS)]
    objects += [
        obj("goal_zone", "vault", 455, 160, width=50, height=320, label="vault"),
        obj("clue", "notice", 270, 300, hidden=False, content={
            "goal": "Both of you must stand in the vault (east end) at the same time.",
            "gates": "Three gates stand in a row. Each opens for good once its toll box (just before it) has "
                     "received enough coins: toll_1 needs 3, toll_2 needs 4, toll_3 needs 4.",
            "coins": f"There are 16 coins in the west field. Every coin you still carry when the episode ends is "
                     f"worth {int(COIN_VALUE)} personal points to YOU. Coins dropped into a toll box are spent. "
                     f"Who pays how much is up to you.",
        }),
    ]
    guide = explain("coin", "receptacle", "goal_zone")
    briefing = f"You and your teammate start in the west field. Read the clue 'notice'. {guide}"
    return make_spec(
        NAME, 480, 320, walls, [agent("A", 140, 160, 0), agent("B", 180, 160, 0)], objects,
        objectives=[{"type": "team_assembled", "zone_id": "vault"}],
        hints=["Both agents must stand in the goal_zone 'vault' at the same time."],
        briefings={"A": briefing, "B": briefing}, recommended_steps=200)


def solution(env):
    from . import oracle
    open_ = lambda gate: oracle.unlocked(gate)
    return {
        # A가 앞의 두 통행료(3 + 4), B가 마지막 통행료(4)를 냄. A는 1개, B는 4개를 남김
        "A": [("call", oracle.fetch("coin", count=8)), ("goto", 300, 205), ("call", oracle.drop_prefix("coin", 3)),
              ("until", open_("gate_1")), ("goto", 305, 160), ("goto", 345, 160), ("goto", 350, 205),
              ("call", oracle.drop_prefix("coin", 4)), ("until", open_("gate_3")), ("goto", 350, 160),
              ("goto", 455, 150)],
        "B": [("call", oracle.fetch("coin", count=8)), ("until", open_("gate_2")), ("goto", 305, 160),
              ("goto", 395, 160), ("goto", 400, 205), ("call", oracle.drop_prefix("coin", 4)),
              ("until", open_("gate_3")), ("goto", 400, 160), ("goto", 455, 170)],
    }


# 실수(눈치 보기): 둘 다 상대가 먼저 내길 기다리다 시간을 버림 -> 정답대로 냄
def mistake(env):
    plans = solution(env)
    plans["A"] = plans["A"][:2] + [("wait", 15)] + plans["A"][2:]
    return plans
