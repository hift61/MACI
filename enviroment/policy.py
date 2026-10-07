import json
import math
import random
import time
import traceback
import copy
import queue
import threading
from pathlib import Path

from openai import OpenAI, RateLimitError

from _policy_harness import _check_code_safety  # 생성 단계와 실행 단계가 같은 검사를 쓰도록
from policy_sandbox import run_decide_code, compile_policy_code, CodeChecks
from tools import TOOLS

_RATE_LIMIT_MAX_RETRIES = 3
_RATE_LIMIT_DEFAULT_DELAY_SEC = 5.0


# OpenRouter 무료 모델은 여러 사용자가 나눠 쓰는 공용 풀이라 일시적인 429가 흔함.
# 이런 요청 하나를 즉시 포기하고 noop으로 넘기면(특히 CodePolicy처럼 코드를 "한 번만"
# 생성해야 하는 경우) 상위 루프의 짧은 스텝 간격 때문에 429를 계속 다시 유발하게 되므로,
# 서버가 알려주는 Retry-After(없으면 기본값)만큼 기다렸다가 몇 번 재시도한다.
def _create_with_retry(client, **kwargs):
    for attempt in range(_RATE_LIMIT_MAX_RETRIES):
        try:
            return client.chat.completions.create(**kwargs)
        except RateLimitError as exc:
            if attempt == _RATE_LIMIT_MAX_RETRIES - 1:
                raise
            delay = _RATE_LIMIT_DEFAULT_DELAY_SEC
            response = getattr(exc, "response", None)
            header_value = response.headers.get("Retry-After") if response is not None else None
            if header_value is not None:
                try:
                    delay = float(header_value)
                except ValueError:
                    pass
            time.sleep(delay)


class Policy:
    @property
    def conversation_history(self):
        if not hasattr(self, '_conversation_history'):
            self._conversation_history = []
        return self._conversation_history

    def remember_step(self, observation, action, next_observation):
        if not hasattr(self, '_conversation_history'):
            return
        self.conversation_history.append({'role': 'user', 'content': 'Simulation step result:\n' + json.dumps(
            {'observation': observation, 'executed_action': action, 'next_observation': next_observation,
             'policy_error': getattr(self, 'last_error', None)},
            ensure_ascii=False, default=str)})

    def _debug(self, event, **details):
        callback = getattr(self, 'debug_sink', None)
        if callback:
            callback(event, details)

    def _generate_tracked(self, *args, **kwargs):
        kwargs['history'] = self.conversation_history
        self._debug('llm_request_started', context_messages=len(self.conversation_history))
        started = time.monotonic()
        try:
            code = _generate_code_with_submission_gate(*args, **kwargs)
            self._debug('code_generated', elapsed_seconds=round(time.monotonic()-started, 3), code=code,
                        context_messages=len(self.conversation_history))
            return code
        except Exception:
            self._debug('llm_request_failed', error=traceback.format_exc())
            raise

    @property
    def code_checks(self):
        if not hasattr(self, '_code_checks'):
            self._code_checks = CodeChecks()
        return self._code_checks

    # AI가 탑재되는 지점의 추상 인터페이스.
    # 실제 AI(규칙 기반, 강화학습, LLM 등)는 이 클래스를 상속해 decide()만 구현하면 됨.
    def decide(self, observation: dict) -> dict:
        raise NotImplementedError


# 아무 행동도 하지 않는 기본 정책 (AI 미탑재 상태의 기본값)
class NoopPolicy(Policy):
    def decide(self, observation: dict) -> dict:
        return {"type": "noop"}


# 무작위로 이동만 하는 정책. 실제 AI 붙이기 전 environment 동작 확인용
class RandomPolicy(Policy):
    def __init__(self, step_size: float = 5.0) -> None:
        self.step_size = step_size

    def decide(self, observation: dict) -> dict:
        dx = random.uniform(-self.step_size, self.step_size)
        dy = random.uniform(-self.step_size, self.step_size)
        return {"type": "move", "dx": dx, "dy": dy}


