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
        self.x = x
        self.y = y
        self.facing = facing            # 바라보는 방향 (도, 0~360)
        self.view_radius = view_radius  # 시야 반경
        self.view_angle = view_angle    # 시야각 (전체 폭, 도)
        self.inventory: list = []
        self.inbox: list = []
        self.policy: Policy | None = None  # 탑재된 AI (Policy 인터페이스 구현체)
        self.rules: list[Rule] = []        # 이 에이전트에게만 적용되는 강제 규칙 목록

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
