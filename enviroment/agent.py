import copy
import math

from policy import Policy
from rule import Rule


class Agent:
    def __init__(
        self,
        agent_id: str,
        x: float,
        y: float,
        facing: float = 0.0,
        view_radius: float = 100.0,
        view_angle: float = 90.0
    ) -> None:
        self.agent_id = agent_id
        self.x = float(x)
        self.y = float(y)
        self.facing = float(facing) % 360  # 도 단위. 화면 픽셀과 별개인 연속 좌표
        self.last_move: dict | None = None
        self.view_radius = view_radius  # 시야 반경
        self.view_angle = view_angle    # 시야각 (전체 폭, 도)
        self.inventory: list = []
        self.inbox: list = []
        self.memory: dict = {}          # 에이전트가 action의 "memory"로 직접 남기는 메모장 (관찰의 memory)
        self.policy: Policy | None = None  # 탑재된 AI (Policy 인터페이스 구현체)
        self.rules: list[Rule] = []        # 이 에이전트에게만 적용되는 강제 규칙 목록

    @property
    def heading(self) -> tuple[float, float]:
        angle = math.radians(self.facing)
        dx, dy = math.cos(angle), math.sin(angle)
        # Exact cardinal headings must not drift into a map boundary.
        return (0.0 if abs(dx) < 1e-15 else dx, 0.0 if abs(dy) < 1e-15 else dy)

    def spatial_state(self) -> dict:
        """Position/heading in world units; last_move excludes portal teleportation."""
        dx, dy = self.heading
        return {
            "x": self.x,
            "y": self.y,
            "facing": self.facing,
            "heading": {"x": dx, "y": dy},
            "last_move": copy.deepcopy(self.last_move),
        }

    # Attach an AI (any Policy implementation) to this agent
    def set_policy(self, policy: Policy) -> None:
        self.policy = policy

    # Ask the attached AI to turn an observation into an action
    def decide(self, observation: dict) -> dict:
        if self.policy is None:
            return {"type": "noop"}
        return self.policy.decide(observation)

    # Attach an agent-specific rule (in addition to environment-wide rules)
    def add_rule(self, rule: Rule) -> None:
        self.rules.append(rule)