# 관찰(observation)만 보고 실제로 도구를 쓰는 규칙 기반 정책.
# 우선순위: 문 열 열쇠가 인벤토리에 있으면 사용 -> 문 여는 버튼/레버가 범위 안이면 사용
# -> 시야의 열쇠가 범위 안이면 습득 -> 가장 가까운 목표(열쇠>버튼>레버>문)로 이동 -> 할 게 없으면 배회.
# 실제 AI를 붙이기 전, environment 전체(문/열쇠/버튼/레버/압력판)가 잘 맞물려 도는지
# 확인하는 테스트베드 용도.
class ToolUsePolicy(Policy):
    def __init__(self, interact_radius: float = 15.0, step_size: float = 5.0) -> None:
        self.interact_radius = interact_radius
        self.step_size = step_size

    def decide(self, observation: dict) -> dict:
        self_state = observation["self"]
        x, y = self_state["x"], self_state["y"]
        inventory = self_state.get("inventory", [])
        objects = observation["visible_objects"]

        doors = [o for o in objects if o["type"] == "door"]
        keys = [o for o in objects if o["type"] == "key"]
        buttons = [o for o in objects if o["type"] == "button"]
        levers = [o for o in objects if o["type"] == "lever"]

        # 1) 인벤토리에 맞는 열쇠가 있고 대상 문이 상호작용 범위 안이면 사용
        # (문은 반경(radius)이 있는 물체라 중심이 아니라 가장자리 기준으로 재야 함 -
        # Environment.use_key와 동일한 기준. 안 그러면 door.radius >= interact_radius일 때
        # 물리적으로 절대 도달 못 하는 문턱이 생김 - enviroment.py의 use_key 참고)
        for item in inventory:
            if item.get("type") != "key":
                continue
            door = next((d for d in doors if d["object_id"] == item["unlocks"] and d["locked"]), None)
            if door is not None:
                reach = self.interact_radius + door.get("radius", 0.0)
                if self._distance(x, y, door) <= reach:
                    return {"type": "use_key", "key_id": item["object_id"]}

        # 2) 잠긴 문에 연결된 버튼/레버가 상호작용 범위 안이면 사용
        for button in buttons:
            door = next((d for d in doors if d["object_id"] == button.get("linked_door_id") and d["locked"]), None)
            if door is not None and self._distance(x, y, button) <= self.interact_radius:
                return {"type": "press_button", "button_id": button["object_id"]}

        for lever in levers:
            linked_ids = lever.get("linked_door_ids", [])
            if any(d["locked"] for d in doors if d["object_id"] in linked_ids):
                if self._distance(x, y, lever) <= self.interact_radius:
                    return {"type": "pull_lever", "lever_id": lever["object_id"]}

        # 3) 시야의 열쇠가 상호작용 범위 안이면 습득
        nearest_key = self._nearest(x, y, keys)
        if nearest_key is not None and self._distance(x, y, nearest_key) <= self.interact_radius:
            return {"type": "pick_up", "object_id": nearest_key["object_id"]}

        # 4) 목표(열쇠 > 버튼 > 레버 > 문)로 이동
        target = nearest_key or self._nearest(x, y, buttons) or self._nearest(x, y, levers) or self._nearest(x, y, doors)
        if target is not None:
            return self._move_toward(x, y, target)

        # 5) 할 일이 없으면 무작위 배회
        dx = random.uniform(-self.step_size, self.step_size)
        dy = random.uniform(-self.step_size, self.step_size)
        return {"type": "move", "dx": dx, "dy": dy}

    def _distance(self, x: float, y: float, obj: dict) -> float:
        return math.hypot(obj["x"] - x, obj["y"] - y)

    def _nearest(self, x: float, y: float, objs: list) -> dict | None:
        if not objs:
            return None
        return min(objs, key=lambda o: self._distance(x, y, o))

    # Stop just outside interact_radius instead of walking onto the target,
    # since a door also has its own blocking radius that can be larger and
    # would otherwise wedge the agent against it (move blocked -> same move
    # recomputed next step -> stuck forever).
    def _move_toward(self, x: float, y: float, obj: dict) -> dict:
        dx, dy = obj["x"] - x, obj["y"] - y
        distance = math.hypot(dx, dy)

        stop_distance = self.interact_radius
        if obj["type"] == "door":
            stop_distance = max(stop_distance, obj.get("radius", 0.0) + 1.0)

        if distance <= stop_distance:
            return {"type": "noop"}

        travel = min(self.step_size, distance - stop_distance)
        scale = travel / distance
        return {"type": "move", "dx": dx * scale, "dy": dy * scale}


# openai 파이썬 SDK로 로컬/오픈소스 tiny 모델을 호출하는 정책.
# Ollama/vLLM/LM Studio처럼 OpenAI 호환 API를 제공하는 서버를 base_url로 지정하면 됨
# (OpenAI의 실제 클라우드 API도 model/api_key만 맞으면 그대로 사용 가능).
# tools.TOOLS를 function-calling 스키마로 넘기고, 모델이 고른 tool_call을 그대로
# action(dict)으로 변환한다. tiny 모델은 tool_call을 안 하거나 잘못된 인자를 줄 수
# 있으므로, 그런 경우 noop으로 대체해 시뮬레이션이 멈추지 않게 한다.
class LLMPolicy(Policy):
    def __init__(
        self,
        model: str,
        base_url: str | None = None,
        api_key: str = "not-needed",
        system_prompt: str = (
            "You are an agent in a multi-agent collaboration experiment. "
            "Given the observation, call exactly one tool to decide your next action."
        ),
        temperature: float = 0.2,
        max_tokens: int = 2000,
        extra_params: dict | None = None
    ) -> None:
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = model
        self.system_prompt = system_prompt
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.extra_params = extra_params or {}  # 프로바이더 전용 옵션 (예: gpt-oss의 reasoning_effort)
        self.last_error = None  # 가장 최근 decide() 호출에서 발생한 예외/사유 (없으면 None)

    def decide(self, observation: dict) -> dict:
        try:
            history = self.conversation_history
            if not history:
                history.append({'role': 'system', 'content': self.system_prompt})
            history.append({'role': 'user', 'content': json.dumps(observation, ensure_ascii=False)})
            response = _create_with_retry(
                self.client,
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                messages=copy.deepcopy(history),
                tools=TOOLS,
                tool_choice="required",
                **self.extra_params
            )
            message = response.choices[0].message
            history.append({'role': 'assistant', 'content': json.dumps(
                {'content': message.content, 'tool_calls': [
                    {'name': call.function.name, 'arguments': call.function.arguments}
                    for call in (message.tool_calls or [])]}, ensure_ascii=False)})
            if response.choices[0].finish_reason == "length":
                self.last_error = (
                    "LLM response was cut off before finishing (finish_reason='length'); "
                    "the tool call may be incomplete/unparseable."
                )
                return {"type": "noop"}

            tool_calls = response.choices[0].message.tool_calls
            if not tool_calls:
                self.last_error = "model did not call any tool (replied with plain text instead)"
                return {"type": "noop"}

            call = tool_calls[0]
            action = json.loads(call.function.arguments) if call.function.arguments else {}
            action["type"] = call.function.name
            self.last_error = None
            return action
        except Exception:
            self.last_error = traceback.format_exc()
            return {"type": "noop"}


