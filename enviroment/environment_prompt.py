"""Agent identity, common mechanics and optional minimal objective descriptions.

정보 계약 v2 (2026-10-13, scenarios/MAP_GUIDE.md): 에이전트에게는 (a) 행동하는 데 필요한 인터페이스와
(b) 시야 제약 때문에 step 예산 안에 스스로 알아낼 수 없는 정보만 줌. 전략 힌트("소통은 선택", "짧게 답하라"),
물체 작동 설명, 역할 설명, 비용 규칙(기본 숨김, --disclose-costs)은 주지 않음.
"""

import json

PROMPT_CONTRACT = "v2"


# objective(EventLog 조건 dict) 한 개를 목표 문장으로. 모르는 종류는 JSON 그대로
_GOAL_SENTENCES = {
    'door_unlocked': lambda o: f"unlock door '{o['door_id']}'",
    'item_picked_up': lambda o: f"pick up '{o['object_id']}'",
    'team_assembled': lambda o: f"be inside goal_zone '{o['zone_id']}' at the same time "
                                f"(everyone named in its 'agents' field, or all agents)",
    'keypad_solved': lambda o: f"open keypad '{o['panel_id']}'",
    'sync_success': lambda o: f"succeed with the sync pads of group '{o['group']}'",
    'delivery_complete': lambda o: f"deliver items to receptacle '{o['receptacle_id']}' until it reaches its target",
    'all_checkpoints_visited': lambda o: "visit every checkpoint",
    'all_targets_filled': lambda o: "get a block onto every block_target at the same time",
    'scale_balanced': lambda o: f"make scale '{o['scale_id']}' read 'balanced'",
    'all_stages_completed': lambda o: "clear every stage in order (the current stage's goal is observation 'stage')",
}


def objective_description(objectives):
    goals = []
    for objective in objectives:
        sentence = _GOAL_SENTENCES.get(objective.get('type'))
        try:
            goals.append(sentence(objective) if sentence else json.dumps(objective, ensure_ascii=False))
        except KeyError:
            goals.append(json.dumps(objective, ensure_ascii=False))
    return ' Goal: ' + '; '.join(goals) + '.' if goals else ''


def environment_description(agent_id, agent_ids, width, height):
    others = ", ".join(a for a in agent_ids if a != agent_id) or "none"
    return (
        f"You are agent {agent_id} in a {width}x{height} area. Other agents: {others}; they never appear in "
        "your observations, and send_message with their ID reaches them. "
        "You see objects within a 90-degree view cone up to 200 units away; walls block sight. "
        "Coordinates are continuous; facing is in degrees (0 right, 90 down, 180 left, 270 up). "
        "self.step is a clock shared by all agents."
    )
