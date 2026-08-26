# Interface Definition

This document defines the functions shared between modules, including their parameters, return values, and expected output formats.

--- 

## world_core.py

### GameMap(Class)

- 변수

self.map_width : 테스트 환경의 좌우 길이

self.map_height : 테스트 환경의 상하 길이

- 함수

__init__(self) -> None : 맵의 기본 함수 정의

configure_map(self) -> None : 맵의 크기 입력(정수형)

---

## tools.py

OpenAI function-calling(tool) 스키마 목록(TOOLS). Environment.apply_action()이 처리하는 action type(move/pick_up/drop/use_key/press_button/pull_lever/send_message/share_belief/request_info/confirm/claim_role/claim_task/noop)과 1:1로 대응됨. apply_action에 새 action type을 추가/변경하면 여기도 함께 갱신해야 함. policy.py의 LLMPolicy가 이 목록을 그대로 사용.

- 변수

TOOLS : 모듈 상수(list[dict]). 각 항목은 {"type": "function", "function": {"name", "description", "parameters"(JSON schema)}} 형식. "issue_command"도 포함되어 있어, 중심 에이전트 역할의 LLM이 다른 에이전트에게 명령을 내리는 데 사용 가능

---

## policy.py

AI가 탑재되는 지점의 추상 인터페이스. 실제 AI(규칙 기반, 강화학습, LLM 등)를 아직 정하지 않았기 때문에, decide() 하나만 강제하는 최소 인터페이스로 두고 이후 이 클래스를 상속해 구현체를 갈아끼우는 구조.

전역 함수/상수 (모듈 레벨)

_create_with_retry(client, **kwargs) -> ChatCompletion : client.chat.completions.create(**kwargs)를 그대로 호출하되, RateLimitError(429)가 나면 응답의 Retry-After 헤더(없으면 _RATE_LIMIT_DEFAULT_DELAY_SEC=5.0초)만큼 대기 후 최대 _RATE_LIMIT_MAX_RETRIES=3회까지 재시도. OpenRouter 무료 모델처럼 여러 사용자가 공유하는 풀에서 일시적인 429가 흔한데, 그대로 즉시 포기하면 상위 스텝 루프가 짧은 간격으로 계속 같은 429를 재유발하므로 여기서 서버가 알려준 시간만큼 기다렸다가 재시도함. 모든 재시도가 실패하면 마지막 RateLimitError를 그대로 raise (호출부의 last_error 처리로 이어짐). LLMPolicy.decide(), CodePolicy._generate_code(), LiveCodePolicy._generate_code()가 client.chat.completions.create() 대신 이 함수를 사용

### Policy(Class)

- 함수

decide(self, observation: dict) -> dict : 추상 메서드. observation을 받아 action(dict)을 반환. 하위 클래스에서 반드시 구현

### NoopPolicy(Class, Policy 상속)

AI 미탑재 상태의 기본값. 아무 행동도 하지 않음.

- 함수

decide(self, observation: dict) -> dict : 항상 {"type": "noop"} 반환

### RandomPolicy(Class, Policy 상속)

실제 AI를 붙이기 전, environment 동작 확인용 무작위 이동 정책.

- 변수

self.step_size : 한 번에 이동할 수 있는 최대 거리

- 함수

__init__(self, step_size: float = 5.0) -> None : 이동 폭 설정

decide(self, observation: dict) -> dict : -step_size ~ step_size 범위의 무작위 dx, dy로 {"type": "move", "dx":.., "dy":..} 반환

### ToolUsePolicy(Class, Policy 상속)

관찰(observation)만 보고 실제로 도구를 쓰는 규칙 기반 정책. 우선순위: 인벤토리의 열쇠로 문 열기 -> 상호작용 범위 안 버튼/레버로 문 열기 -> 상호작용 범위 안 열쇠 습득 -> 가장 가까운 목표(열쇠>버튼>레버>문) 방향으로 이동 -> 할 일 없으면 무작위 배회. 실제 AI를 붙이기 전, environment 전체(문/열쇠/버튼/레버/압력판)가 잘 맞물려 도는지 확인하는 테스트베드.

- 변수

self.interact_radius : Environment.interact_radius와 맞춰 설정해야 하는 상호작용 판단 거리

self.step_size : 한 번에 이동할 수 있는 최대 거리

- 함수

__init__(self, interact_radius: float = 15.0, step_size: float = 5.0) -> None : 상호작용 거리와 이동 폭 설정

decide(self, observation: dict) -> dict : 위 우선순위에 따라 action(dict) 반환. use_key 사용 가능 판정은 문 중심이 아니라 가장자리 기준(interact_radius + door["radius"] 이내)으로 함 (Environment.use_key와 동일한 이유)

_distance(self, x: float, y: float, obj: dict) -> float : 현재 좌표에서 obj까지의 거리

_nearest(self, x: float, y: float, objs: list) -> dict | None : objs 중 가장 가까운 것을 반환 (없으면 None)

_move_toward(self, x: float, y: float, obj: dict) -> dict : obj를 향해 이동하는 move action 생성. obj가 문이면 문의 radius(+여유 1.0)를 고려해 그 반경 밖에서 멈추도록 stop_distance를 계산 (그렇지 않으면 문의 차단 반경에 막혀 제자리에서 멈추는 상태에 빠질 수 있음)