# "Code as Policies" (Liang et al., 2023) 스타일 정책.
# LLMPolicy는 매 스텝 tool_call을 하나씩 받아오지만, CodePolicy는 LLM에게
# observation -> action(dict)을 계산하는 decide() 함수의 "코드"를 한 번만 쓰게 하고,
# 이후에는 매 스텝 그 코드를 그대로 실행해 재사용한다 (반응형 컨트롤러처럼 동작).
# 생성된 코드는 환경을 직접 조작하지 않고 action(dict)만 반환하는 순수 함수여야
# 하며(그래야 Rule 강제 시스템을 우회할 수 없음), 논문 III절과 동일하게 import/
# exec/eval/__로 시작하는 이름 사용을 금지해 안전하게 실행한다.
#
# 코드 생성과 코드 실행 둘 다 이중으로 강제된다:
#   1) 생성 단계 - submit_policy_code tool-call 게이트. 모델은 텍스트로 답을 끝낼 수
#      없고 반드시 이 tool을 호출해야 하며, 코드가 compile+안전성 검사를 통과해야만
#      "accepted"로 응답받는다. 실패하면 그 에러가 tool 결과로 그대로 돌아가 같은 턴
#      안에서(MAX_TOOL_ROUNDS까지) 다시 시도할 수 있다 - 잘못된 코드를 그냥 버리고
#      noop으로 넘어가는 대신, 모델 스스로 고칠 기회를 준다. tool-calling을 지원하지
#      않는 프로바이더에서는 자동으로 예전 방식(평문 + 코드펜스 추출)으로 대체된다.
#   2) 실행 단계 - policy_sandbox.run_decide_code()가 매 decide() 호출마다 코드를
#      격리된 `python -I -S` 서브프로세스에서 실행하고 하드 타임아웃을 건다. 생성
#      단계의 검사를 우회하는 경로(예: 재생성 없이 재사용되는 캐시된 코드)가 있어도,
#      무한루프나 크래시가 시뮬레이션 프로세스 자체는 절대 멈추지 못하게 하는
#      OS 수준의 두 번째 방어선 - 자세한 내용은 policy_sandbox.py, _policy_harness.py
#      참고.

def _action_schema_docs() -> str:
    lines = []
    for tool in TOOLS:
        fn = tool["function"]
        params = ", ".join(fn["parameters"].get("properties", {}).keys())
        lines.append(f'- {{"type": "{fn["name"]}", {params}}} : {fn["description"]}')
    return "\n".join(lines)


# CodePolicy/LiveCodePolicy 프롬프트에 들어가는 observation 형식 설명 (Environment.get_observation과 맞춰야 함)
_OBSERVATION_DOC = """{"self": {"x", "y", "facing", "inventory": [...], "step", "map_width", "map_height"},
 "visible_objects": [...], "known_objects": {object_id: {..., "last_seen_step"}},
 "walls": [[x, y, width, height], ...], "memory": {...}, "inbox": [...]}
- Every object has "object_id", "type", "x", "y" plus type-specific fields (door: "locked"; key: "unlocks";
  button: "linked_door_id"; lever: "on", "linked_door_ids"; pressure_plate: "linked_door_id", "radius";
  item: "category" ("normal" or "coop"); portal: "dest_x", "dest_y"; clue: "content";
  number_pad: "number", "room", "touch_radius"; display: "room", "last_press", "resets").
- number_pad activates automatically when you enter its touch_radius, including crossing it during a move.
  No press_button is needed. Staying inside does not repeat; leave and re-enter for another input.
- In sequence_rooms, clue.content has total_presses and your_presses [{order, number}].
  display.last_press is null or {pad_id, number, step, result: accepted or wrong_reset}.
  The display gives no global progress; coordinate the shared order using messages.
- visible_objects: what you see right now (view cone around "facing"; walls block sight).
- known_objects: last seen state of everything you have ever seen (it may be outdated).
- walls: walls near you. Walls block movement - a move stops right before a wall.
- facing is in degrees: 0 = +x (right), 90 = +y (down), 180 = left, 270 = up. Moving turns you toward the move.
- inbox: every message ever delivered to you (oldest first); each has "step" (when it arrived) and "from".
- memory: your own notes. Add a "memory": {...} key to any returned action to replace it for the next step
  (your code runs fresh every step, so this is the only way to remember plans or explored places).
- Interactions (pick_up, use_key, press_button, pull_lever) only work within about 15 units."""


