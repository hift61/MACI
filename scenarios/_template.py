"""새 시나리오 템플릿 - 이 파일을 sNN_이름.py로 복사해서 고쳐 쓰세요 (만드는 순서는 scenarios/MAP_GUIDE.md).

그대로도 풀리는 작은 예제가 들어 있음: 왼쪽 방의 판을 한 명이 밟아 문을 열어 주고, 건너간 사람이
래치 레버로 문을 영구히 연 뒤 둘이 오른쪽 구역에 모이면 클리어.
SCENARIO_NAMES에 등록하지 않은 파일이라 맵으로 내보내지지 않음 (테스트에서만 검증).
"""
from .common import agent, explain, make_spec, obj, vwall

# ---- 1. 이름표 ------------------------------------------------------------
NAME = "s00_template"   # 파일 이름과 같게 (맵 파일: map_datas/<NAME>.json)
TITLE = "템플릿 예제"     # 한국어 이름 (문서/목록용)
FAMILY = "순서 계획"      # 계열: 순서 계획/공동 추론/통신 규약/사회적 딜레마/작업 분배/시간 예측/신뢰, 검증


# ---- 2. 맵 -------------------------------------------------------------------
# 좌표: 0~width, 0~height, y는 아래로 증가. facing 0=오른쪽, 90=아래, 180=왼쪽, 270=위
def build():
    # 벽: [x, y, w, h]. vwall/hwall은 gaps 자리를 비워 줌 -> 폭 20 틈에 반경 12 문을 끼우면 막힘
    walls = vwall(150, 0, 200, gaps=[(100, 20)])

    objects = [
        # 장치. kind = Environment.add_<kind>, 나머지 키워드 = 그 함수 인자 (MAP_GUIDE.md 3장 표)
        obj("door", "gate", 155, 100, locked=True, radius=12.0),
        obj("switch_plate", "plate", 30, 30, opens=["gate"]),
        obj("latch_lever", "latch", 250, 170, doors=["gate"]),
        obj("goal_zone", "exit", 225, 100, width=150, height=200, label="east room"),
        # 단서: 에이전트가 읽는 내용은 영어. dict로 주제별로 나누면 읽기 쉬움.
        # hidden=False면 멀리서도(시야 안) 보이고, True면 15 이내로 가야 보임
        obj("clue", "note", 60, 180, hidden=False, content={
            "plate": "Standing on 'plate' holds 'gate' open. Nobody can stand on the plate and walk "
                     "through the gate at the same time.",
            "latch": "The lever 'latch' in the east room opens the gate permanently.",
        }),
    ]

    # 과제 설명 끝에 붙는 개인별 안내문 (영어). 상황 + 읽을 단서 + 새 물체 설명(explain)
    guide = explain("switch_plate", "latch_lever", "goal_zone")
    briefing = f"You and your teammate start in the west room. Read the clue 'note'. {guide}"

    return make_spec(
        NAME, 300, 200, walls,
        [agent("A", 60, 100, 0), agent("B", 80, 120, 0)],
        objects,
        # 클리어 조건: EventLog 이벤트와 키/값이 모두 같으면 충족 (MAP_GUIDE.md 4장 표)
        objectives=[{"type": "team_assembled", "zone_id": "exit"}],
        # 목표 문장 (목표 공개 시 "Goal: ..."로 보여 줌, 영어)
        hints=["Both agents must stand inside the goal_zone 'exit' (east room) at the same time."],
        briefings={"A": briefing, "B": briefing},
        rules={},                 # 메시지 손실/길이 제한 등이 필요하면 (MAP_GUIDE.md 5장)
        recommended_steps=60)     # LLM 실행 권장 step (오라클 클리어 step의 3~5배 정도)


# ---- 3. 검증용 plan (LLM과 무관, 맵이 실제로 풀리는지 확인) -------------------------
# 항목 형식은 oracle.py 맨 위 설명. 상호작용은 대상에서 15 이내 - 12~13 정도로 여유 있게 설 것
def solution(env):
    from .oracle import unlocked
    return {
        "A": [("goto", 30, 30), ("until", lambda e: e.objects["gate"].get("latched")),
              ("goto", 140, 100), ("goto", 200, 100)],
        "B": [("until", unlocked("gate")), ("goto", 140, 100), ("goto", 180, 100), ("goto", 250, 157),
              ("act", {"type": "pull_lever", "lever_id": "latch"}), ("goto", 220, 100)],
    }


# 실수한 뒤에도 풀리는지: 실수 -> (대가: 시간) -> 정답. 실수가 실제로 시간을 잃게 하는지도 확인할 것
def mistake(env):
    plans = solution(env)
    plans["A"] = [("goto", 140, 90), ("wait", 5)] + plans["A"]  # 둘 다 아무도 판을 안 밟은 채 문 앞에서 기다림
    plans["B"] = [("goto", 140, 110)] + plans["B"]
    return plans