### LLMPolicy(Class, Policy 상속)

openai 파이썬 SDK로 로컬/오픈소스 tiny 모델을 호출하는 정책. Ollama/vLLM/LM Studio처럼 OpenAI 호환 API(base_url)를 제공하는 서버에 연결해 여러 tiny 모델을 실험 대상으로 붙일 수 있음 (OpenAI 클라우드 API도 model/api_key만 맞으면 그대로 사용 가능). tools.py의 TOOLS를 function-calling 스키마로 전달하고, 모델이 고른 tool_call을 그대로 action(dict)으로 변환. tiny 모델은 tool_call을 아예 안 하거나 잘못된 인자를 줄 수 있어, 그런 경우와 API 예외 모두 noop으로 대체해 시뮬레이션이 멈추지 않게 함.

- 변수

self.client : openai.OpenAI 클라이언트 인스턴스

self.model : 호출할 모델 이름

self.system_prompt : 매 호출마다 system 메시지로 넣는 프롬프트

self.temperature : 생성 temperature

self.max_tokens : 응답의 최대 출력 토큰 수 (기본 2000). 추론(reasoning) 모델이 답을 내기 전 토큰을 많이 써서 응답이 잘리는 것을 방지

self.extra_params : chat.completions.create()에 그대로 전달되는 프로바이더 전용 옵션 (dict). 예: Groq의 gpt-oss 계열에서 reasoning_effort="low"로 추론 토큰 사용을 줄일 때 사용

self.last_error : 가장 최근 decide() 호출에서 noop으로 대체된 사유 (응답 잘림/tool 미호출/예외 등). 없으면 None

- 함수

__init__(self, model: str, base_url: str = None, api_key: str = "not-needed", system_prompt: str = ..., temperature: float = 0.2, max_tokens: int = 2000, extra_params: dict = None) -> None : client 생성 및 설정 저장. base_url을 로컬 서버 주소로 지정하면 tiny 모델에 연결됨

decide(self, observation: dict) -> dict : observation을 JSON으로 만들어 system_prompt와 함께 chat.completions.create(tools=TOOLS, tool_choice="required", **extra_params)로 호출 (매 스텝 반드시 tool을 고르도록 강제, 텍스트로만 답하고 넘어가는 것을 방지). finish_reason이 "length"(응답 잘림)이거나 tool_call이 없으면 그 사유를 last_error에 남기고 noop. 정상이면 첫 번째 tool_call의 function.name을 action["type"]으로, function.arguments(JSON)를 나머지 필드로 채워 반환하고 last_error를 None으로 초기화. 예외(네트워크 오류, JSON 파싱 실패 등) 발생 시 traceback을 last_error에 남기고 {"type": "noop"} 반환

### CodePolicy(Class, Policy 상속)

"Code as Policies"(Liang et al., 2023) 스타일 정책. LLMPolicy는 매 스텝 tool_call을 하나씩 받아오지만, CodePolicy는 LLM에게 observation -> action(dict)을 계산하는 decide() 함수의 코드를 한 번만 작성하게 하고, 이후 매 스텝 그 코드를 그대로 실행해 재사용(반응형 컨트롤러처럼 동작, LLM 재호출 없음). 생성된 코드는 환경을 직접 조작하지 않고 action(dict)만 반환하는 순수 함수여야 하며, 그래야 apply_action의 Rule 강제를 우회할 수 없음. 논문 III절과 동일하게 import/exec/eval/open/__로 시작하는 이름 사용을 금지하고, 제한된 builtins로 exec하여 안전하게 실행.

- 변수

self.client : openai.OpenAI 클라이언트 인스턴스

self.model : 코드 생성에 쓸 모델 이름

self.task_description : decide() 코드를 생성할 때 user 메시지로 전달하는 작업 설명 (자연어)

self.temperature : 코드 생성 temperature (기본 0.0, 결정적 출력 권장)

self.max_tokens : 코드 생성 요청의 최대 출력 토큰 수 (기본 4000). 너무 작으면 코드가 완성되기 전에 응답이 잘려 SyntaxError로 이어질 수 있어 넉넉히 잡음

self.extra_params : chat.completions.create()에 그대로 전달되는 프로바이더 전용 옵션 (dict). 예: Groq의 gpt-oss 계열에서 reasoning_effort="low"로 추론 토큰 사용을 줄일 때 사용

self._decide_fn : 생성/컴파일된 decide() 함수 캐시. None이면 다음 decide() 호출 때 새로 생성

self.generated_code : LLM이 실제로 작성한 decide() 코드 원문 (str). 아직 생성 전이면 None. 컴파일/안전성 검사 실패해도 원문은 남아있어 디버깅/표시용으로 확인 가능

self.last_error : 가장 최근 decide() 호출에서 발생한 예외의 traceback 문자열 (없으면 None). noop으로 조용히 대체되는 실패의 원인을 밖에서 확인할 수 있게 함

- 함수

__init__(self, model: str, task_description: str, base_url: str = None, api_key: str = "not-needed", temperature: float = 0.0, max_tokens: int = 4000, extra_params: dict = None) -> None : client 생성 및 설정 저장

reset(self) -> None : _decide_fn, generated_code, last_error를 모두 비워, 다음 decide() 호출에서 정책 코드를 새로 생성하도록 함