POLICY_LAYOUT = Path(__file__).with_name('policy_template.py').read_text(encoding='utf-8')
# Strip the module description: models receive the actual executable function layout.
POLICY_LAYOUT = POLICY_LAYOUT[POLICY_LAYOUT.index('def decide(observation):'):]
POLICY_LAYOUT_INSTRUCTIONS = """Use the supplied action-function layout below.
Keep sections 1 and 2 (observation setup and helpers) unchanged. Fill the DECISION START/END
region with your task-specific logic and any additional local helper functions.
Return the COMPLETE decide(observation) function, including the supplied sections.
Use finish(), move_toward(), or send_message() for all action returns so memory is saved.
move_toward() is a direct movement helper, NOT a path planner: choose waypoints using walls;
avoid accidentally touching other number pads. Target coordinates may come from the task,
memory or known objects even when a target is outside the current view.
Find objects by object_id. Other agents are absent from objects; use their IDs from the task
when sending messages. Follow the task's interaction rules and check inbox/reset state.

Base action-function layout:
```python
""" + POLICY_LAYOUT + "\n```"

CODE_POLICY_SYSTEM_PROMPT = f"""Complete the provided Python action-function layout for an agent in a multi-agent simulation.

decide() is called once per simulation step with an observation dict shaped like:
{_OBSERVATION_DOC}

It must RETURN an action dict (never call environment methods directly). Valid action \
shapes (the "type" field is required):
{_action_schema_docs()}

Rules:
- No import statements, no exec/eval/open, no names starting with __.
- The `math` module is already available as `math` (no import needed).
- Only output one fenced ```python code block containing the decide() function, nothing else.

{POLICY_LAYOUT_INSTRUCTIONS}"""

def _extract_code(text: str) -> str:
    if "```" not in text:
        return text.strip()
    fenced = text.split("```")[1]
    lines = fenced.split("\n", 1)
    if len(lines) > 1 and lines[0].strip().isalpha():  # 언어 태그(python/json 등) 줄이면 제거
        fenced = lines[1]
    return fenced.strip()


def _safety_check_error(code: str, checks=None) -> str | None:
    """Compile+safety-check `code` without running it (used by the
    submit_policy_code gate below). Returns None if it's fine to accept, or
    a short error string to hand back to the model as a tool result."""
    error = compile_policy_code(code, checks, context='submission')
    if error:
        return error
    try:
        _check_code_safety(code)  # ast.parse() inside raises SyntaxError on bad syntax too
        return None
    except (SyntaxError, ValueError) as e:
        return f"{type(e).__name__}: {e}"


MAX_TOOL_ROUNDS = 4

SUBMIT_POLICY_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "submit_policy_code",
        "description": (
            "Submit your final decide() policy code. This is the ONLY way to answer - "
            "plain text is ignored. The code is checked for valid, safe Python before "
            "being accepted: if it fails, you get the error back and must call this "
            "again with a fix (nothing is run for real until it is accepted)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "The final Python code defining decide(observation)."},
            },
            "required": ["code"],
        },
    },
}


def _generate_code_with_submission_gate(
    client,
    model: str,
    system_prompt: str,
    user_content: str,
    temperature: float,
    max_tokens: int,
    extra_params: dict,
    checks=None,
    history=None,
) -> str:
    """Drives the submit_policy_code tool-call loop: the model must call the
    tool to answer, and its code is compile+safety-checked before being
    accepted - a failure comes back as a tool result (not spent as a wasted
    generation) and the model gets up to MAX_TOOL_ROUNDS attempts to fix it,
    within the SAME call to this function (no extra LLM calls from the
    caller's side). Falls back to the old plain one-shot text + code-fence
    extraction path (no tool calling at all) if the provider never returns a
    tool call, or outright rejects the tools/tool_choice parameters (some
    OpenRouter free models don't support function-calling reliably)."""
    messages = history if history is not None else []
    if not messages:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_content})

    try:
        for _round in range(MAX_TOOL_ROUNDS):
            response = _create_with_retry(
                client,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                messages=copy.deepcopy(messages),
                tools=[SUBMIT_POLICY_TOOL_SCHEMA],
                tool_choice="required",
                **extra_params,
            )
            choice = response.choices[0]
            if choice.finish_reason == "length":
                messages.append({'role': 'assistant', 'content': choice.message.content or '(response truncated)'})
                raise ValueError(
                    "LLM response was cut off before finishing (finish_reason='length'); "
                    "the generated code may be incomplete. Increase max_tokens."
                )

            tool_calls = choice.message.tool_calls or []
            if not tool_calls:
                # Some models answer in plain text despite tool_choice="required" -
                # nudge them back instead of silently accepting untrusted text.
                messages.append({"role": "assistant", "content": choice.message.content})
                messages.append({"role": "user", "content": (
                    "That was plain text, which is ignored - you must call the "
                    "submit_policy_code tool with your final code to answer."
                )})
                continue

            messages.append({
                "role": "assistant",
                "content": choice.message.content,
                "tool_calls": [
                    {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in tool_calls
                ],
            })

            accepted_code = None
            for tc in tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except Exception:
                    args = {}
                code = _extract_code(str(args.get("code", "")))
                error = _safety_check_error(code, checks)
                if error is None:
                    result = {"accepted": True}
                    accepted_code = accepted_code if accepted_code is not None else code
                else:
                    result = {"accepted": False, "error": f"NOT accepted - {error}. Fix it and call submit_policy_code again."}
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result)})

            if accepted_code is not None:
                return accepted_code
        # Exhausted MAX_TOOL_ROUNDS without an accepted submission - fall through.
    except Exception:
        pass  # provider rejected tools/tool_choice outright - fall back below

    response = _create_with_retry(
        client,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        messages=_text_history(messages),
        **extra_params,
    )
    messages.append({'role': 'assistant', 'content': response.choices[0].message.content or ''})
    if response.choices[0].finish_reason == "length":
        raise ValueError(
            "LLM response was cut off before finishing (finish_reason='length'); "
            "the generated code is incomplete. Increase max_tokens or shorten "
            "the system/task prompt."
        )
    code = _extract_code(response.choices[0].message.content)
    error = _safety_check_error(code, checks)
    if error:
        messages.append({'role': 'user', 'content': 'Code validation failed: ' + error})
        raise ValueError(error)
    return code


