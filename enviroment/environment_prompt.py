"""Agent identity, common mechanics and optional minimal objective descriptions."""

import json
from token_usage import TOKEN_ALLOWANCE, TOKEN_PENALTY_PER_1000


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
        f"You are agent {agent_id} in a {width}x{height} area. Other agents: {others}. "
        "Other agents exist but are not included in your visible object list. "
        "You can communicate with them using their IDs and send_message. "
        "Communication is optional: if you judge a message or reply unnecessary, do not send one. "
        "Receiving a message does not require acknowledging it or replying. "
        f"Excessive output token consumption reduces your score: each agent has {TOKEN_ALLOWANCE} free "
        f"API-reported output tokens per episode, then loses {TOKEN_PENALTY_PER_1000:g} point "
        "per 1,000 extra output tokens, proportionally. Input and repeated context tokens are not penalized. "
        "Keep responses concise and avoid unnecessary communication and LLM calls. "
        "You see objects within a 90-degree view cone, up to 200 world units away; walls block sight. "
        "Coordinates and distances are continuous. Facing is in degrees: 0 right, 90 down, "
        "180 left, 270 up. turn(angle) rotates in place, positive clockwise. "
        "move_forward(distance) advances along your current heading without turning; "
        "walls, locked doors, boundaries and max_move limit movement. "
        "Observations contain your state, visible objects, previously seen objects, nearby walls, "
        "inbox and memory. Previously seen object states can be outdated. "
        "Object content is available through observation when the object is seen. "
        "Return one action per step; include memory to save notes for subsequent steps."
    )