_generate_code(self) -> str : CODE_POLICY_SYSTEM_PROMPT(액션 스키마 문서 포함) + task_description으로 LLM을 호출(max_tokens, extra_params 반영)해 생성된 코드 텍스트(마크다운 코드펜스 포함 가능)를 반환. finish_reason이 "length"(응답이 잘림)이면 그 사실을 명시한 ValueError 발생 (원인 불명의 SyntaxError로 이어지는 것을 방지)

_compile(self, code: str) -> Callable : 모듈 함수 _compile_decide_code(code)에 위임 (안전성 검사 후 제한된 스코프에서 exec하여 decide 함수를 반환)

decide(self, observation: dict) -> dict : _decide_fn이 없으면 생성+컴파일해 캐싱한 뒤 호출. 성공하면 last_error를 None으로 초기화. 반환값이 dict가 아니거나 "type"이 없으면, 또는 코드 생성/안전성 검사/실행 중 예외가 나면 last_error에 상세 내용을 기록하고 {"type": "noop"} 반환

전역 함수/상수 (모듈 레벨)

CODE_POLICY_SYSTEM_PROMPT : CodePolicy가 코드 생성 시 사용하는 system 프롬프트 (tools.TOOLS 기반 액션 스키마 설명 + 규칙 + 예시 포함)

_action_schema_docs() -> str : TOOLS를 사람이 읽을 수 있는 액션 스키마 설명 텍스트로 변환

_check_code_safety(code: str) -> None : ast로 파싱해 import문, __로 시작하는 이름 참조, exec/eval/open/__import__/compile/input 호출을 발견하면 ValueError 발생

_extract_code(text: str) -> str : LLM 응답에서 마크다운 코드펜스(```python ... ``` 등, 언어 태그는 알파벳 단어면 아무거나 인식)를 제거해 순수 코드(또는 순수 JSON) 텍스트만 추출

_compile_decide_code(code: str) -> Callable : _check_code_safety()로 안전성 검사 후, 제한된 builtins(+math)만 있는 스코프에서 exec하여 정의된 decide 함수를 반환. decide 함수가 없으면 예외 발생. CodePolicy/LiveCodePolicy/HybridPolicy가 공통으로 사용

### LiveCodePolicy(Class, Policy 상속)

CodePolicy는 코드를 처음 한 번만 생성해 재사용하므로, 생성 이후 들어오는 메시지(inbox)에 맞춰 판단 로직 자체를 바꾸지 못한다(고정된 반응형 컨트롤러). LiveCodePolicy는 반대로 매 decide() 호출마다 그 시점의 observation(및 inbox 메시지)을 LLM에게 보여주고 decide() 코드를 새로 쓰게 해서, 에이전트가 매 스텝 "대화하며" 판단을 바꿀 수 있게 한다. 대신 스텝마다 LLM 호출이 발생하므로 LLMPolicy와 비슷한 속도/비용 특성을 가짐(CodePolicy보다 느리고 API 호출량이 많음).

- 변수

self.client : openai.OpenAI 클라이언트 인스턴스

self.model : 코드 생성에 쓸 모델 이름

self.task_description : 매 스텝 user 메시지에 관찰(observation)과 함께 전달하는 작업 설명 (자연어). 전체 계획을 한 번에 담을 필요 없이 "지금 무엇을 해야 하는가"에 집중해도 됨 (다음 스텝에 다시 물어보기 때문)

self.temperature : 코드 생성 temperature (기본 0.2)

self.max_tokens : 코드 생성 요청의 최대 출력 토큰 수 (기본 1500, 스텝당 짧은 코드 하나만 생성하므로 CodePolicy보다 작게 설정)

self.extra_params : chat.completions.create()에 그대로 전달되는 프로바이더 전용 옵션 (dict). 예: Groq의 gpt-oss 계열에서 reasoning_effort="low"

self.generated_code : 가장 최근 스텝에서 LLM이 작성한 decide() 코드 원문 (str). 매 스텝 덮어써짐. 표시/디버깅용

self.last_error : 가장 최근 decide() 호출에서 발생한 예외의 traceback 문자열 (없으면 None)

- 함수

__init__(self, model: str, task_description: str, base_url: str = None, api_key: str = "not-needed", temperature: float = 0.2, max_tokens: int = 1500, extra_params: dict = None) -> None : client 생성 및 설정 저장 (캐시 없음 - CodePolicy와 달리 _decide_fn을 저장하지 않음)

_generate_code(self, observation: dict) -> str : CODE_STEP_SYSTEM_PROMPT(액션 스키마 문서 포함) + task_description + 현재 observation(JSON)으로 매번 LLM을 새로 호출(max_tokens, extra_params 반영)해 생성된 코드 텍스트를 반환. finish_reason이 "length"이면 ValueError 발생

_compile(self, code: str) -> Callable : 모듈 함수 _compile_decide_code(code)에 위임

decide(self, observation: dict) -> dict : 매 호출마다 _generate_code()로 코드를 새로 받아 self.generated_code에 저장한 뒤 즉시 _compile()해서 그 자리에서 실행 (캐싱 없이 매번 컴파일까지 새로). 반환값이 dict가 아니거나 "type"이 없으면, 또는 코드 생성/안전성 검사/실행 중 예외가 나면 last_error에 상세 내용을 기록하고 {"type": "noop"} 반환, 성공하면 last_error를 None으로 초기화