def _text_history(messages):
    """Retain prior tool exchanges as text for providers without tool support."""
    result = []
    for message in messages:
        if message['role'] == 'tool':
            result.append({'role': 'user', 'content': 'Code validation result: ' + message['content']})
        elif message.get('tool_calls'):
            result.append({'role': 'assistant', 'content': (message.get('content') or '') + '\n' +
                           json.dumps(message['tool_calls'], ensure_ascii=False)})
        else:
            result.append(copy.deepcopy(message))
    return result


# 캐시된 코드가 막혔을 때 LLM에게 다시 짜게 하는(재생성) 조건:
#   즉시 (stuck) - decide() 실행 오류(예외/타임아웃/잘못된 action), 또는 move를 했는데 위치가
#                  그대로(벽/잠긴 문/coop 운반에 막힘). 코드는 같은 관찰에 같은 행동을 내므로
#                  그대로 두면 같은 자리에서 영원히 반복됨
#   누적 (정지) - stall_limit step 연속으로 위치가 그대로 (noop/turn만 반복 등). 단 압력판 위에서
#                  기다리는 것은 의도된 대기이므로 제외
# 재생성 때는 이유/이전 코드/현재 관찰을 함께 보여줌. 비용 폭주를 막기 위해 회차당 max_replans회까지
CODE_REPLAN_PROMPT = """{task}

Your previous decide() code got stuck at step {step}: {reason}
Previous code:
```python
{code}
```

Current observation:
{observation}

Fill the supplied base layout's decision region to fix this failure and continue the task.
Keep the observation setup and action helpers from the system prompt, and return the complete decide()."""


