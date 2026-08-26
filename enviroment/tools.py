# OpenAI function-calling(tool) 스키마 목록.
# Environment.apply_action()이 처리하는 action type과 1:1로 대응되므로,
# apply_action에 새 action type을 추가/변경하면 여기도 함께 갱신해야 함.
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "move",
            "description": "현재 위치에서 (dx, dy)만큼 이동한다",
            "parameters": {
                "type": "object",
                "properties": {
                    "dx": {"type": "number", "description": "x축 이동량"},
                    "dy": {"type": "number", "description": "y축 이동량"}
                },
                "required": ["dx", "dy"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "pick_up",
            "description": "상호작용 범위 안에 있는 물체(item 또는 key)를 습득해 인벤토리에 넣는다",
            "parameters": {
                "type": "object",
                "properties": {
                    "object_id": {"type": "string", "description": "습득할 물체의 object_id"}
                },
                "required": ["object_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "drop",
            "description": "인벤토리의 물체를 현재 위치에 내려놓는다",
            "parameters": {
                "type": "object",
                "properties": {
                    "object_id": {"type": "string", "description": "내려놓을 물체의 object_id"}
                },
                "required": ["object_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "use_key",
            "description": "인벤토리의 열쇠를 사용해 상호작용 범위 안의 대응 문을 잠금 해제한다. 열쇠는 소모된다",
            "parameters": {
                "type": "object",
                "properties": {
                    "key_id": {"type": "string", "description": "사용할 열쇠의 object_id"}
                },
                "required": ["key_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "press_button",
            "description": "상호작용 범위 안의 버튼을 눌러 연결된 문의 잠금 상태를 토글한다",
            "parameters": {
                "type": "object",
                "properties": {
                    "button_id": {"type": "string", "description": "누를 버튼의 object_id"}
                },
                "required": ["button_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "pull_lever",
            "description": "상호작용 범위 안의 레버를 당겨 on/off 상태를 뒤집고, 연결된 문들을 함께 제어한다",
            "parameters": {
                "type": "object",
                "properties": {
                    "lever_id": {"type": "string", "description": "당길 레버의 object_id"}
                },
                "required": ["lever_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_message",
            "description": "다른 에이전트 한 명에게 자유 텍스트 메시지를 보낸다",
            "parameters": {
                "type": "object",
                "properties": {
                    "receiver_id": {"type": "string"},
                    "content": {"type": "string"}
                },
                "required": ["receiver_id", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "share_belief",
            "description": "특정 대상(subject)에 대한 사실 주장(claim)을 다른 에이전트에게 전달한다",
            "parameters": {
                "type": "object",
                "properties": {
                    "receiver_id": {"type": "string"},
                    "subject": {"type": "string", "description": "주장의 대상 (예: object_id)"},
                    "claim": {"type": "string", "description": "주장 내용"}
                },
                "required": ["receiver_id", "subject", "claim"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "request_info",
            "description": "다른 에이전트에게 특정 대상(subject)에 대한 정보를 요청한다",
            "parameters": {
                "type": "object",
                "properties": {
                    "receiver_id": {"type": "string"},
                    "subject": {"type": "string"}
                },
                "required": ["receiver_id", "subject"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "confirm",
            "description": "이전에 받은 belief 또는 request(subject)에 대해 동의 또는 거부 의사를 전달한다",
            "parameters": {
                "type": "object",
                "properties": {
                    "receiver_id": {"type": "string"},
                    "subject": {"type": "string"},
                    "agree": {"type": "boolean"}
                },
                "required": ["receiver_id", "subject", "agree"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "claim_role",
            "description": "자신이 맡을 역할을 다른 모든 에이전트에게 공개 선언(broadcast)한다",
            "parameters": {
                "type": "object",
                "properties": {
                    "role": {"type": "string"}
                },
                "required": ["role"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "claim_task",
            "description": "자신이 맡을 작업을 다른 모든 에이전트에게 공개 선언(broadcast)한다",
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {"type": "string"}
                },
                "required": ["task"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "issue_command",
            "description": (
                "다른 에이전트에게 명령을 내린다. 그 에이전트가 이 명령을 따르도록 "
                "설정되어 있다면(중심-주변 구조), 자신의 판단과 무관하게 command를 그대로 실행한다. "
                "command는 수신자가 실행할 action이며 type 필드를 포함해야 한다 "
                "(예: {\"type\": \"move\", \"dx\": 5, \"dy\": 0})"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "receiver_id": {"type": "string"},
                    "command": {
                        "type": "object",
                        "description": "수신자가 실행할 action(dict). type 필드 필수"
                    }
                },
                "required": ["receiver_id", "command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "noop",
            "description": "아무 행동도 하지 않는다",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    }
]
