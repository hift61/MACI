"""Agent identity, common mechanics and optional minimal objective descriptions.

정보 계약 v2 (2026-10-13, scenarios/MAP_GUIDE.md): 에이전트에게는 (a) 행동하는 데 필요한 인터페이스와
(b) 시야 제약 때문에 step 예산 안에 스스로 알아낼 수 없는 정보만 줌. 전략 힌트("소통은 선택", "짧게 답하라"),
물체 작동 설명, 역할 설명, 비용 규칙(기본 숨김, --disclose-costs)은 주지 않음.
"""

import json

PROMPT_CONTRACT = "v2"


def objective_description(objectives):
    goals = []
    for objective in objectives:
        if objective.get('type') == 'door_unlocked':
            goals.append(f"unlock door '{objective['door_id']}'")
        else:
            goals.append(json.dumps(objective, ensure_ascii=False))
    return ' Goal: achieve all of the following: ' + '; '.join(goals) + '.' if goals else ''


def environment_description(agent_id, agent_ids, width, height):
    others = ", ".join(a for a in agent_ids if a != agent_id) or "none"
    return (
        f"You are agent {agent_id} in a {width}x{height} area. Other agents: {others}; they never appear in "
        "your observations, and send_message with their ID reaches them. "
        "You see objects within a 90-degree view cone up to 200 units away; walls block sight. "
        "Coordinates are continuous; facing is in degrees (0 right, 90 down, 180 left, 270 up). "
        "self.step is a clock shared by all agents."
    )
