import copy


# 에이전트 사이에 오간 메시지를 순서대로 기록. README의 반사실적 재현(counterfactual
# replay) - "언제, 어느 에이전트가 실패를 유발했는지" 분석 - 을 하려면 대화 기록이 남아있어야
# 하므로, Environment._deliver()가 메시지를 전달할 때마다 자동으로 여기에 기록한다.
# 실험이 끝난 뒤 실험자가 이 기록을 그대로 읽거나 filter()로 걸러서 분석에 사용.
class MessageLog:
    def __init__(self) -> None:
        self.entries: list[dict] = []

    # step: 메시지가 전달된 시점의 Environment.step_count
    # message: type/from(및 type별 필드: subject/claim/content/command 등)이 이미 담긴 dict
    def record(self, step: int, receiver_id: str, message: dict) -> None:
        self.entries.append({
            "step": step,
            "receiver_id": receiver_id,
            **copy.deepcopy(message)
        })

    # sender_id("from")/receiver_id/message_type("type") 중 지정한 조건만 만족하는 항목을
    # 반환 (모두 생략하면 전체 기록 그대로)
    def filter(
        self,
        sender_id: str = None,
        receiver_id: str = None,
        message_type: str = None
    ) -> list[dict]:
        result = self.entries
        if sender_id is not None:
            result = [e for e in result if e.get("from") == sender_id]
        if receiver_id is not None:
            result = [e for e in result if e.get("receiver_id") == receiver_id]
        if message_type is not None:
            result = [e for e in result if e.get("type") == message_type]
        return result

    def clear(self) -> None:
        self.entries = []


# 매 step마다 각 에이전트가 무엇을 관찰했고, 자신의 policy가 무엇을 결정했으며, Rule
# 강제 적용 이후 실제로는 무엇이 실행됐는지를 기록. "이 에이전트가 이 시점에 다른 행동을
# 했다면 어떻게 됐을까"를 물으려면(반사실적 재현) 그 시점의 관찰과 실제 결정이 남아있어야
# 하므로, Environment.step()이 매 에이전트 결정마다 자동으로 여기 기록한다.
class DecisionLog:
    def __init__(self) -> None:
        self.entries: list[dict] = []

    # action: agent.decide()가 실제로 고른 원본 action (policy의 결정)
    # final_action: Environment.apply_action()이 Rule 강제까지 반영해 실제로 실행한 action
    #               (Rule이 개입 안 했으면 action과 동일)
    def record(self, step: int, agent_id: str, observation: dict, action: dict, final_action: dict) -> None:
        self.entries.append({
            "step": step,
            "agent_id": agent_id,
            "observation": copy.deepcopy(observation),
            "action": copy.deepcopy(action),
            "final_action": copy.deepcopy(final_action),
            "overridden": action != final_action  # Rule이 policy의 결정을 바꿔치기했는지
        })

    # agent_id/step/action_type("action"의 "type")/overridden 중 지정한 조건만 만족하는
    # 항목을 반환 (모두 생략하면 전체 기록 그대로)
    def filter(
        self,
        agent_id: str = None,
        step: int = None,
        action_type: str = None,
        overridden: bool = None
    ) -> list[dict]:
        result = self.entries
        if agent_id is not None:
            result = [e for e in result if e["agent_id"] == agent_id]
        if step is not None:
            result = [e for e in result if e["step"] == step]
        if action_type is not None:
            result = [e for e in result if e["action"].get("type") == action_type]
        if overridden is not None:
            result = [e for e in result if e["overridden"] == overridden]
        return result

    def clear(self) -> None:
        self.entries = []