class CodePolicy(Policy):
    def __init__(
        self,
        model: str,
        task_description: str,
        base_url: str | None = None,
        api_key: str = "not-needed",
        temperature: float = 0.0,
        max_tokens: int = 4000,
        extra_params: dict | None = None,
        sandbox_timeout: float = 5.0,
        stall_limit: int = 3,
        max_replans: int = 10
    ) -> None:
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = model
        self.task_description = task_description
        self.temperature = temperature
        self.max_tokens = max_tokens        # 응답이 코드 완성 전에 잘리는 것을 막기 위한 여유값
        self.extra_params = extra_params or {}  # 프로바이더 전용 옵션 (예: gpt-oss의 reasoning_effort)
        self.sandbox_timeout = sandbox_timeout  # decide() 서브프로세스 실행 하드 타임아웃 (초)
        self.generated_code = None   # LLM이 제출/수락한 코드 원문 (처음 생성 후 재사용, stuck이면 재생성)
        self.last_error = None       # 가장 최근 decide() 호출에서 발생한 예외 (없으면 None)
        self.stall_limit = stall_limit    # 위치가 이만큼 연속으로 그대로면 재생성
        self.max_replans = max_replans    # 일반 정체 재계획 최대 횟수 (실행 오류 복구는 별도)
        self.replans: list[dict] = []     # 재생성 기록 [{"step", "reason"}]
        self.last_replan = None           # 이번 decide() 호출에서 재생성했으면 그 기록 (manifest용)
        self._last_pos = None             # 직전 관찰의 위치
        self._last_action = None          # 직전에 반환한 action
        self._stall_count = 0             # 위치가 연속으로 그대로였던 step 수
        self._repair_results = queue.Queue()
        self._repair_thread = None
        self._repair_wait = 0
        self._repair_attempts = 0
        self._execution_error = None
        self.last_recovery = None

    # 다음 decide() 호출에서 정책 코드를 새로 생성하도록 캐시를 비움
    def reset(self) -> None:
        self._conversation_history = []
        self.generated_code = None
        self.last_error = None
        self.replans = []
        self.last_replan = None
        self._last_pos = None
        self._last_action = None
        self._stall_count = 0
        self._repair_results = queue.Queue()
        self._repair_thread = None
        self._repair_wait = 0
        self._repair_attempts = 0
        self._execution_error = None
        self.last_recovery = None

    def _start_repair(self, observation):
        """Generate a replacement off the simulation thread; only one request at a time."""
        if self._repair_thread is not None:
            return
        self._repair_attempts += 1
        reason = f"decide() failed: {self._execution_error}"
        prompt = CODE_REPLAN_PROMPT.format(
            task=self.task_description, step=observation["self"].get("step"), reason=reason,
            code=self.generated_code, observation=json.dumps(copy.deepcopy(observation), ensure_ascii=False))
        self.last_replan = {"step": observation["self"].get("step"), "reason": reason,
                            "kind": "execution_repair"}
        self.replans.append(self.last_replan)
        results = self._repair_results

        def repair():
            try:
                results.put((self._generate_code(prompt), None))
            except Exception:
                results.put((None, traceback.format_exc()))

        self._repair_thread = threading.Thread(target=repair, daemon=True)
        self._repair_thread.start()

    def _recover(self, observation):
        if self._repair_thread is not None:
            try:
                code, error = self._repair_results.get_nowait()
            except queue.Empty:
                code, error = None, None
            else:
                self._repair_thread = None
                if code is not None:
                    self.generated_code = code
                    # A repair must execute successfully against the *current* observation.
                    result = run_decide_code(code, observation, timeout=self.sandbox_timeout, checks=self.code_checks)
                    if not result.get("error"):
                        self._execution_error = None
                        self.last_error = None
                        self._stall_count = 0
                        self.last_recovery = {"status": "recovered", "attempts": self._repair_attempts}
                        return result["action"]
                    error = result["error"]
                self._execution_error = error
                self._repair_wait = 3
        if self._repair_thread is None:
            if self._repair_wait:
                self._repair_wait -= 1
            else:
                # Runtime repair retries are not stopped by the normal stall replan budget.
                self._start_repair(observation)
        self.last_error = self._execution_error
        self.last_recovery = {"status": "regenerating" if self._repair_thread else "retry_wait",
                              "attempts": self._repair_attempts, "waiting": True}
        return {"type": "noop"}

    def _wait_for_recovery(self, observation):
        self._debug('recovery_wait_started', step=observation['self'].get('step'), error=self._execution_error)
        print(f"[CODE RECOVERY] step {observation['self'].get('step')}: waiting for working code", flush=True)
        while True:
            try:
                action = self._recover(observation)
                if self._execution_error is None:
                    self._debug('recovery_succeeded', step=observation['self'].get('step'), attempts=self._repair_attempts)
                    print(f"[CODE RECOVERY] recovered after {self._repair_attempts} attempt(s)", flush=True)
                    return action
            except Exception:
                self._execution_error = traceback.format_exc()
                self.last_error = self._execution_error
                self._repair_wait = 3
            # No action is applied and no additional simulation step is consumed here.
            time.sleep(1.0)

    def _generate_code(self, user_content: str = None) -> str:
        return self._generate_tracked(
            self.client,
            self.model,
            CODE_POLICY_SYSTEM_PROMPT,
            user_content or self.task_description,
            self.temperature,
            self.max_tokens,
            self.extra_params,
            checks=self.code_checks,
        )

    # 이번 관찰로 정지 횟수를 갱신하고, 재생성할 이유가 있으면 그 설명을 반환 (없으면 None)
    def _stuck_reason(self, observation: dict) -> str | None:
        me = observation["self"]
        pos = (me["x"], me["y"])
        if self._last_pos is None:
            return None
        if pos != self._last_pos:
            self._stall_count = 0
            return None
        self._stall_count += 1

        last = self._last_action or {}
        if last.get("type") == "move" and (last.get("dx") or last.get("dy")):
            return f"your last move {last} was blocked - your position {pos} did not change"
        if self._stall_count >= self.stall_limit and not self._on_pressure_plate(observation, pos):
            return f"you have not moved from {pos} for {self._stall_count} steps in a row"
        return None

    @staticmethod
    def _on_pressure_plate(observation: dict, pos) -> bool:
        return any(
            obj.get("type") == "pressure_plate"
            and math.hypot(obj["x"] - pos[0], obj["y"] - pos[1]) <= obj.get("radius", 0.0)
            for obj in observation.get("known_objects", {}).values()
        )

    # 이유와 함께 코드를 새로 생성. max_replans를 다 썼으면 기존 코드를 유지하고 False
    def _replan(self, observation: dict, reason: str) -> bool:
        if sum(r.get("kind") != "execution_repair" for r in self.replans) >= self.max_replans:
            return False
        step = observation["self"].get("step")
        self.generated_code = self._generate_code(CODE_REPLAN_PROMPT.format(
            task=self.task_description,
            step=step,
            reason=reason,
            code=self.generated_code,
            observation=json.dumps(observation, ensure_ascii=False),
        ))
        self.last_replan = {"step": step, "reason": reason}
        self.replans.append(self.last_replan)
        self._stall_count = 0
        return True

    def decide(self, observation: dict) -> dict:
        self.last_replan = None
        self.last_recovery = None
        action = {"type": "noop"}
        try:
            if self._execution_error is not None:
                action = self._wait_for_recovery(observation)
            elif self.generated_code is None:
                self.generated_code = self._generate_code()
            else:
                reason = self._stuck_reason(observation)
                if reason is not None:
                    self._replan(observation, reason)

            if self.last_recovery is None:
                result = run_decide_code(self.generated_code, observation, timeout=self.sandbox_timeout, checks=self.code_checks)
                if result.get("error"):
                    self._execution_error = result["error"]
                    action = self._wait_for_recovery(observation)
                else:
                    self.last_error = None
                    action = result["action"]
        except Exception:
            self.last_error = traceback.format_exc()
            self._execution_error = self.last_error
            action = self._wait_for_recovery(observation)
        self._last_pos = (observation["self"]["x"], observation["self"]["y"])
        self._last_action = action
        return action


