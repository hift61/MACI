"""s15 유리벽 분업 (정보 분할 + 보상 없는 역할) - MAP_GUIDE.md 기준으로 만든 단계형 맵. 축 C + D.
가운데 유리벽(이동은 막고 시야는 통과)이 맵을 둘로 나눔. A는 왼쪽, B는 오른쪽에만 갈 수 있음.
점수 변화(관찰의 reward)만 피드백으로 주고, 무엇이 점수를 주는지·좌표판이 누구 것인지는 알려 주지 않음.
  1단계: 보이는 체크포인트 4곳 (각자 자기 쪽 2곳) - 방문하면 점수가 오른다는 것을 배움
  2단계: 숨은 체크포인트 6곳 (가까이 가야 보임). 내 쪽 좌표판에는 '상대 쪽' 좌표만 적혀 있음 -> 먼저 알려 줘야 함
  3단계: 2단계 + B 쪽 한 곳은 문 안에 있고, 그 문은 A 쪽 판을 누군가 밟고 있는 동안만 열림 (밟는 쪽은 점수 없음)
"""
from .common import STAGED_OBJECTIVES, agent, hwall, make_spec, obj, stage, vwall

NAME = "s15_glass_division"
TITLE = "유리벽 분업"
FAMILY = "작업 분배"

GLASS = [[245, 0, 10, 400]]
POINTS = {  # 단계 -> (A 쪽 체크포인트, B 쪽 체크포인트)
    1: ([(80, 80), (180, 300)], [(320, 100), (430, 320)]),
    2: ([(60, 60), (200, 200), (120, 360)], [(300, 60), (450, 200), (350, 360)]),
    3: ([(80, 120), (200, 330), (150, 40)], [(300, 250), (460, 60), (450, 370)]),
}
PLATE_3 = (40, 40)       # 3단계: A 쪽 판 (밟는 동안 pocket 문이 열림)
DOOR_3 = (450, 325)      # 3단계: B 쪽 pocket 입구 문
POCKET_WALLS = hwall(320, 390, 500, gaps=[(450, 24)]) + vwall(390, 320, 400)


def _checkpoints(n, hidden):
    a, b = POINTS[n]
    return [obj("checkpoint", f"c{n}_{i}", x, y, radius=12.0, hidden=hidden)
            for i, (x, y) in enumerate(a + b, start=1)]


def _visit_all(n):
    count = len(POINTS[n][0]) + len(POINTS[n][1])
    return [{"type": "checkpoint_visited", "object_id": f"c{n}_{i}"} for i in range(1, count + 1)]


def _boards(n):
    a, b = POINTS[n]
    # A 쪽 판에는 B 쪽 좌표, B 쪽 판에는 A 쪽 좌표 (누구 것인지는 적지 않음)
    return [obj("clue", f"board_{n}a", 120, 250, hidden=False, content={"points": [list(p) for p in b]}),
            obj("clue", f"board_{n}b", 380, 150, hidden=False, content={"points": [list(p) for p in a]})]


def _stage(n):
    objects = _checkpoints(n, hidden=n > 1)
    walls = []
    if n > 1:
        objects += _boards(n)
    if n == 3:
        objects += [obj("door", "pocket_door", *DOOR_3, locked=True, radius=12.0),
                    obj("switch_plate", "p3", *PLATE_3, opens=["pocket_door"])]
        walls = POCKET_WALLS
    return stage(f"stage {n}", f"Visit every checkpoint c{n}_*.", _visit_all(n), objects, walls=walls)


def build():
    briefings = {"A": "You start in the bottom-left. Agent B starts in the top-right.",
                 "B": "You start in the top-right. Agent A starts in the bottom-left."}
    return make_spec(
        NAME, 500, 400, [], [agent("A", 60, 330, 270), agent("B", 440, 70, 90)], [],
        objectives=STAGED_OBJECTIVES, hints=["Visit every checkpoint of every stage."], briefings=briefings,
        rules={"glass_walls": GLASS, "show_reward": True, "stages": [_stage(n) for n in (1, 2, 3)]},
        recommended_steps=440)


def _route(points):
    return [("goto", x, y) for x, y in points]


def solution(env):
    from .oracle import unlocked
    plans = {"A": [], "B": []}
    for n in (1, 2):
        a, b = POINTS[n]
        plans["A"] += [("stage", n)] + _route(a)
        plans["B"] += [("stage", n)] + _route(b)
    a, b = POINTS[3]
    pocket = b[2]
    in_pocket = lambda e: e.agents["B"].y > 330
    left_pocket = lambda e: e.objects["c3_6"]["visited"] and e.agents["B"].y < 315
    plans["A"] += [("stage", 3), ("goto", *PLATE_3), ("until", in_pocket), ("until", left_pocket)] + _route(a)
    plans["B"] += [("stage", 3)] + _route(b[:2]) + [("goto", DOOR_3[0], 300), ("until", unlocked("pocket_door")),
                                                    ("goto", *pocket), ("goto", DOOR_3[0], 300)]
    return plans


# 실수(3단계): A가 B가 pocket에서 나오기 전에 판을 떠남 -> 문이 닫혀 B가 갇힘 -> A가 돌아와 다시 열어 줌
def mistake(env):
    from .oracle import unlocked
    plans = solution(env)
    a, b = POINTS[3]
    in_pocket = lambda e: e.agents["B"].y > 330
    left_pocket = lambda e: e.objects["c3_6"]["visited"] and e.agents["B"].y < 315
    stage3 = plans["A"].index(("stage", 3))
    plans["A"] = plans["A"][:stage3] + [("stage", 3), ("goto", *PLATE_3), ("until", in_pocket), ("goto", 80, 120),
                                        ("goto", *PLATE_3), ("until", left_pocket)] + _route(a)
    return plans
