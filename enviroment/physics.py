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
# 맵 경계 안으로 좌표를 clamp하고, 잠긴 문의 radius 안쪽으로는 진입을 막는 것 외에는
# 아무 충돌 처리도 하지 않음 (에이전트끼리는 서로 통과 가능). 벽 등 정적 물리 구조는
# world_core 쪽 물리 엔진이 맡을 영역이라 여기서는 다루지 않음.
class SimplePhysicsEngine(PhysicsEngine):
    def resolve_move(self, environment, agent, dx: float, dy: float) -> tuple[float, float]:
        new_x = min(max(agent.x + dx, 0), environment.game_map.map_width)
        new_y = min(max(agent.y + dy, 0), environment.game_map.map_height)

        if self._blocked_by_door(environment, new_x, new_y):
            return agent.x, agent.y

        return new_x, new_y

    def _blocked_by_door(self, environment, x: float, y: float) -> bool:
        for obj in environment.objects.values():
            if obj["type"] == "door" and obj["locked"]:
                if math.hypot(x - obj["x"], y - obj["y"]) <= obj["radius"]:
                    return True
        return False