전역 상수 (모듈 레벨)

CODE_STEP_SYSTEM_PROMPT : LiveCodePolicy가 매 스텝 코드 생성 시 사용하는 system 프롬프트. CODE_POLICY_SYSTEM_PROMPT와 액션 스키마/안전 규칙은 동일하지만, "매 스텝 다시 호출되니 이번 한 스텝만 결정하면 된다"는 점을 명시

### HybridPolicy(Class, Policy 상속)

LiveCodePolicy(매 스텝 코드 재생성)와 CodePolicy(한 번 생성 후 고정 재사용)의 중간 지점. 평소엔 캐시된 코드를 그대로 실행해 LLM을 호출하지 않다가, 그 코드 스스로 {"type": "replan"}을 반환할 때만(상황이 바뀌어 더 이상 처리 못 할 때) LLM을 다시 불러 새로 판단한다. 또한 LLM은 매번 코드를 쓸 필요 없이, 그 자리에서 끝나는 단순한 행동이면 코드 없이 action(JSON) 하나만 답해도 된다 - "코드"는 복잡한 행동(추적/회피/다단계 조건)이 필요할 때만 쓰는 도구가 됨. OpenAI의 tools(function-calling) API는 전혀 쓰지 않고 텍스트만 파싱하므로 tool-calling 미지원 모델(OpenRouter 무료 모델 등)에서도 동작.

- 변수

self.client : openai.OpenAI 클라이언트 인스턴스

self.model : 호출할 모델 이름

self.task_description : LLM에게 매번(직접 행동/코드 응답 요청 시) observation과 함께 전달하는 작업 설명

self.temperature : 응답 temperature (기본 0.2)

self.max_tokens : 응답의 최대 출력 토큰 수 (기본 1500)

self.extra_params : chat.completions.create()에 그대로 전달되는 프로바이더 전용 옵션 (dict)

self._decide_fn : 캐시된 코드 모드 함수. None이면 다음 decide() 호출에서 매번 LLM에게 새로 물어봄(직접 행동 모드일 수도, 코드 모드로 새로 전환될 수도 있음)

self.generated_code : 현재 캐시된 코드 원문 (str). 코드 모드가 아니면(직접 행동으로 응답 중이거나 아직 캐시가 없으면) None

self.last_error : 가장 최근 decide() 호출에서 발생한 예외/사유 (없으면 None)

- 함수

__init__(self, model: str, task_description: str, base_url: str = None, api_key: str = "not-needed", temperature: float = 0.2, max_tokens: int = 1500, extra_params: dict = None) -> None : client 생성 및 설정 저장

_ask_llm(self, observation: dict) -> str : HYBRID_POLICY_SYSTEM_PROMPT + task_description + 현재 observation(JSON)으로 LLM을 호출(max_tokens, extra_params 반영)해 응답 텍스트를 반환. finish_reason이 "length"이면 ValueError 발생

decide(self, observation: dict) -> dict : (1) 캐시된 _decide_fn이 있으면 실행 - 반환 action이 {"type":"replan"}이 아니면 그대로 반환(LLM 호출 없음), replan이면 캐시를 비우고 이번 호출 안에서 바로 (2)로 진행. (2) 캐시가 없으면 _ask_llm()으로 응답을 받아 _extract_code()로 펜스를 벗긴 뒤, "def decide("가 포함돼 있으면 코드로 간주해 _compile_decide_code()로 컴파일·캐싱하고 즉시 실행한 결과(단, replan이면 무효 처리)를, 아니면 순수 JSON으로 간주해 json.loads() 후 그 action을 바로 반환. 반환값이 유효한 action(dict, "type" 포함)이 아니거나 코드 생성/컴파일/실행 중 예외가 나면 last_error에 기록하고 {"type": "noop"} 반환(캐시도 비움), 성공하면 last_error를 None으로 초기화

전역 상수 (모듈 레벨)

HYBRID_POLICY_SYSTEM_PROMPT : HybridPolicy가 사용하는 system 프롬프트. 매 응답을 "단순 행동 하나(JSON)" 또는 "재사용 가능한 decide() 코드(```python)" 중 하나로만 하도록 지시하고, 코드 안에서만 의미 있는 {"type": "replan"} 규약을 설명

---

## rule.py

실험을 위해 정해두는 강제 규칙의 추상 인터페이스. 에이전트의 AI(policy)가 어떤 action을 고르든, 이 규칙을 통과한 action만 environment에 실제로 적용되므로 에이전트는 규칙을 무조건 따르게 됨. Environment.apply_action() 내부에서 강제되기 때문에 step()을 거치지 않고 apply_action()을 직접 호출해도 우회할 수 없음.

### Rule(Class)

- 함수

enforce(self, agent, observation: dict, action: dict) -> dict : 추상 메서드. action을 검사하고 필요하면 다른 action으로 강제 교체해 반환. 하위 클래스에서 반드시 구현

### AllowAllRule(Class, Rule 상속)

아무 제약 없이 action을 그대로 통과시키는 기본 규칙.

- 함수

enforce(self, agent, observation: dict, action: dict) -> dict : action을 그대로 반환

### ForbidActionRule(Class, Rule 상속)

