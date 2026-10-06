import ast
import json
import math
import random
import time
import traceback

from openai import OpenAI, RateLimitError

from policy_sandbox import run_decide_code
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
            response = _create_with_retry(
                self.client,
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": json.dumps(observation, ensure_ascii=False)}
                ],
                tools=TOOLS,
                tool_choice="required",
                **self.extra_params
            )
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
  item: "category" ("normal" or "coop"); portal: "dest_x", "dest_y"; clue: "content").
- visible_objects: what you see right now (view cone around "facing"; walls block sight).
- known_objects: last seen state of everything you have ever seen (it may be outdated).
- walls: walls near you. Walls block movement - a move stops right before a wall.
- facing is in degrees: 0 = +x (right), 90 = +y (down), 180 = left, 270 = up. Moving turns you toward the move.
- memory: your own notes. Add a "memory": {...} key to any returned action to replace it for the next step
  (your code runs fresh every step, so this is the only way to remember plans or explored places).
- Interactions (pick_up, use_key, press_button, pull_lever) only work within about 15 units."""


CODE_POLICY_SYSTEM_PROMPT = f"""You write Python policy code for an agent in a multi-agent \
simulation. Define exactly one function:

def decide(observation):
    ...
    return action

decide() is called once per simulation step with an observation dict shaped like:
{_OBSERVATION_DOC}

It must RETURN an action dict (never call environment methods directly). Valid action \
shapes (the "type" field is required):
{_action_schema_docs()}

Rules:
- No import statements, no exec/eval/open, no names starting with __.
- The `math` module is already available as `math` (no import needed).
- Only output one fenced ```python code block containing the decide() function, nothing else.

Example:
```python
def decide(observation):
    x = observation["self"]["x"]
    y = observation["self"]["y"]
    dx = -5 if x > 0 else 5
    dy = -5 if y > 0 else 5
    return {{"type": "move", "dx": dx, "dy": dy}}
```"""

_FORBIDDEN_CALL_NAMES = {"exec", "eval", "open", "__import__", "compile", "input"}


def _check_code_safety(code: str) -> None:
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise ValueError("generated code may not use import statements")
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            raise ValueError("generated code may not reference dunder names")
        # Blocks attribute-access escapes too (e.g. ({}).__class__.__bases__),
        # not just bare dunder names (e.g. __builtins__) - a bare-name-only
        # check would let object-introspection chains slip through unnoticed.
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise ValueError("generated code may not reference dunder attributes")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in _FORBIDDEN_CALL_NAMES:
                raise ValueError(f"generated code may not call {node.func.id}()")


def _extract_code(text: str) -> str:
    if "```" not in text:
        return text.strip()
    fenced = text.split("```")[1]
    lines = fenced.split("\n", 1)
    if len(lines) > 1 and lines[0].strip().isalpha():  # 언어 태그(python/json 등) 줄이면 제거
        fenced = lines[1]
    return fenced.strip()


