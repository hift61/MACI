"""s11 포위 (시간 예측) - 기둥을 도는 2인용 코어를 둘이 같은 순간 붙잡아 함께 운반. 단계형 3단계.
  1단계 멈춰 있는 코어 (함께 들고 옮기기 연습), 2단계 느린 코어 (속도 6), 3단계 원래 s11 (속도 12)
목표/의도/단서 내용은 scenarios/SCENARIOS.md 참고.
"""
import math

from .common import STAGED_OBJECTIVES, agent, make_spec, obj, stage

NAME = "s11_pincer"
TITLE = "포위"
FAMILY = "시간 예측"

LOOP = [[330, 60], [330, 260], [130, 260], [130, 60]]  # 코어 순환 경로 (관찰에서 숨김)
SPEEDS = {2: 6.0, 3: 12.0}
STILL_CORE = (330, 60)  # 1단계 코어 위치


def _dock(n):
    return obj("receptacle", f"dock_{n}", 420, 295, accepts=[f"core_{n}"], target=1, radius=20.0, label="core dock")


def _stage1():
    objects = [
        obj("item", "core_1", *STILL_CORE, category="coop", required_agents=2),
        _dock(1),
        obj("clue", "notice_1", 60, 300, hidden=False, content={
            "core": "The power core is too heavy for one agent."}),
    ]
    return stage("resting core", "Deliver core_1 to dock_1.",
                 [{"type": "delivery_complete", "receptacle_id": "dock_1"}], objects)


def _moving_stage(n):
    speed = SPEEDS[n]
    objects = [
        obj("mover", f"core_{n}", 130, 60, waypoints=LOOP, speed=speed, object_type="item", loop=True,
            extra={"category": "coop", "required_agents": 2, "label": "power core", "_hide_path": True}),
        _dock(n),
        obj("clue", f"notice_{n}", 60, 300, hidden=False, content={
            "core": f"The power core moves on its own along a hidden path, about {speed:g} units per step.",
            "deliver": f"Dropped anywhere except dock_{n}, the core starts moving on its own again."}),
    ]
    return stage("slow core" if n == 2 else "fast core",
                 f"Deliver core_{n} to dock_{n}.",
                 [{"type": "delivery_complete", "receptacle_id": f"dock_{n}"}], objects)


def build():
    walls = [[180, 110, 100, 100]]  # 가운데 기둥 (시야를 가림)
    return make_spec(
        NAME, 460, 320, walls, [agent("A", 60, 160, 0), agent("B", 400, 160, 180)], [],
        objectives=STAGED_OBJECTIVES,
        hints=["Clear all three stages; each stage ends when that stage's core is delivered to its dock."],
        rules={"stages": [_stage1(), _moving_stage(2), _moving_stage(3)]}, recommended_steps=400)


def _both_near(core_id, radius=14.0):
    def check(env):
        core = env.objects.get(core_id)
        return core is not None and all(math.hypot(a.x - core["x"], a.y - core["y"]) <= radius
                                        for a in env.agents.values())
    return check


def _stage1_plan():
    from .oracle import carry_legs
    legs = carry_legs((330, 72), [(415, 290)])
    return {
        "A": [("stage", 1), ("goto", 130, 60), ("goto", 330, 72), ("barrier", "pick1"), ("act", {"type": "pick_up", "object_id": "core_1"}),
              ("barrier", "carry1")] + legs + [("act", {"type": "drop", "object_id": "core_1"})],
        "B": [("stage", 1), ("goto", 330, 72), ("barrier", "pick1"), ("barrier", "carry1")] + legs,
    }


def _moving_plan(n, lone_try=False):
    from .oracle import carry_legs
    core = f"core_{n}"
    legs = carry_legs((330, 60), [(415, 290)])
    picked = lambda e: core not in e.objects
    a_plan = [("stage", n)]
    if lone_try:  # 실수: A가 혼자 코어를 붙잡으려 함(pickup_blocked)
        alone = lambda e: core in e.objects and math.hypot(e.agents["A"].x - e.objects[core]["x"],
                                                           e.agents["A"].y - e.objects[core]["y"]) <= 14
        a_plan += [("goto", 130, 160), ("goto", 130, 250), ("until", alone),
                   ("act", {"type": "pick_up", "object_id": core})]
    a_plan += [("goto", 130, 60), ("goto", 330, 60), ("until", _both_near(core)),
               ("act", {"type": "pick_up", "object_id": core}),
               (("barrier", f"carry{n}"))] + legs + [("act", {"type": "drop", "object_id": core})]
    return {"A": a_plan, "B": [("stage", n), ("goto", 330, 60), ("until", picked), ("barrier", f"carry{n}")] + legs}


def _join(*parts):
    return {aid: [item for part in parts for item in part[aid]] for aid in ("A", "B")}


def solution(env):
    return _join(_stage1_plan(), _moving_plan(2), _moving_plan(3))


# 실수(3단계): A가 혼자 코어를 붙잡으려 함(pickup_blocked) -> 그다음 함께 매복
def mistake(env):
    return _join(_stage1_plan(), _moving_plan(2), _moving_plan(3, lone_try=True))