지정한 action type들을 금지하고, 시도하면 noop으로 강제 교체 (예: 특정 에이전트의 메시지 전송 금지 실험).

- 변수

self.forbidden_types : 금지할 action type의 집합(set)

- 함수

__init__(self, forbidden_types) -> None : 금지 목록 설정

enforce(self, agent, observation: dict, action: dict) -> dict : action["type"]이 forbidden_types에 있으면 {"type": "noop"}으로 교체, 아니면 그대로 반환

### ObeyCommandRule(Class, Rule 상속)

중심-주변(hierarchical) 에이전트 구조를 위한 규칙. commander_id로부터 받은 "command" 타입 메시지가 있으면, 이 에이전트의 policy가 무엇을 결정했든 무시하고 그 명령(action)을 그대로 강제 실행. Environment.set_hierarchy()로 특정 에이전트에게만 걸어주는 방식이라, 아무 설정 안 하면 기존처럼 모든 에이전트가 동등한 구조 그대로 유지됨. 한 번 실행된 명령은 inbox 메시지에 "handled": True로 표시되어 같은 명령이 매 틱 반복 실행되지 않음 (다음 command가 올 때까지는 다시 자기 policy를 따름).

- 변수

self.commander_id : 이 규칙이 명령을 받아들이는 대상 에이전트의 id

- 함수

__init__(self, commander_id: str) -> None : commander_id 설정

enforce(self, agent, observation: dict, action: dict) -> dict : observation["inbox"]에서 commander_id가 보낸, 아직 처리 안 된("handled" 아닌) 첫 "command" 메시지를 찾아 handled로 표시하고 그 command(action dict)를 반환. 없으면 원래 action을 그대로 반환

---

## physics.py

에이전트 이동을 실제로 어떻게 처리할지(경계/충돌 계산)를 결정하는 교체 가능한 인터페이스. Environment.move_agent()가 좌표 계산을 직접 하지 않고 이 인터페이스에 위임하므로, 팀원이 정교한 물리 엔진을 만들면 이 클래스를 상속한 구현체로 통째로 교체해 Environment(physics=...)에 넣기만 하면 됨 (agent/policy/rule/tools는 그대로 유지).

### PhysicsEngine(Class)

- 함수

resolve_move(self, environment, agent, dx: float, dy: float) -> tuple[float, float] : 추상 메서드. 에이전트가 (dx, dy)만큼 이동을 시도할 때 경계/충돌을 반영한 최종 (x, y)를 반환. environment로 맵 크기(game_map)와 물체 목록(objects)을 조회. 하위 클래스에서 반드시 구현

### SimplePhysicsEngine(Class, PhysicsEngine 상속)

실제 물리 엔진이 준비되기 전까지 쓰는 자리표시자(placeholder) 기본 구현. 맵 경계로 좌표를 clamp하고, 잠긴 문의 radius 안쪽으로는 진입을 막는 것 외에는 아무 충돌 처리도 하지 않음(에이전트끼리는 서로 통과 가능). 벽 등 정적 물리 구조는 world_core 쪽 물리 엔진이 맡을 영역이라 다루지 않음. Environment 생성 시 physics를 지정하지 않으면 기본값으로 사용됨.

- 함수

resolve_move(self, environment, agent, dx: float, dy: float) -> tuple[float, float] : 새 좌표를 맵 경계 안으로 clamp한 뒤, _blocked_by_door()로 막히면 원래 좌표를 그대로 반환(이동 취소), 아니면 새 좌표 반환

_blocked_by_door(self, environment, x: float, y: float) -> bool : 해당 좌표가 environment.objects 중 잠긴 문(locked)의 radius 안인지 판정

---

## agent.py

### Agent(Class)

- 변수

self.agent_id : 에이전트 고유 식별자

self.x : 에이전트의 x좌표 (연속값)

self.y : 에이전트의 y좌표 (연속값)

self.facing : 에이전트가 바라보는 방향 (도, 0~360)

self.view_radius : 에이전트의 시야 반경

self.view_angle : 에이전트의 시야각 (전체 폭, 도)

self.inventory : 에이전트가 보유한 아이템 목록

self.inbox : 에이전트가 수신한 메시지 목록

self.policy : 에이전트에 탑재된 AI (policy.py의 Policy 구현체, 예: NoopPolicy, RandomPolicy, 추후 실제 AI)

self.rules : 이 에이전트에게만 적용되는 강제 규칙 목록 (list[Rule]), 환경 전역 규칙에 추가로 적용됨

- 함수

__init__(self, agent_id: str, x: float, y: float, facing: float = 0.0, view_radius: float = 100.0, view_angle: float = 90.0) -> None : 에이전트 기본 정보 정의

set_policy(self, policy: Policy) -> None : 에이전트에 AI(Policy 구현체)를 탑재

decide(self, observation: dict) -> dict : 탑재된 policy.decide(observation)을 호출해 action을 반환 (policy 없으면 {"type": "noop"})

add_rule(self, rule: Rule) -> None : 이 에이전트 전용 강제 규칙을 추가

---

## history.py

에이전트 사이에 오간 메시지를 순서대로 기록하는 로그. README의 반사실적 재현(counterfactual replay) - "언제, 어느 에이전트가 실패를 유발했는지" 분석 - 을 하려면 대화 기록이 남아있어야 하므로, Environment._deliver()가 메시지를 전달할 때마다 자동으로 여기 기록됨.