# CodePolicy는 코드를 처음 한 번만 생성해 재사용하므로, 생성 이후 들어오는 메시지에
# 맞춰 판단 로직 자체를 바꾸지 못한다 (고정된 반응형 컨트롤러). LiveCodePolicy는 반대로
# 매 decide() 호출마다 그 시점의 observation(및 inbox 메시지)을 LLM에게 보여주고 코드를
# 새로 쓰게 해서, 매 스텝 "대화하며" 판단을 바꿀 수 있게 한다. 대신 스텝마다 LLM 호출이
# 발생하므로 LLMPolicy와 비슷한 속도/비용 특성을 가진다.
CODE_STEP_SYSTEM_PROMPT = f"""Complete the supplied action-function layout for ONE agent's decision at a single simulation step.

You will be called again on the very next step with a FRESH observation (including any \
new inbox messages from other agents), so only decide the single best next action for \
right now — you do not need to plan the whole task inside this one function, and you may \
change your approach completely on the next call based on what you see then.

observation is shaped like:
{_OBSERVATION_DOC}

It must RETURN an action dict (never call environment methods directly). Valid action \
shapes (the "type" field is required):
{_action_schema_docs()}

Rules:
- No import statements, no exec/eval/open, no names starting with __.
- The `math` module is already available as `math` (no import needed).
- Only output one fenced ```python code block containing the decide() function, nothing else.

{POLICY_LAYOUT_INSTRUCTIONS}"""


class LiveCodePolicy(Policy):
    def __init__(
        self,
        model: str,
        task_description: str,
        base_url: str | None = None,
        api_key: str = "not-needed",
        temperature: float = 0.2,
        max_tokens: int = 1500,
        extra_params: dict | None = None,
        sandbox_timeout: float = 5.0
    ) -> None:
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = model
        self.task_description = task_description
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.extra_params = extra_params or {}  # 프로바이더 전용 옵션 (예: gpt-oss의 reasoning_effort)
        self.sandbox_timeout = sandbox_timeout  # decide() 서브프로세스 실행 하드 타임아웃 (초)
        self.generated_code = None   # 가장 최근 스텝에서 제출/수락된 코드 원문 (표시/디버깅용)
        self.last_error = None       # 가장 최근 decide() 호출에서 발생한 예외 (없으면 None)

    def _generate_code(self, observation: dict) -> str:
        return self._generate_tracked(
            self.client,
            self.model,
            CODE_STEP_SYSTEM_PROMPT,
            f"Task: {self.task_description}\n\nCurrent observation:\n{json.dumps(observation, ensure_ascii=False)}",
            self.temperature,
            self.max_tokens,
            self.extra_params,
            checks=self.code_checks,
        )

    def decide(self, observation: dict) -> dict:
        try:
            code = self._generate_code(observation)
            self.generated_code = code  # 실행 실패해도 원문은 남김

            result = run_decide_code(code, observation, timeout=self.sandbox_timeout, checks=self.code_checks)
            if result.get("error"):
                self.last_error = result["error"]
                return {"type": "noop"}

            self.last_error = None
            return result["action"]
        except Exception:
            self.last_error = traceback.format_exc()
            return {"type": "noop"}


