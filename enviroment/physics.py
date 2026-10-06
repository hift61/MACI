import math


# 에이전트 이동을 실제로 어떻게 처리할지 결정하는 추상 인터페이스.
# Environment.move_agent()는 이동 계산을 직접 하지 않고 이 인터페이스에 위임하므로,
# 나중에 팀원이 정교한 물리 엔진을 만들면 이 클래스를 상속한 구현체로 통째로 교체해
# Environment.__init__(physics=...)에 넣기만 하면 됨 (agent/policy/rule/tools 쪽은
# 그대로 두고 물리 계산만 바꿔 끼우는 구조).
class PhysicsEngine:
    def resolve_move(self, environment, agent, dx: float, dy: float) -> tuple[float, float]:
        # environment: 맵 크기(game_map)와 오브젝트(objects)를 조회할 때 필요
        # agent: 이동을 시도하는 에이전트 (현재 agent.x, agent.y 포함)
        # 반환값: 충돌/경계를 반영해 실제로 적용할 최종 (x, y)
        raise NotImplementedError


# 실제 물리 엔진이 들어오기 전까지 쓰는 자리표시자(placeholder) 기본 구현.
# 맵 경계 안으로 좌표를 clamp하고, 벽(environment._walls())에 닿으면 그 직전에서 멈추고,
# 잠긴 문의 radius 안쪽으로는 진입을 막음 (에이전트끼리는 서로 통과 가능). 더 정교한 충돌
# 처리가 필요하면 world_core 쪽 물리 엔진으로 교체.
class SimplePhysicsEngine(PhysicsEngine):
    WALL_STANDOFF = 0.5  # 벽에 막혔을 때 벽면에서 띄워 멈추는 거리

    def resolve_move(self, environment, agent, dx: float, dy: float) -> tuple[float, float]:
        new_x = min(max(agent.x + dx, 0), environment.game_map.map_width)
        new_y = min(max(agent.y + dy, 0), environment.game_map.map_height)

        # 이동 경로 중간에 벽이 있으면 (한 번에 크게 움직여 벽을 뛰어넘는 것 포함) 벽 직전까지만 이동
        t = self._first_wall_hit(environment._walls(), agent.x, agent.y, new_x, new_y)
        if t is not None:
            length = math.hypot(new_x - agent.x, new_y - agent.y)
            t = max(0.0, t - self.WALL_STANDOFF / length) if length > 0 else 0.0
            new_x = agent.x + (new_x - agent.x) * t
            new_y = agent.y + (new_y - agent.y) * t

        if self._blocked_by_door(environment, new_x, new_y):
            return agent.x, agent.y

        return new_x, new_y

    # (x0, y0)->(x1, y1) 선분이 벽 안으로 처음 들어가는 지점의 비율 t(0~1). 안 부딪히면 None.
    # 이미 벽 안에 있는 상태(시작점이 벽 내부)라면 그 벽은 무시해서 빠져나올 수 있게 함
    @staticmethod
    def _first_wall_hit(walls, x0: float, y0: float, x1: float, y1: float):
        dx, dy = x1 - x0, y1 - y0
        first = None
        for wx, wy, ww, wh in walls:
            if wx < x0 < wx + ww and wy < y0 < wy + wh:
                continue
            t_enter, t_exit = 0.0, 1.0
            hit = True
            for p, q in ((-dx, x0 - wx), (dx, wx + ww - x0), (-dy, y0 - wy), (dy, wy + wh - y0)):
                if p == 0:
                    if q < 0:
                        hit = False
                        break
                    continue
                t = q / p
                if p < 0:
                    t_enter = max(t_enter, t)
                else:
                    t_exit = min(t_exit, t)
            if hit and t_enter < t_exit and t_enter <= 1 and (first is None or t_enter < first):
                first = t_enter
        return first

    def _blocked_by_door(self, environment, x: float, y: float) -> bool:
        for obj in environment.objects.values():
            if obj["type"] == "door" and obj["locked"]:
                if math.hypot(x - obj["x"], y - obj["y"]) <= obj["radius"]:
                    return True
        return False