### MessageLog(Class)

- 변수

self.entries : 기록된 메시지 목록 (list[dict]). 각 항목은 {"step":.., "receiver_id":.., "type":.., "from":.., (type별 추가 필드: content/subject/claim/agree/role/task/command 등)}

- 함수

__init__(self) -> None : 빈 로그로 초기화

record(self, step: int, receiver_id: str, message: dict) -> None : message(type/from 등이 이미 담긴 dict)를 step, receiver_id와 함께 deep copy로 기록 (이후 원본 message가 바뀌어도 로그는 그대로 보존)

filter(self, sender_id: str = None, receiver_id: str = None, message_type: str = None) -> list[dict] : sender_id("from")/receiver_id/message_type("type") 중 지정한 조건만 만족하는 항목을 반환 (모두 생략하면 전체)

clear(self) -> None : 기록을 모두 비움

### DecisionLog(Class)

매 step마다 각 에이전트가 무엇을 관찰했고, 자신의 policy가 무엇을 결정했으며, Rule 강제 적용 이후 실제로는 무엇이 실행됐는지를 기록. "이 에이전트가 이 시점에 다른 행동을 했다면 어떻게 됐을까"를 묻는 반사실적 재현에 필요한 관찰/결정 기록. Environment.step()이 매 에이전트 결정마다 자동으로 여기 기록함.

- 변수

self.entries : 기록된 결정 목록 (list[dict]). 각 항목은 {"step":.., "agent_id":.., "observation":.., "action":.., "final_action":.., "overridden": bool}

- 함수

__init__(self) -> None : 빈 로그로 초기화

record(self, step: int, agent_id: str, observation: dict, action: dict, final_action: dict) -> None : action(policy가 실제로 고른 원본 결정)과 final_action(Rule 강제까지 반영해 실제로 실행된 action - Rule이 개입 안 했으면 action과 동일)을 observation과 함께 deep copy로 기록. overridden은 action != final_action 여부(Rule이 policy의 결정을 바꿔치기했는지)를 자동 계산해 같이 저장

filter(self, agent_id: str = None, step: int = None, action_type: str = None, overridden: bool = None) -> list[dict] : agent_id/step/action_type("action"의 "type")/overridden 중 지정한 조건만 만족하는 항목을 반환 (모두 생략하면 전체)

clear(self) -> None : 기록을 모두 비움

---

## enviroment.py

Agent(agent.py), MessageLog(history.py), PhysicsEngine(physics.py), Rule(rule.py)을 import해서 사용. 맵 자체는 만들지 않고 world_core.GameMap을 참조만 함.

### Environment(Class)

- 변수

self.game_map : 에이전트 이동 범위를 정의하는 맵 객체 (world_core.GameMap, 맵 자체는 environment에서 생성하지 않고 참조만 함)

self.agents : 환경에 등록된 에이전트 목록 (dict[str, Agent])

self.objects : 환경에 배치된 상호작용 가능한 물체 목록 (dict[str, dict], 다른 에이전트는 포함하지 않음). type이 "item"/"key"/"door"/"button"/"lever"/"pressure_plate"/"clue", 또는 add_mover로 만든 임의의 type(기본 "hazard")

self.interact_radius : 문/버튼 등과 상호작용(use_key, press_button)할 수 있는 최대 거리

self.physics : 이동/충돌 계산을 위임할 physics.py의 PhysicsEngine 구현체. 생성 시 physics를 안 주면 SimplePhysicsEngine(자리표시자)을 기본으로 사용하며, 나중에 실제 물리 엔진이 준비되면 이 값만 교체하면 됨 (agent/policy/rule/tools는 그대로 유지)

self.rules : 모든 에이전트에게 동일하게 적용되는 전역 강제 규칙 목록 (list[Rule])

self.step_count : step()이 몇 번 실행됐는지 (1부터 증가). 메시지 기록에 시점을 남기는 용도

self.message_log : 오간 메시지를 전부 기록하는 history.py의 MessageLog 인스턴스 (반사실적 재현 분석용)

self.decision_log : 매 step 각 에이전트의 관찰/결정/실제 실행(Rule 적용 후)을 기록하는 history.py의 DecisionLog 인스턴스 (반사실적 재현 분석용)

- 함수

__init__(self, game_map, interact_radius: float = 15.0, physics: PhysicsEngine = None) -> None : 환경 초기화, 맵 객체 연결, physics 미지정 시 SimplePhysicsEngine() 사용

add_agent(self, agent_id: str, x: float, y: float, facing: float = 0.0, view_radius: float = 100.0, view_angle: float = 90.0, policy=None, rules: list[Rule] = None) -> Agent : 새 에이전트를 환경에 등록(원하면 policy와 에이전트별 rules 동시 지정)하고 생성된 Agent 반환

remove_agent(self, agent_id: str) -> None : 에이전트를 환경에서 제거

add_rule(self, rule: Rule) -> None : 모든 에이전트에게 적용되는 전역 규칙 추가

add_agent_rule(self, agent_id: str, rule: Rule) -> None : 특정 에이전트에게만 적용되는 규칙 추가

