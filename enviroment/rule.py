class Rule:
    # 실험을 위해 정해두는 강제 규칙의 추상 인터페이스.
    # 에이전트의 AI(policy)가 결정한 action을 검사하고, 필요하면 다른 action으로 강제 교체함.
    # AI가 무엇을 고르든 이 규칙을 통과한 action만 environment에 실제로 적용되므로,
    # 에이전트는 이 규칙을 무조건 따르게 됨.
    def enforce(self, agent, observation: dict, action: dict) -> dict:
        raise NotImplementedError


# 아무 제약 없이 action을 그대로 통과시키는 기본 규칙
class AllowAllRule(Rule):
    def enforce(self, agent, observation: dict, action: dict) -> dict:
        return action


# 지정한 action type들을 금지하고, 시도하면 noop으로 강제 교체
# 예: ForbidActionRule({"send_message"}) -> 해당 에이전트는 메시지를 보낼 수 없음
class ForbidActionRule(Rule):
    def __init__(self, forbidden_types) -> None:
        self.forbidden_types = set(forbidden_types)

    def enforce(self, agent, observation: dict, action: dict) -> dict:
        if action.get("type") in self.forbidden_types:
            return {"type": "noop"}
        return action


# 중심-주변(hierarchical) 에이전트 구조를 위한 규칙.
# commander_id로부터 "command" 타입 메시지가 오면, 이 에이전트 자신의 policy가
# 무엇을 결정했든 무시하고 그 명령(action)을 그대로 강제 실행함.
# 명령은 한 번 실행되면 inbox 메시지에 "handled"로 표시되어 다시 반복 실행되지 않음
# (같은 명령이 매 틱 재실행되는 것을 방지).
class ObeyCommandRule(Rule):
    def __init__(self, commander_id: str) -> None:
        self.commander_id = commander_id

    def enforce(self, agent, observation: dict, action: dict) -> dict:
        for message in observation["inbox"]:
            if message.get("type") != "command" or message.get("from") != self.commander_id:
                continue
            if message.get("handled"):
                continue

            command = message.get("command")
            message["handled"] = True
            if isinstance(command, dict) and "type" in command:
                return command

        return action
