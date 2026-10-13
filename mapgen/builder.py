import os
import sys

from .spec import MapSpec

# MapSpec -> Environment 변환. mapgen 패키지에서 enviroment/를 import하는 유일한 파일이므로,
# 맵 생성기를 다른 환경에 붙이고 싶으면 이 파일만 바꾸면 됨.

ENVIRONMENT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "enviroment")
if ENVIRONMENT_DIR not in sys.path:
    sys.path.insert(0, ENVIRONMENT_DIR)  # enviroment/*.py use flat sibling imports

from enviroment import Environment  # noqa: E402
from environment_prompt import environment_description, objective_description  # noqa: E402


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
# 시나리오 맵(spec.scenario 또는 spec.rules가 있음)은 scenarios.engine.ScenarioEnvironment로 만듦 -
# 기존 Environment를 상속해 시나리오 전용 물체(add_keypad 등)와 규칙만 더한 것
def build_environment(spec: MapSpec, interact_radius: float = 15.0, reveal_goal: bool = True):
    if spec.scenario or spec.rules:
        from scenarios.engine import ScenarioEnvironment
        env = ScenarioEnvironment(GeneratedMap(spec), rules=spec.rules, seed=spec.seed,
                                  interact_radius=interact_radius)
    else:
        env = Environment(GeneratedMap(spec), interact_radius=interact_radius)

    for obj in spec.objects:
        add = getattr(env, f"add_{obj['kind']}")
        add(obj["id"], obj["x"], obj["y"], **obj["params"])

    for agent in spec.agents:
        view = {key: agent[key] for key in ("view_radius", "view_angle") if key in agent}
        env.add_agent(agent["id"], x=agent["x"], y=agent["y"], facing=agent["facing"], **view)
    # 단계형 시나리오 맵은 에이전트 배치가 끝난 뒤 첫 단계를 불러옴 (scenarios/engine.py)
    if hasattr(env, "begin_stages"):
        env.begin_stages()

    return env, task_descriptions(spec, reveal_goal=reveal_goal), list(spec.objectives)


def task_descriptions(spec: MapSpec, reveal_goal: bool = True) -> dict[str, str]:
    agent_ids = [a["id"] for a in spec.agents]
    descriptions = {aid: environment_description(aid, agent_ids, spec.width, spec.height)
                         + (objective_description(spec.objectives) if reveal_goal else '')
                    for aid in agent_ids}
    # 시나리오 맵의 개인별 안내 (새 물체 설명, 맵 규칙)
    for agent_id, briefing in (getattr(spec, "briefings", None) or {}).items():
        if agent_id in descriptions and briefing:
            descriptions[agent_id] += "\n" + briefing
    return descriptions