# LiveCodePolicy는 매 스텝 코드를 새로 짜므로 상황이 단순할 때도 매번 LLM을 호출해야 해서
# 비효율적이고, CodePolicy는 반대로 한 번 짠 코드를 계속 재사용해서 상황이 바뀌어도
# 대응을 못 한다. HybridPolicy는 그 중간: 평소엔 캐시된 코드를 그대로 실행해 LLM을
# 안 부르다가, 그 코드 스스로 "이 상황은 내가 못 처리해" 신호({"type": "replan"})를
# 반환할 때만 LLM을 다시 불러 새로 판단하게 한다. 또한 LLM이 매번 코드를 쓸 필요도 없이
# 그 자리에서 바로 끝나는 단순한 행동이면 코드 없이 action(JSON) 하나만 답해도 됨 -
# "코드"는 복잡한 행동(추적/회피/다단계 조건)이 필요할 때만 쓰는 도구가 된다.
# OpenAI의 tools(function-calling) API는 전혀 안 쓰고 텍스트만 파싱하므로, tool-calling을
# 지원 안 하는 모델(OpenRouter 무료 모델 등)에서도 동작한다.
def _hybrid_policy_system_prompt() -> str:
    return f"""You control one agent in a multi-agent simulation. Each time you are asked, \
respond in ONE of two ways:

1) Simple action (use this for most steps): if the right next action is obvious and \
doesn't need ongoing tracking or multi-step logic, reply with a single JSON action object \
and nothing else, e.g. {{"type": "move", "dx": 5, "dy": 0}}. This action is used for THIS \
step only - you will be asked again next step with a fresh observation.

2) Reusable code (use this ONLY when the situation is genuinely complex - e.g. tracking or \
intercepting a moving target, navigating around several obstacles, evaluating many \
candidates, multi-step conditional planning): reply with a single fenced ```python code \
block defining:

def decide(observation):
    ...
    return action

This function will be CACHED and reused every subsequent step WITHOUT calling you again, \
until it itself returns {{"type": "replan"}} - call for that from inside the code whenever \
the situation no longer matches what the code was written for (e.g. task done, unexpected \
obstacle, needs a new plan). When that happens you will be asked again with the current \
observation.

Valid action shapes (the "type" field is required):
{_action_schema_docs()}
Plus the special {{"type": "replan"}} action, only meaningful when returned FROM INSIDE \
generated code (never as your direct top-level reply).

Rules for code:
- No import statements, no exec/eval/open, no names starting with __.
- The `math` module is already available as `math` (no import needed).

Reply with EITHER one JSON object OR one ```python code block. Nothing else, no explanation."""


HYBRID_POLICY_SYSTEM_PROMPT = _hybrid_policy_system_prompt() + "\n\nWhen choosing reusable code:\n" + POLICY_LAYOUT_INSTRUCTIONS


class HybridPolicy(Policy):
    def __init__(
        self,
        model: str,
        task_description: str,
        base_url: str | None = None,
        api_key: str = "not-needed",
        temperature: float = 0.2,
        max_tokens: int = 1500,
        extra_params: dict | None = None,
        sandbox_timeout: float = 5.0
    ) -> None:
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = model
        self.task_description = task_description
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.extra_params = extra_params or {}  # 프로바이더 전용 옵션 (예: gpt-oss의 reasoning_effort)
        self.sandbox_timeout = sandbox_timeout  # 코드 모드 decide() 서브프로세스 실행 하드 타임아웃 (초)
        self.generated_code = None   # 현재 캐시된 코드 원문. None이면 코드 모드가 아니라 매 스텝 LLM에게 새로 물어봄
        self.last_error = None       # 가장 최근 decide() 호출에서 발생한 예외/사유 (없으면 None)

    def _ask_llm(self, observation: dict) -> str:
        history = self.conversation_history
        if not history:
            history.append({'role': 'system', 'content': HYBRID_POLICY_SYSTEM_PROMPT})
        history.append({'role': 'user', 'content': f'Task: {self.task_description}\n\nCurrent observation:\n' +
                        json.dumps(observation, ensure_ascii=False)})
        response = _create_with_retry(
            self.client,
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            messages=copy.deepcopy(history),
            **self.extra_params
        )
        history.append({'role': 'assistant', 'content': response.choices[0].message.content or ''})
        if response.choices[0].finish_reason == "length":
            raise ValueError(
                "LLM response was cut off before finishing (finish_reason='length'); "
                "the reply is incomplete. Increase max_tokens or shorten "
                "task_description / HYBRID_POLICY_SYSTEM_PROMPT."
            )
        return response.choices[0].message.content

    def decide(self, observation: dict) -> dict:
        try:
            if self.generated_code is not None:
                result = run_decide_code(self.generated_code, observation, timeout=self.sandbox_timeout, checks=self.code_checks)
                if result.get("error"):
                    self.last_error = f"cached decide() failed: {result['error']}"
                    self.generated_code = None
                    return {"type": "noop"}
                action = result["action"]
                if action["type"] != "replan":
                    self.last_error = None
                    return action
                # 코드가 스스로 재계획을 요청함: 캐시를 비우고 이번 호출 안에서 바로
                # LLM에게 다시 물어봄 (한 스텝을 그냥 버리지 않기 위해)
                self.generated_code = None

            reply = self._ask_llm(observation)
            stripped = _extract_code(reply)

            if "def decide(" in stripped:
                safety_error = _safety_check_error(stripped, self.code_checks)
                if safety_error is not None:
                    self.last_error = f"generated code rejected: {safety_error}"
                    return {"type": "noop"}

                result = run_decide_code(stripped, observation, timeout=self.sandbox_timeout, checks=self.code_checks)
                action = result.get("action")
                if result.get("error") or not isinstance(action, dict) or "type" not in action or action["type"] == "replan":
                    self.last_error = f"generated decide()'s first action was invalid: {result.get('error') or action!r}"
                    return {"type": "noop"}
                self.generated_code = stripped
                self.last_error = None
                return action

            self.generated_code = None
            action = json.loads(stripped)
            if not isinstance(action, dict) or "type" not in action:
                self.last_error = f"LLM returned invalid direct action: {action!r}"
                return {"type": "noop"}
            self.last_error = None
            return action
        except Exception:
            self.last_error = traceback.format_exc()
            self.generated_code = None
            return {"type": "noop"}
