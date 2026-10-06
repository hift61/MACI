import math


# 에이전트 이동을 실제로 어떻게 처리할지 결정하는 추상 인터페이스.
# Environment.move_forward()는 내부 _move_agent()를 통해 이 인터페이스에 위임하므로,
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
# 잠긴 문의 radius와도 이동 선분 전체를 검사함 (에이전트끼리는 서로 통과 가능). 더 정교한 충돌
# 처리가 필요하면 world_core 쪽 물리 엔진으로 교체.
class SimplePhysicsEngine(PhysicsEngine):
    WALL_STANDOFF = 0.5  # 벽에 막혔을 때 벽면에서 띄워 멈추는 거리

    def resolve_move(self, environment, agent, dx: float, dy: float) -> tuple[float, float]:
        # Stop at the first map edge along the requested direction, without bending
        # a diagonal path by independently clamping its endpoint's x and y.
        boundary_t = 1.0
        for position, delta, limit in (
            (agent.x, dx, environment.game_map.map_width),
            (agent.y, dy, environment.game_map.map_height),
        ):
            if delta > 0:
                boundary_t = min(boundary_t, max(0.0, (limit - position) / delta))
            elif delta < 0:
                boundary_t = min(boundary_t, max(0.0, -position / delta))
        new_x = agent.x + dx * boundary_t
        new_y = agent.y + dy * boundary_t

        # 이동 경로 중간에 벽이 있으면 (한 번에 크게 움직여 벽을 뛰어넘는 것 포함) 벽 직전까지만 이동
        hits = [
            self._first_wall_hit(environment._walls(), agent.x, agent.y, new_x, new_y),
            self._first_door_hit(environment, agent.x, agent.y, new_x, new_y),
        ]
        t = min((hit for hit in hits if hit is not None), default=None)
        if t is not None:
            length = math.hypot(new_x - agent.x, new_y - agent.y)
            t = max(0.0, t - self.WALL_STANDOFF / length) if length > 0 else 0.0
            new_x = agent.x + (new_x - agent.x) * t
            new_y = agent.y + (new_y - agent.y) * t

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
            # 도착점이 벽 가장자리에 정확히 닿는 경우(겹치는 길이 0)도 부딪힌 것으로 침. 안 그러면
            # 벽 표면 위에 서게 되어, 그다음부터 벽을 따라 미끄러지는 이동이 전부 막힘
            elif first is None and wx <= x1 <= wx + ww and wy <= y1 <= wy + wh:
                first = 1.0
        return first

    @staticmethod
    def _first_door_hit(environment, x0: float, y0: float, x1: float, y1: float):
        """Earliest segment/circle contact, including doors crossed mid-move."""
        dx, dy = x1 - x0, y1 - y0
        length_squared = dx * dx + dy * dy
        if length_squared == 0:
            return None
        first = None
        for obj in environment.objects.values():
            if obj["type"] != "door" or not obj["locked"]:
                continue
            ox, oy = x0 - obj["x"], y0 - obj["y"]
            c = ox * ox + oy * oy - obj["radius"] ** 2
            projection = ox * dx + oy * dy
            # If a door closes around the agent, allow movement out of it.
            if c <= 0 and projection >= 0:
                continue
            if c <= 0:
                hit = 0.0
            else:
                discriminant = projection * projection - length_squared * c
                if discriminant < 0:
                    continue
                hit = (-projection - math.sqrt(discriminant)) / length_squared
                if not 0 <= hit <= 1:
                    continue
            first = hit if first is None else min(first, hit)
        return first