set_hierarchy(self, commander_id: str, subordinate_ids: list[str]) -> None : 중심-주변 구조 설정 편의 함수. subordinate_ids 각각에 ObeyCommandRule(commander_id)를 걸어, commander_id의 명령을 무조건 따르게 만듦. 호출하지 않으면 기존처럼 모든 에이전트가 동등한 구조

_enforce_rules(self, agent: Agent, observation: dict, action: dict) -> dict : 전역 규칙 → 해당 에이전트 전용 규칙 순서로 action을 통과시켜 최종 action을 반환

move_agent(self, agent_id: str, dx: float, dy: float) -> None : 에이전트 이동을 self.physics.resolve_move()에 위임하고 그 결과 좌표를 적용 (실제 경계/충돌 계산은 physics.py 참고)

add_object(self, object_id: str, x: float, y: float, object_type: str = "item") -> None : 환경에 일반 상호작용 물체 배치

remove_object(self, object_id: str) -> None : 환경에서 물체 제거

pick_up(self, agent_id: str, object_id: str) -> None : 에이전트가 근처(interact_radius 이내)의 물체(item/key만 가능, door/button/lever/pressure_plate 불가)를 습득, objects에서 제거하고 inventory에 추가. object_id가 존재하지 않거나 None이면 조용히 무시(예외 없음)

drop(self, agent_id: str, object_id: str) -> None : 에이전트가 물체를 내려놓음, inventory에서 제거하고 현재 위치의 objects에 추가. object_id가 inventory에 없으면 조용히 무시(예외 없음)

add_door(self, door_id: str, x: float, y: float, locked: bool = True, radius: float = 10.0, hidden: bool = False) -> None : 문 배치. locked면 radius 반경 안으로 이동 불가, hidden이면 아주 가까이 가야 관찰에 드러나는 "숨겨진 문"

add_key(self, key_id: str, x: float, y: float, unlocks: str) -> None : 특정 door_id(unlocks)를 여는 열쇠 배치

add_button(self, button_id: str, x: float, y: float, linked_door_id: str) -> None : 특정 door_id(linked_door_id)와 연결된 버튼 배치

add_lever(self, lever_id: str, x: float, y: float, linked_door_ids: list[str]) -> None : 레버 배치. 버튼과 달리 on/off 상태를 유지하며, 여러 door_id(linked_door_ids)를 한 번에 제어 가능

add_pressure_plate(self, plate_id: str, x: float, y: float, linked_door_id: str, radius: float = 10.0) -> None : 압력판 배치. 별도 action 없이 매 step마다 자동 판정되는 수동 트리거형 장치. 같은 linked_door_id로 여러 판을 배치하면(예: 서로 떨어진 위치에 하나씩) 그 문은 연결된 판 전부가 동시에 밟혀야만 열림(AND 조건) - 여러 에이전트가 동시에 협력해야 하는 상황을 만들 때 사용

add_clue(self, clue_id: str, x: float, y: float, content, hidden: bool = True) -> None : 정보 오브젝트 배치. content는 실험 설계자가 정의하는 임의의 값(문자열/딕셔너리 등)으로 게임 로직에는 아무 영향 없이 observation에 그대로 노출됨. hidden=True(기본값)면 add_door의 hidden 오브젝트와 동일하게 interact_radius 안까지 가야만 관찰에 나타나므로, 한 에이전트만 우연히 발견하고 나머지는 메시지로 전달받아야만 아는 정보 비대칭 상황을 만들 수 있음. hidden=False면 일반 물체처럼 시야각 안에서 멀리서도 보임

add_mover(self, mover_id: str, x: float, y: float, waypoints: list[tuple[float, float]], speed: float = 5.0, object_type: str = "hazard", loop: bool = True, extra: dict = None) -> None : waypoints를 순서대로 순회하며 매 step마다 자동으로 위치가 갱신되는 오브젝트 배치(물리적 충돌/차단은 없음 - 정적/동적 충돌 구조는 world_core 물리 엔진의 몫). object_type은 원하는 값 아무거나 가능(기본 "hazard"), extra로 추가 필드(dict)를 오브젝트에 병합 가능(예: 움직이는 열쇠를 만들려면 object_type="key", extra={"unlocks": "d1"}). 목표가 매 스텝 위치를 바꾸므로, 한 번의 판단이 아니라 추적/예측하는 반복문·조건문(코드)이 있어야 따라잡을 수 있는 상황을 만들 수 있음

use_key(self, agent_id: str, key_object_id: str) -> None : 인벤토리의 열쇠를 사용해 근처의 대응 문을 잠금 해제, 열쇠는 소모됨. 거리 판정은 문 중심이 아니라 문의 가장자리 기준(interact_radius + door["radius"] 이내)으로 함 - _blocked_by_door가 잠긴 문의 radius 안쪽 진입 자체를 막으므로, 중심 기준으로만 재면 door["radius"] >= interact_radius일 때 영원히 도달 불가능한 상태가 됨

press_button(self, agent_id: str, button_id: str) -> None : 근처(interact_radius 이내) 버튼을 눌러 연결된 문의 잠금 상태를 토글

pull_lever(self, agent_id: str, lever_id: str) -> None : 근처(interact_radius 이내) 레버를 당겨 on/off 상태를 뒤집고, linked_door_ids의 모든 문 잠금 상태를 그 상태(on=잠금 해제)에 맞춤