def _safety_check_error(code: str) -> str | None:
    """Compile+safety-check `code` without running it (used by the
    submit_policy_code gate below). Returns None if it's fine to accept, or
    a short error string to hand back to the model as a tool result."""
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
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    try:
        for _round in range(MAX_TOOL_ROUNDS):
            response = _create_with_retry(
                client,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                messages=messages,
                tools=[SUBMIT_POLICY_TOOL_SCHEMA],
                tool_choice="required",
                **extra_params,
            )
            choice = response.choices[0]
            if choice.finish_reason == "length":
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
                error = _safety_check_error(code)
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
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        **extra_params,
    )
    if response.choices[0].finish_reason == "length":
        raise ValueError(
            "LLM response was cut off before finishing (finish_reason='length'); "
            "the generated code is incomplete. Increase max_tokens or shorten "
            "the system/task prompt."
        )
    return _extract_code(response.choices[0].message.content)


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
        sandbox_timeout: float = 5.0
    ) -> None:
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = model
        self.task_description = task_description
        self.temperature = temperature
        self.max_tokens = max_tokens        # 응답이 코드 완성 전에 잘리는 것을 막기 위한 여유값
        self.extra_params = extra_params or {}  # 프로바이더 전용 옵션 (예: gpt-oss의 reasoning_effort)
        self.sandbox_timeout = sandbox_timeout  # decide() 서브프로세스 실행 하드 타임아웃 (초)
        self.generated_code = None   # LLM이 제출/수락한 코드 원문 (한 번만 생성, 매 스텝 재사용)
        self.last_error = None       # 가장 최근 decide() 호출에서 발생한 예외 (없으면 None)

    # 다음 decide() 호출에서 정책 코드를 새로 생성하도록 캐시를 비움
    def reset(self) -> None:
        self.generated_code = None
        self.last_error = None

    def _generate_code(self) -> str:
        return _generate_code_with_submission_gate(
            self.client,
            self.model,
            CODE_POLICY_SYSTEM_PROMPT,
            self.task_description,
            self.temperature,
            self.max_tokens,
            self.extra_params,
        )

    def decide(self, observation: dict) -> dict:
        try:
            if self.generated_code is None:
                self.generated_code = self._generate_code()

            result = run_decide_code(self.generated_code, observation, timeout=self.sandbox_timeout)
            if result.get("error"):
                self.last_error = result["error"]
                return {"type": "noop"}

            self.last_error = None
            return result["action"]
        except Exception:
            # 매 스텝 같은 버그로 계속 noop이 나와도 원인을 알 수 있도록 예외를 보존.
            # (여기서 noop으로 폴백하는 이유는 그대로: 시뮬레이션 자체는 멈추면 안 됨)
            self.last_error = traceback.format_exc()
            return {"type": "noop"}


# CodePolicy는 코드를 처음 한 번만 생성해 재사용하므로, 생성 이후 들어오는 메시지에
# 맞춰 판단 로직 자체를 바꾸지 못한다 (고정된 반응형 컨트롤러). LiveCodePolicy는 반대로
# 매 decide() 호출마다 그 시점의 observation(및 inbox 메시지)을 LLM에게 보여주고 코드를
# 새로 쓰게 해서, 매 스텝 "대화하며" 판단을 바꿀 수 있게 한다. 대신 스텝마다 LLM 호출이
# 발생하므로 LLMPolicy와 비슷한 속도/비용 특성을 가진다.
CODE_STEP_SYSTEM_PROMPT = f"""You write Python policy code for ONE agent's decision at a \
single simulation step in a multi-agent simulation. Define exactly one function:

def decide(observation):
    ...
    return action

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
- Only output one fenced ```python code block containing the decide() function, nothing else."""


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
        return _generate_code_with_submission_gate(
            self.client,
            self.model,
            CODE_STEP_SYSTEM_PROMPT,
            f"Task: {self.task_description}\n\nCurrent observation:\n{json.dumps(observation, ensure_ascii=False)}",
            self.temperature,
            self.max_tokens,
            self.extra_params,
        )

    def decide(self, observation: dict) -> dict:
        try:
            code = self._generate_code(observation)
            self.generated_code = code  # 실행 실패해도 원문은 남김

            result = run_decide_code(code, observation, timeout=self.sandbox_timeout)
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


HYBRID_POLICY_SYSTEM_PROMPT = _hybrid_policy_system_prompt()


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
        response = _create_with_retry(
            self.client,
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            messages=[
                {"role": "system", "content": HYBRID_POLICY_SYSTEM_PROMPT},
                {"role": "user", "content": (
                    f"Task: {self.task_description}\n\n"
                    f"Current observation:\n{json.dumps(observation, ensure_ascii=False)}"
                )}
            ],
            **self.extra_params
        )
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
                result = run_decide_code(self.generated_code, observation, timeout=self.sandbox_timeout)
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
                safety_error = _safety_check_error(stripped)
                if safety_error is not None:
                    self.last_error = f"generated code rejected: {safety_error}"
                    return {"type": "noop"}

                result = run_decide_code(stripped, observation, timeout=self.sandbox_timeout)
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
