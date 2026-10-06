import os
import sys

from .spec import MapSpec

# MapSpec -> Environment 변환. mapgen 패키지에서 enviroment/를 import하는 유일한 파일이므로,
# 맵 생성기를 다른 환경에 붙이고 싶으면 이 파일만 바꾸면 됨.

ENVIRONMENT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "enviroment")
if ENVIRONMENT_DIR not in sys.path:
    sys.path.insert(0, ENVIRONMENT_DIR)  # enviroment/*.py use flat sibling imports

from enviroment import Environment  # noqa: E402


class WallRect:
    def __init__(self, x: float, y: float, width: float, height: float) -> None:
        self.x, self.y, self.width, self.height = x, y, width, height


# Environment가 맵에서 쓰는 것만 가진 최소 맵 객체 (map_width/map_height: 이동 범위,
# walls: 시야 가림 - Environment._walls 참고). world_core.GameMap에 의존하지 않기 위함
class GeneratedMap:
    def __init__(self, spec: MapSpec) -> None:
        self.map_width = spec.width
        self.map_height = spec.height
        self.walls = [WallRect(*wall) for wall in spec.walls]


# 반환: (env, 에이전트별 과제 설명, objectives)
def build_environment(spec: MapSpec, interact_radius: float = 15.0):
    env = Environment(GeneratedMap(spec), interact_radius=interact_radius)

    for obj in spec.objects:
        add = getattr(env, f"add_{obj['kind']}")
        add(obj["id"], obj["x"], obj["y"], **obj["params"])

    for agent in spec.agents:
        env.add_agent(agent["id"], x=agent["x"], y=agent["y"], facing=agent["facing"])

    return env, task_descriptions(spec), list(spec.objectives)


def task_descriptions(spec: MapSpec) -> dict[str, str]:
    agent_ids = [a["id"] for a in spec.agents]
    goals = "\n".join(f"- {hint}" for hint in spec.hints)
    descriptions = {}
    for agent_id in agent_ids:
        others = ", ".join(a for a in agent_ids if a != agent_id) or "none"
        descriptions[agent_id] = (
            f"You are agent {agent_id} in a {spec.width}x{spec.height} area. Other agents: {others}. "
            f"The team clears the map when ALL of these goals have been achieved:\n{goals}\n"
            f"You only see objects inside your view cone (90 degrees around your facing, about 100 units "
            f"far), and walls block sight. You can only move forward along your body's heading with "
            f"move_forward(distance); fractional distances are allowed. To choose a new direction, "
            f"turn(angle) rotates your body in place (degrees; positive clockwise, negative counterclockwise), "
            f"then move forward on a later step. Forward motion preserves heading. "
            f"You cannot see other agents - use send_message to share what you find and coordinate."
        )
    return descriptions
