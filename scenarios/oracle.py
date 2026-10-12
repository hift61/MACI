"""정답 검증용 스크립트 정책. 시나리오가 실제로 풀리는지(그리고 실수한 뒤에도 풀리는지) 확인하는 용도.

각 시나리오 파일의 solution(env)/mistake(env)가 agent_id -> plan(아래 항목의 목록)을 돌려주면
run()이 그 plan대로 env.step()을 돌려 클리어 step을 반환함. LLM과 무관하며 테스트/검수 전용.

plan 항목
  ("goto", x, y[, step])  (x, y)를 향해 돌고 나서 step(기본 20)씩 전진. 도착하면 다음 항목
  ("face", deg)           그 절대 방향으로 회전
  ("act", action)         action dict를 한 번 실행
  ("wait", n)             n step 동안 noop
  ("at_step", n)          관찰의 step이 n이 될 때까지 noop
  ("until", fn)           fn(env)가 True가 될 때까지 noop
  ("barrier", name)       모든 에이전트가 같은 barrier에 도착한 다음 step에 함께 출발 (2인 운반용)
  ("call", fn)            fn(env, agent_id, observation)이 action을 주면 실행, None이면 다음 항목
"""
import math
import threading

from mapgen.builder import build_environment
from scoring import clear_step


class Oracle:
    def __init__(self, agent_ids):
        self.agent_ids = list(agent_ids)
        self.barriers: dict[str, dict[str, int]] = {}
        self.lock = threading.Lock()


class ScriptPolicy:
    def __init__(self, oracle: Oracle, env, agent_id: str, plan: list):
        self.oracle, self.env, self.agent_id, self.plan = oracle, env, agent_id, list(plan)
        self._waited = 0

    def decide(self, observation: dict) -> dict:
        while self.plan:
            action = self._run(self.plan[0], observation)
            if action is not None:
                return action
            self.plan.pop(0)
            self._waited = 0
        return {"type": "noop"}

    # 항목을 계속 진행해야 하면 action, 끝났으면 None
    def _run(self, item, obs):
        me = obs["self"]
        kind = item[0]
        if kind == "goto":
            tx, ty = item[1], item[2]
            step = item[3] if len(item) > 3 else 20.0
            dx, dy = tx - me["x"], ty - me["y"]
            distance = math.hypot(dx, dy)
            if distance <= 0.01:
                return None
            angle = (math.degrees(math.atan2(dy, dx)) - me["facing"] + 180) % 360 - 180
            if abs(angle) > 1e-6:
                return {"type": "turn", "angle": angle}
            return {"type": "move_forward", "distance": min(step, distance)}
        if kind == "face":
            angle = (item[1] - me["facing"] + 180) % 360 - 180
            return None if abs(angle) < 1e-6 else {"type": "turn", "angle": angle}
        if kind == "act":
            if self._waited:
                return None
            self._waited = 1
            return dict(item[1])
        if kind == "wait":
            if self._waited >= item[1]:
                return None
            self._waited += 1
            return {"type": "noop"}
        if kind == "at_step":
            return None if me["step"] >= item[1] else {"type": "noop"}
        if kind == "until":
            return None if item[1](self.env) else {"type": "noop"}
        if kind == "barrier":
            with self.oracle.lock:
                arrived = self.oracle.barriers.setdefault(item[1], {})
                arrived.setdefault(self.agent_id, me["step"])
                ready = all(a in arrived and arrived[a] < me["step"] for a in self.oracle.agent_ids)
            return None if ready else {"type": "noop"}
        if kind == "call":
            return item[1](self.env, self.agent_id, obs)
        raise ValueError(f"unknown plan item: {item!r}")


# 2인 운반: 두 에이전트가 같은 위치에서 똑같은 회전/전진을 같은 step에 하도록 펼친 plan
def carry_legs(start, waypoints, step=10.0) -> list:
    plan, (x, y) = [], start
    facing = None
    for tx, ty in waypoints:
        heading = math.degrees(math.atan2(ty - y, tx - x)) % 360
        if facing is None or abs((heading - facing + 180) % 360 - 180) > 1e-6:
            plan.append(("act", {"type": "turn", "facing": heading}))  # 항상 정확히 1 step (lockstep 유지)
            facing = heading
        distance = math.hypot(tx - x, ty - y)
        while distance > 1e-6:
            move = min(step, distance)
            plan.append(("act", {"type": "move_forward", "distance": move}))
            distance -= move
        x, y = tx, ty
    return plan


def near(env, agent_id, x, y, radius=1.0) -> bool:
    agent = env.agents[agent_id]
    return math.hypot(agent.x - x, agent.y - y) <= radius


def unlocked(door_id):
    return lambda env: not env.objects[door_id]["locked"]


# module: 시나리오 모듈, mode: "solution" 또는 "mistake". 반환: (클리어 step 또는 None, env)
def run(module, mode: str = "solution", max_steps: int = 400):
    env, _, objectives = build_environment(module.build())
    plans = getattr(module, mode)(env)
    oracle = Oracle(env.agents)
    for agent_id, plan in plans.items():
        env.agents[agent_id].set_policy(ScriptPolicy(oracle, env, agent_id, plan))
    for _ in range(max_steps):
        env.step()
        cleared = clear_step(env.event_log.entries, objectives)
        if cleared is not None:
            return cleared, env
    return None, env
