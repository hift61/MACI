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


# 환경의 상태를 실제로 바꾼 사건(문 열림/잠김, 물품 습득, 압력판 점유, 포탈 이동, 함정 발동
# 등)과 그 사건을 일으킨 에이전트를 기록. DecisionLog가 "무엇을 하려 했나"라면 이쪽은
# "그래서 실제로 무슨 일이 일어났고 누구 덕/탓인가"로, 마일스톤 기반 채점과 에이전트별
# 기여도(credit) 산정에 사용한다. 상태가 바뀌지 않은 시도(이미 열린 문에 열쇠 사용 등)는
# 기록하지 않고, 협력 판단에 의미 있는 실패(coop 물품 단독 습득/이동 시도)만 따로 기록한다.
# Environment가 각 처리 지점에서 자동으로 기록한다.
class EventLog:
    def __init__(self) -> None:
        self.entries: list[dict] = []

    # step: 사건이 일어난 시점의 Environment.step_count
    # event_type: 사건 종류 (enviroment.py의 Environment 주석/INTERFACE.md의 이벤트 목록 참고)
    # agent_ids: 사건을 일으킨(공로/책임이 있는) 에이전트 목록. 압력판으로 문이 열린 경우처럼
    #            여러 명이 함께 일으킨 사건이면 여러 명, 환경이 스스로 일으킨 사건이면 빈 목록
    # fields: 사건별 추가 정보 (door_id, object_id, cause 등)
    def record(self, step: int, event_type: str, agent_ids: list[str], **fields) -> None:
        self.entries.append({
            "step": step,
            "type": event_type,
            "agent_ids": list(agent_ids),
            **copy.deepcopy(fields)
        })

    # event_type/agent_id(agent_ids에 포함되는지)/step 중 지정한 조건만 만족하는 항목을
    # 반환 (모두 생략하면 전체 기록 그대로)
    def filter(
        self,
        event_type: str = None,
        agent_id: str = None,
        step: int = None
    ) -> list[dict]:
        result = self.entries
        if event_type is not None:
            result = [e for e in result if e["type"] == event_type]
        if agent_id is not None:
            result = [e for e in result if agent_id in e["agent_ids"]]
        if step is not None:
            result = [e for e in result if e["step"] == step]
        return result

    def clear(self) -> None:
        self.entries = []