_update_pressure_plates(self) -> None : 모든 pressure_plate에 대해 radius 안에 서 있는 에이전트가 있는지 판정한 뒤, 같은 linked_door_id를 공유하는 판들의 점유 여부를 AND로 묶어 그 문을 잠금/해제. 판이 하나뿐인 문은 기존과 동일(점유 시 해제, 아니면 잠금), 여러 판이 연결된 문은 전부 동시에 점유돼야만 해제됨. step() 시작 시 자동 호출됨 (에이전트의 action 없이 동작)

_update_movers(self) -> None : waypoints가 있는 모든 오브젝트를 현재 목표 waypoint 쪽으로 한 스텝(speed만큼) 이동시키고, 도착하면 다음 waypoint로 진행(마지막이면 loop 여부에 따라 처음으로 순환하거나 그 자리에 정지). step() 시작 시 자동 호출됨 (에이전트의 action과 무관하게 동작)

_deliver(self, receiver_id: str, message: dict) -> None : message(dict)를 그대로 수신자의 inbox에 추가하고, self.message_log에도 기록하는 내부 헬퍼 (모든 send_message/share_belief/request_info/confirm/claim_role/claim_task/issue_command가 이 함수를 거치므로 메시지 기록의 유일한 통로). receiver_id가 존재하지 않으면(None 포함) 조용히 무시하고 기록도 남기지 않음(예외 없음)

_broadcast(self, sender_id: str, message: dict) -> None : sender_id를 제외한 모든 에이전트의 inbox에 message를 동일하게 전달하는 내부 헬퍼

send_message(self, sender_id: str, receiver_id: str, content: str) -> None : 자유 텍스트 메시지 전송. inbox에 {"type": "text", "from":.., "content":..}로 기록

share_belief(self, sender_id: str, receiver_id: str, subject: str, claim) -> None : 특정 대상(subject)에 대한 주장(claim)을 상대에게 전달. inbox에 {"type": "belief", ...}로 기록. send_message와 분리한 이유는 "누가 어떤 사실을 주장했고 그게 맞았는지"를 실패 분석에서 구분하기 위함

request_info(self, sender_id: str, receiver_id: str, subject: str) -> None : 특정 대상(subject)에 대한 정보를 상대에게 요청. inbox에 {"type": "request", ...}로 기록

confirm(self, sender_id: str, receiver_id: str, subject: str, agree: bool = True) -> None : 이전 belief/request(subject)에 대해 동의/확인(또는 거부)을 전달. inbox에 {"type": "confirm", ..., "agree": bool}로 기록

claim_role(self, agent_id: str, role: str) -> None : 자신의 역할(role)을 다른 모든 에이전트에게 공개 선언(broadcast). inbox에 {"type": "role_claim", ...}로 기록

claim_task(self, agent_id: str, task: str) -> None : 자신이 맡을 작업(task)을 다른 모든 에이전트에게 공개 선언(broadcast). inbox에 {"type": "task_claim", ...}로 기록

issue_command(self, sender_id: str, receiver_id: str, command) -> None : receiver_id에게 명령(command, action dict)을 전달. inbox에 {"type": "command", "from":.., "command":.., "handled": False}로 기록. 그 자체로는 belief/request처럼 단순 전달일 뿐이며, receiver가 ObeyCommandRule(commander_id=sender_id)을 갖고 있을 때만 실제로 강제되는 명령이 됨 (set_hierarchy 참고)

_is_visible(self, agent: Agent, obj_x: float, obj_y: float) -> bool : 해당 좌표가 에이전트의 시야(반경 + 시야각) 안에 있는지 판정

get_observation(self, agent_id: str) -> dict : 에이전트의 관찰 생성. 자신의 위치/방향/inventory, 시야 내 물체 목록(숨겨진 문은 interact_radius 이내에서만 노출), inbox만 포함하며 다른 에이전트 정보는 제공하지 않음 (협력 평가를 위해 의도적으로 배제). inventory와 visible_objects는 deep copy로 반환(policy/생성된 코드가 observation을 직접 mutate해서 pick_up/use_key 등을 거치지 않고 환경을 조작하는 것을 막기 위함). inbox만은 참조를 그대로 유지(ObeyCommandRule이 message["handled"]=True를 표시해야 하므로)

apply_action(self, agent_id: str, action: dict) -> dict : action을 _enforce_rules()로 먼저 강제 검사/교체한 뒤(ObeyCommandRule이 걸려 있으면 여기서 명령으로 치환됨), move/pick_up/drop/use_key/press_button/pull_lever/send_message/share_belief/request_info/confirm/claim_role/claim_task/issue_command 중 해당 처리로 라우팅. step() 없이 직접 호출해도 규칙은 항상 적용됨. 강제 적용 후 실제로 실행된 action을 반환(step()이 이 값을 DecisionLog에 final_action으로 기록)

step(self) -> None : step_count를 먼저 1 증가시키고, _update_pressure_plates()로 압력판을, _update_movers()로 움직이는 오브젝트를 갱신한 뒤, 모든 에이전트에 대해 관찰 생성 → policy로 행동 결정 → 행동 적용(apply_action이 반환한 final_action까지 observation/action과 함께 decision_log에 기록)을 한 틱만큼 수행
