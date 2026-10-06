# Interface Definition

This document defines the functions shared between modules, including their parameters, return values, and expected output formats.

---

## benchmark.py

CodePolicy 에이전트로 협력 에피소드 하나를 실행하고, 매 step의 결정/메시지/이벤트를 manifest.jsonl로 기록하는 실행 스크립트. 채점은 별도로 maci_judge.py가 manifest를 읽어서 함. 맵은 기본 압력판 맵(build_episode) 또는 mapgen으로 만든 무작위 맵(--map-seed/--map-file) 중 선택. --policy로 API 키 없이 규칙 기반 정책(tooluse/random/noop)으로도 전체 파이프라인(맵/로그/채점)을 실행해 볼 수 있음.

read_secret(env_var: str, filename: str) -> str : 환경변수 env_var를 먼저 보고, 없으면 현재 작업 폴더의 filename(예: key.txt) 내용을 읽어 API 키 반환. 둘 다 없으면 SystemExit

build_episode() -> tuple[Environment, dict[str, str]] : 압력판 두 개를 동시에 밟아야 열리는 gate 맵과 에이전트 A/B를 만들고 (env, 에이전트별 과제 설명) 반환

GATE_OBJECTIVES : 기본 맵(build_episode)의 클리어 조건 [{"type": "door_unlocked", "door_id": "gate"}] (형식은 scoring._matches 참고)

POLICY_CHOICES : --policy 선택지 ("code", "tooluse", "random", "noop"). code만 LLM(API 키 필요)을 씀

make_policy(kind: str, model: str, description: str, base_url: str, api_key: str, extra_params: dict, interact_radius: float) -> Policy : kind에 맞는 정책 생성. code=CodePolicy, tooluse=ToolUsePolicy(step_size 10), random=RandomPolicy(step_size 10), noop=NoopPolicy. 그 외는 ValueError

run_episode(model: str, base_url: str, api_key: str, extra_params: dict, steps: int, log_path: str, map_spec: MapSpec = None, policy_kind: str = "code") -> None : map_spec이 있으면 mapgen.builder.build_environment()로, 없으면 build_episode()로 환경을 만들고 에이전트마다 make_policy(policy_kind, ...)로 정책을 붙인 뒤 에피소드를 최대 steps만큼 진행하며 step마다 한 줄씩 log_path에 기록. objectives가 전부 충족되면(scoring.clear_step) 성공으로, trap이 발동하면(env.failure) 실패로 조기 종료. 각 줄의 필드: step, task, map_seed(기본 맵이면 None), objectives, cleared(지금까지 모든 objective 충족 여부), messages(이번 step의 MessageLog 항목), events(이번 step의 EventLog 항목), agents(에이전트별 model(code가 아니면 정책 이름)/position/generated_code(CodePolicy가 아니면 None)/decision). 회차가 끝나면 scoring.score_episode()로 점수를 매겨 manifest 옆에 <manifest 이름>.score.json으로 저장하고 총점/단체/에이전트별 점수를 출력 (manifest는 maci_judge.py가 step 단위로 읽으므로 같은 파일에 섞지 않음)

main() -> None : 명령행 인자(--model, --steps, --base-url, --api-key-env, --api-key-file, --reasoning-effort, --out, --map-seed, --map-file, --policy)를 읽어 run_episode 실행. --map-file이 있으면 MapSpec.load()로 불러온 맵, --map-seed가 있으면 generate_map(seed)로 만든 맵을 사용 (둘 다 없으면 기본 맵). API 키는 --policy code(기본)일 때만 읽음

---

## maci_judge.py

build_turn_summary(record: dict, agent_record: dict) -> str : 판정 모델에게 보여줄 한 에이전트의 턴 요약 생성. manifest의 gate_locked 필드가 objectives/cleared로 바뀌어, 요약에 "Objectives: ... (all achieved so far: ...)" 줄을 넣음 (나머지 함수는 이 문서에 아직 정리되지 않음)

---

## mapgen/ (무작위 맵 생성 패키지)

시드 하나로 벽/오브젝트/퍼즐/에이전트 배치/클리어 조건이 들어간 맵을 무작위로 만들거나, pygame 에디터(mapgen/editor.py)로 직접 그려서 만드는 패키지. 두 방식 모두 같은 MapSpec JSON을 만들어 benchmark.py --map-file로 바로 실행 가능. 다른 모듈과 쉽게 분리할 수 있도록 "순수 데이터 생성/편집"(spec/layout/puzzles/generator/hints/editor_model - enviroment/와 pygame에 의존하지 않음), "환경에 적용"(builder - enviroment/를 import하는 유일한 파일), "화면"(editor - pygame을 쓰는 유일한 파일)을 나눔. 같은 seed + 같은 GenConfig면 항상 같은 맵이 나옴. 좌표는 Environment와 같은 맵 좌표(0~width, 0~height)를 씀 (world_core의 화면 여백 25 없음). 벽은 시야와 이동을 모두 막으므로, 생성된 맵은 첫 에이전트 위치에서 걸어서 모든 에이전트/오브젝트에 다가갈 수 있는지 확인을 통과한 것만 반환됨.

### mapgen/spec.py - MapSpec(Class, dataclass)

맵 한 판의 순수 데이터. 다른 모듈에 의존하지 않으므로 JSON으로 저장/공유 가능.

- 변수

seed : 생성에 쓴 시드 (int)

width, height : 맵 크기 (int)

walls : 벽 목록, 각 항목은 [x, y, width, height] (list)

agents : 에이전트 목록, 각 항목은 {"id", "x", "y", "facing"} (list)

objects : 오브젝트 목록, 각 항목은 {"kind", "id", "x", "y", "params"}. kind는 Environment의 add_<kind>() 이름(door/key/button/lever/pressure_plate/item/portal/clue)과 같고 params는 그 함수의 나머지 키워드 인자 그대로 (list)

objectives : 클리어 조건 목록, 각 항목은 EventLog 항목과 비교할 dict (scoring._matches 형식) (list)

puzzles : 사용된 퍼즐 템플릿 이름 목록 (list)

hints : 과제 설명에 들어갈 퍼즐별 안내 문장 목록 (list)

config : 생성에 쓰인 GenConfig 값 (재현용, dict)

- 함수

to_dict(self) -> dict : dict로 변환

from_dict(cls, data: dict) -> MapSpec : (classmethod) dict에서 생성

save(self, path: str) -> None : JSON 파일로 저장

load(cls, path: str) -> MapSpec : (classmethod) JSON 파일에서 불러오기

### mapgen/layout.py - Layout(Class)

벽 생성과, 벽/다른 오브젝트와 겹치지 않는 빈 좌표 뽑기 담당.

- 변수

self.rng : 난수 생성기 (random.Random, 시드 고정용)

self.width, self.height : 맵 크기

self.margin : 맵 가장자리에서 띄울 거리 (기본 20)

self.min_gap : 오브젝트/스폰끼리 최소 간격 (기본 30)

self.wall_clearance : 벽에서 띄울 거리 (기본 8)

self.walls : 생성된 벽 목록 ([x, y, width, height])

self.points : 이미 사용한 좌표 목록

- 함수

__init__(self, rng: random.Random, width: int, height: int, margin: float = 20.0, min_gap: float = 30.0, wall_clearance: float = 8.0) -> None : 초기화

generate_walls(self, count: int) -> None : world_core._make_random_wall과 같은 크기 규칙(가로 80~200 x 세로 10~25 막대, 또는 그 반대)으로 서로 겹치지 않는 벽을 최대 count개 생성 (count*20번 시도 안에 못 채우면 그만큼만)

_rects_overlap(a, b) -> bool : (staticmethod) 두 사각형 (x, y, w, h)가 겹치는지

_in_wall(self, x: float, y: float) -> bool : 좌표가 벽(wall_clearance만큼 넓힌 범위) 안인지

_free(self, x: float, y: float, gap: float) -> bool : 벽 밖이고 기존 좌표들과 gap 이상 떨어졌는지

free_point(self) -> tuple[float, float] : 빈 좌표를 뽑아 사용 처리 후 반환. 자리가 없으면 간격 조건을 절반씩 완화해서라도 반환 (벽 안에는 절대 두지 않음)

far_pair(self, min_distance: float) -> tuple[tuple[float, float], tuple[float, float]] : 서로 min_distance 이상 떨어진 빈 좌표 두 개 (압력판 쌍, 포탈 쌍 등). 50번 안에 조건을 못 맞추면 시도 중 가장 멀었던 쌍 사용

_release(self, *points) -> None : 사용 처리한 좌표를 되돌림 (far_pair에서 버린 후보용)

all_reachable(self, start, targets, blockers=(), cell: float = 5.0) -> bool : 벽(self.walls)과 blockers(원 (x, y, radius) 목록, 예: 잠긴 문)를 피해 start에서 걸어서 갈 수 있는 칸을 cell 간격 격자 탐색으로 구한 뒤, targets의 각 (x, y, reach)마다 reach 거리 안에 도달 가능한 칸이 있으면 True. 포탈로 이어지는 길은 고려하지 않음(보수적 판정)

### mapgen/puzzles.py

퍼즐 템플릿 모음. 각 템플릿은 (layout, ctx)를 받아 PuzzlePart를 돌려주는 함수이고 PUZZLES에 이름으로 등록됨. 새 퍼즐은 함수를 만들어 PUZZLES에 추가하기만 하면 generator가 자동으로 고를 수 있음.

PuzzleContext(Class, dataclass) : 템플릿에 넘기는 정보. index(이 맵에서 몇 번째 퍼즐인지 - 오브젝트 id 접미사), n_agents, reveal_positions(과제 설명에 대략적인 위치를 넣을지)

PuzzlePart(Class, dataclass) : 템플릿 결과. objects(배치할 오브젝트), objectives(클리어 조건), hints(과제 설명 문장)

_obj(kind: str, obj_id: str, point, **params) -> dict : MapSpec.objects 형식의 오브젝트 dict 생성

_where(ctx: PuzzleContext, point) -> str : reveal_positions면 " (around (x, y))", 아니면 빈 문자열

_door_objective(door_id: str) -> dict : {"type": "door_unlocked", "door_id": door_id}

_pickup_objective(object_id: str) -> dict : {"type": "item_picked_up", "object_id": object_id}

key_door(layout, ctx) -> PuzzlePart : 잠긴 문 + 그 문을 여는 열쇠 (혼자 가능)

lever_door(layout, ctx) -> PuzzlePart : 잠긴 문 + 연결된 레버 (혼자 가능)

button_door(layout, ctx) -> PuzzlePart : 잠긴 문 + 연결된 버튼 (혼자 가능)

dual_plate_door(layout, ctx) -> PuzzlePart : 잠긴 문 + 맵 짧은 변의 절반 이상 떨어진 압력판 두 개 (두 명이 동시에 밟아야 함)

coop_item(layout, ctx) -> PuzzlePart : coop 물품(required_agents = min(2, n_agents)), 목표는 그 물품 습득

clue_trap(layout, ctx) -> PuzzlePart : 똑같이 보이는 유물 두 개(하나는 진짜 normal, 하나는 위장된 trap) + 어느 쪽이 진짜인지 적힌 숨겨진 clue. 목표는 진짜 유물 습득. trap의 seals는 None으로 두고 generator가 맵의 모든 문으로 채움 (잘못 집으면 클리어 불가)

PUZZLES : 이름 -> (템플릿 함수, 문을 여는 퍼즐인지, 협력이 필요한지) (dict)

### mapgen/generator.py

GenConfig(Class, dataclass) : 생성 설정. width/height(기본 500), n_agents(기본 2), wall_count(벽 개수 범위, 기본 (3, 8)), puzzle_count(기본 2), allowed_puzzles(기본 PUZZLES 전체), require_coop(협력 퍼즐을 최소 하나 넣을지, 기본 True), portal_pairs(양방향 포탈 쌍 개수, 기본 1), distractor_items(목표와 무관한 일반 물품 개수, 기본 1), reveal_positions(과제 설명에 위치 포함, 기본 False)

MAX_ATTEMPTS : 갈 수 없는 곳이 있는 맵이 나왔을 때 같은 rng로 이어서 다시 만드는 최대 횟수 (50)

generate_map(seed: int, config: GenConfig = None) -> MapSpec : 시드로 맵 생성. _generate_once()로 만들고 _is_reachable()을 통과할 때까지 같은 rng로 최대 MAX_ATTEMPTS번 다시 만듦 (같은 seed + config면 결과는 항상 같음). 끝까지 실패하면 RuntimeError

_generate_once(seed: int, rng: random.Random, config: GenConfig) -> MapSpec : 맵 한 번 생성. 벽 → 에이전트 스폰(A, B, C.. / facing은 45도 단위 무작위) → 퍼즐 → trap의 seals를 모든 문으로 연결 → 포탈 쌍 → 방해용 일반 물품 순서로 배치

_is_reachable(spec: MapSpec) -> bool : 첫 에이전트 위치에서 걸어서(Layout.all_reachable) 모든 에이전트(8 이내)와 오브젝트(문은 중심 20 이내, 나머지는 8 이내)에 다가갈 수 있는지. 처음엔 모든 문이 잠겨 있으므로 문도 지나갈 수 없는 장애물로 취급

_choose_puzzles(rng: random.Random, config: GenConfig) -> list[str] : 퍼즐 고르기. 첫 퍼즐은 문을 여는 퍼즐(trap이 봉인할 문이 반드시 있도록), require_coop이고 퍼즐이 2개 이상이면 협력 퍼즐을 최소 하나 포함, 에이전트가 1명이면 협력 퍼즐 제외, 나머지는 허용 목록에서 무작위 후 섞음. 허용 목록에 문 퍼즐이 없으면 ValueError

### mapgen/builder.py

MapSpec을 Environment로 바꾸는 부분. enviroment/를 import하는 유일한 파일이라, 맵 생성기를 다른 환경에 붙이려면 이 파일만 바꾸면 됨.

WallRect(Class) : x, y, width, height만 가진 벽 (Environment._walls가 읽는 형식)

GeneratedMap(Class) : Environment가 맵에서 쓰는 것만 가진 최소 맵 객체. map_width/map_height(이동 범위), walls(WallRect 목록 - 시야 가림). world_core.GameMap에 의존하지 않기 위함

build_environment(spec: MapSpec, interact_radius: float = 15.0) -> tuple[Environment, dict[str, str], list[dict]] : 오브젝트는 getattr(env, "add_" + kind)(id, x, y, **params)로, 에이전트는 add_agent로 배치하고 (env, 에이전트별 과제 설명, objectives) 반환

task_descriptions(spec: MapSpec) -> dict[str, str] : 에이전트별 과제 설명 생성 (맵 크기, 다른 에이전트, 모든 hints를 목표로 나열, 시야/turn/메시지 사용 안내)

### mapgen/hints.py

에디터로 만든 맵처럼 퍼즐 템플릿 없이 만들어진 맵의 과제 설명(hints)을 오브젝트 연결 관계와 objectives로 자동 생성. 순수 데이터만 다룸.

_where(obj: dict, reveal_positions: bool) -> str : reveal_positions면 " (around (x, y))", 아니면 빈 문자열

mechanisms_for(spec: MapSpec, door_id: str) -> list[dict] : door_id를 여는 장치(그 문을 unlocks하는 열쇠, linked_door_id가 그 문인 버튼/압력판, linked_door_ids에 그 문이 있는 레버) 목록

auto_hints(spec: MapSpec, reveal_positions: bool = False) -> list[str] : objective마다 안내 문장 생성 (문: 연결된 열쇠/레버/버튼/압력판(2개 이상이면 동시에 밟기)으로 여는 법, 물품: coop이면 필요 인원과 운반 규칙, 일반이면 줍기). trap이 있으면 함정/단서 안내, 포탈이 있으면 포탈 안내를 덧붙임

### mapgen/editor_model.py - EditorModel(Class)

맵 에디터의 편집 동작(배치/이동/삭제/연결/목표 지정/검증/저장)만 담당. pygame에 의존하지 않으므로 화면 없이 단독으로 쓰거나 테스트할 수 있고 다른 UI를 붙일 수도 있음. 데이터는 MapSpec 형식 그대로 다룸.

- 모듈 상수/함수

OBJECT_TOOLS : 도구 이름 -> (오브젝트 kind, id 접두사, 기본 params). door/key/button/lever/plate(pressure_plate)/item(normal)/coop/trap/clue. trap은 id로 정체가 드러나지 않도록 일반 물품과 같은 접두사(item)를 씀

LINKABLE : 문에 연결할 수 있는 kind ("key", "button", "lever", "pressure_plate")

door_objective(door_id: str) -> dict : {"type": "door_unlocked", "door_id": door_id}

pickup_objective(object_id: str) -> dict : {"type": "item_picked_up", "object_id": object_id}

- 변수

self.spec : 편집 중인 MapSpec (생성 시 받은 spec의 deep copy, 없으면 빈 맵)

- 함수

__init__(self, spec: MapSpec = None, width: int = 500, height: int = 500) -> None : 초기화

_used_ids(self) -> set[str] / _new_id(self, prefix: str) -> str : 사용 중인 id 집합 / 겹치지 않는 "<prefix>_<번호>" id 생성

doors(self) -> list[dict] / _nearest_door(self, x, y) : 문 목록 / 가장 가까운 문(없으면 None)

is_goal(self, obj: dict) -> bool / _objective_for(obj: dict) : 목표로 지정됐는지 / 그 오브젝트의 objective(문: door_unlocked, trap이 아닌 물품: item_picked_up, 나머지 None)

hit_test(self, x: float, y: float, radius: float = 10.0) : (x, y)에 있는 대상. ("object", dict) / ("agent", dict) / ("wall", 인덱스) / None. 오브젝트/에이전트가 벽보다 우선

_clamp(self, x, y) : 맵 범위 안으로 좌표 제한

add_object(self, tool: str, x: float, y: float) -> dict : OBJECT_TOOLS의 도구로 오브젝트 배치. 열쇠/버튼/레버/압력판은 가장 가까운 문에 자동 연결, 문과 coop 물품은 자동으로 목표가 됨

add_portal_pair(self, x1, y1, x2, y2) -> tuple[dict, dict] : 두 지점을 서로 오가는 양방향 포탈 한 쌍

add_agent(self, x, y, facing: float = 0.0) -> dict | None : 비어 있는 첫 알파벳 id(A~Z)로 에이전트 추가 (26명 초과면 None)

add_wall(self, x0, y0, x1, y1, min_size: float = 4.0) -> list | None : 두 모서리로 벽 추가 (가로/세로가 min_size 미만이면 무시)

move_to(self, target, x, y) -> None : 대상을 (x, y)로 이동 (벽은 좌상단 기준, 맵 밖으로 나가지 않게)

delete(self, target) -> None : 대상 삭제. 오브젝트면 그 objective와, 문이면 그 문을 가리키던 열쇠/버튼/레버/압력판 연결도 정리

link(self, source: dict, door: dict) -> bool : 열쇠(unlocks)/버튼·압력판(linked_door_id)을 door에 연결, 레버는 linked_door_ids에서 토글. 대상이 아니면 False

set_portal_dest(self, portal: dict, x, y) -> None : 포탈 목적지 변경

toggle_goal(self, obj: dict) -> bool | None : 목표 지정 토글 (토글 후 목표면 True, 대상이 아니면 None)

toggle_hidden(self, obj: dict) -> bool | None : 문/단서는 hidden, trap은 disguised 토글 (대상이 아니면 None)

rotate_agent(self, agent: dict, delta: float) -> None / set_clue_text(self, clue: dict, text: str) -> None / resize(self, width, height) -> None : 에이전트 방향 회전 / 단서 내용 설정 / 맵 크기 변경

finalize(self) -> MapSpec : 저장/실행용 완성본 (trap의 seals를 모든 문으로 채우고, hints를 auto_hints로 생성, puzzles=["custom"], config={"editor": True})

validate(self) -> tuple[list[str], list[str]] : (errors, warnings). error: 에이전트 없음. warning: 목표 없음, 여는 장치가 없는 목표 문, 에이전트 수보다 많은 압력판만으로 여는 문, 인원이 모자란 coop 물품, 어떤 문에도 연결되지 않은 장치, 내용이 빈 단서, 걸어서 갈 수 없는 곳(generator._is_reachable)

save(self, path: str) -> MapSpec : finalize() 결과를 JSON으로 저장하고 반환

### mapgen/editor.py (pygame 맵 에디터)

python -m mapgen.editor [--load PATH] [--seed N] [--width W] [--height H] [--out PATH] : 빈 맵(기본 500x500), 저장된 맵(--load), 무작위 생성 맵(--seed)에서 시작해 편집. 저장 경로는 --out, 없으면 불러온 파일, 그것도 없으면 map_datas/custom_<시각>.json. 화면/입력만 담당하고 편집 동작은 EditorModel에 맡김. 마우스 좌표는 pygame.mouse 대신 이벤트의 pos만 사용

- 조작 (편집 모드)

도구 키: V 선택/드래그 이동, 1 벽(드래그), 2 문, 3 열쇠, 4 버튼, 5 레버, 6 압력판, 7 일반 물품, 8 협동 물품, 9 함정 물품, 0 포탈(입구→출구 두 번 클릭), C 단서(배치 후 내용 입력), A 에이전트, L 연결(장치→문, 포탈→목적지), G 목표 지정/해제, H 숨김(문/단서)·위장(함정), T 단서 내용 수정. 우클릭: 진행 중인 작업 취소, 없으면 삭제. 휠: 에이전트 방향 45도 회전. Ctrl+S 저장(검증 error가 있으면 거부), P 테스트 플레이, Esc 선택 도구. 좌표는 5 단위로 스냅. 사이드바에 도구/검증 결과(error 빨강, warning 노랑)/메시지 표시

- 조작 (테스트 플레이 모드, P로 전환)

현재 맵을 finalize() → builder.build_environment()로 실제 Environment로 만들어 직접 조작 (Environment는 이때만 import). 방향키/WASD 이동(max_move만큼), Q/E 45도 회전, Space 상호작용(가까운 것부터 열쇠 사용 → 레버/버튼 → 줍기), X 마지막 물품 내려놓기, . 대기, Tab 조작할 에이전트 전환, P/Esc 편집으로 복귀. 키 입력 하나마다 env.step() 한 번 (조작하지 않는 에이전트는 대기). 사이드바에 step, 인벤토리, 목표별 달성 여부, 함정 실패, 최근 이벤트 표시. 현재 에이전트의 시야에 보이는 물체는 흰 테두리로 표시

- 상수/클래스/함수

MAP_VIEW(맵 영역 최대 픽셀 720), PAD(20), SIDEBAR_W(360), SNAP(5), VIEW_RADIUS/VIEW_ANGLE(미리보기 시야 100/90), COLORS(색상표), TOOL_KEYS(키 -> 도구), TOOL_HELP(사이드바 도구 설명)

ManualPolicy(Class) : 테스트 플레이에서 키보드로 고른 행동(next_action)을 한 번만 내보내고 이후엔 noop을 반환하는 정책

EditorApp(Class) : __init__(model: EditorModel, save_path: str)으로 창 생성. run()이 이벤트 루프, handle(event)가 모드별(단서 입력/테스트 플레이/편집) 입력 처리, draw()가 그리기. to_screen/to_map은 맵 좌표 <-> 화면 좌표 변환(to_map은 스냅), save()는 검증 후 저장, start_play()는 테스트 플레이 시작, _smart_interact(env, agent)는 Space 상호작용 결정

main(argv=None) -> None : 명령행 인자를 읽어 에디터 실행

### mapgen/__main__.py (명령행 도구)

python -m mapgen [--seed N] [--agents N] [--puzzles N] [--portals N] [--reveal-positions] [--save] [--out PATH] [--load PATH] [--edit] : 맵을 생성(또는 --load로 불러오기)해 요약과 ASCII 미리보기를 출력. --save면 map_datas/map_<seed>.json으로, --out이면 그 경로로 저장. 시드를 생략하면 무작위 6자리. --edit면 그 맵을 pygame 에디터(EditorApp)로 열어 수정 (pygame은 이때만 import)

render_ascii(spec: MapSpec, cols: int = 60, rows: int = 30) -> str : 맵을 문자 격자로 그림 (# 벽, D 문, k 열쇠, b 버튼, l 레버, P 압력판, O 포탈, ? 단서, i 일반 물품, C coop, T trap, A/B.. 에이전트)

summarize(spec: MapSpec) -> str : 시드/크기/벽 수/퍼즐/objectives/hints 요약

main() -> None : 명령행 인자를 읽어 위 동작 수행

---

## world_core.py

### GameMap(Class)

__init__(self) -> None : 맵의 기본 함수 정의

display_map(self) -> None : pygame을 통하여 화면 출력

make_seed(self, wall_count: int, seed: int) -> str : 시드값 출력(가로x세로-벽의 갯수-6자리 자연수)

read_seed(code: str) -> tuple[int, int, int, int] : 시드의 해석값 출력

make_rseed(self) -> str : 무작위 시드 출력(크기는 사용자 지정 혹은 기본 값 500x500)

configure_map(self) -> None : 맵의 크기 입력(정수형)

---

## tools.py

OpenAI function-calling(tool) 스키마 목록(TOOLS). Environment.apply_action()이 처리하는 action type(move/turn/pick_up/drop/use_key/press_button/pull_lever/send_message/share_belief/request_info/confirm/claim_role/claim_task/noop)과 1:1로 대응됨. apply_action에 새 action type을 추가/변경하면 여기도 함께 갱신해야 함. policy.py의 LLMPolicy가 이 목록을 그대로 사용.

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

"Code as Policies"(Liang et al., 2023) 스타일 정책. LLMPolicy는 매 스텝 tool_call을 하나씩 받아오지만, CodePolicy는 LLM에게 observation -> action(dict)을 계산하는 decide() 함수의 코드를 한 번만 작성하게 하고, 이후 매 스텝 그 코드를 그대로 실행해 재사용(반응형 컨트롤러처럼 동작, LLM 재호출 없음). 생성된 코드는 환경을 직접 조작하지 않고 action(dict)만 반환하는 순수 함수여야 하며, 그래야 apply_action의 Rule 강제를 우회할 수 없음.

생성과 실행이 각각 별도로 강제된다. (1) 생성: 모델은 텍스트로 답을 끝낼 수 없고 submit_policy_code tool을 호출해야만 하며(_generate_code_with_submission_gate), 그 코드가 컴파일+안전성 검사(import/exec/eval/open/__로 시작하는 이름/속성 사용 금지)를 통과해야 accepted로 응답받는다 - 실패하면 그 에러가 tool 결과로 그대로 돌아가 같은 호출 안에서(MAX_TOOL_ROUNDS까지) 다시 제출할 수 있다. tool-calling을 지원하지 않는 프로바이더에서는 자동으로 평문 + 코드펜스 추출 방식으로 대체됨(policy_sandbox.run_decide_code 대신 아무 검증 없이 실행하는 것은 아니고, 실행 단계에서 여전히 안전성 검사를 거침). (2) 실행: decide() 호출마다 policy_sandbox.run_decide_code()가 코드를 격리된 `python -I -S` 서브프로세스에서 하드 타임아웃과 함께 실행 - 무한루프나 크래시가 시뮬레이션 프로세스 자체를 멈추지 못하게 하는 OS 수준 방어선. 자세한 내용은 policy_sandbox.py, _policy_harness.py 참고.

- 변수

self.client : openai.OpenAI 클라이언트 인스턴스

self.model : 코드 생성에 쓸 모델 이름

self.task_description : decide() 코드를 생성할 때 user 메시지로 전달하는 작업 설명 (자연어)

self.temperature : 코드 생성 temperature (기본 0.0, 결정적 출력 권장)

self.max_tokens : 코드 생성 요청의 최대 출력 토큰 수 (기본 4000). 너무 작으면 코드가 완성되기 전에 응답이 잘려 SyntaxError로 이어질 수 있어 넉넉히 잡음

self.extra_params : chat.completions.create()에 그대로 전달되는 프로바이더 전용 옵션 (dict). 예: Groq의 gpt-oss 계열에서 reasoning_effort="low"로 추론 토큰 사용을 줄일 때 사용

self.sandbox_timeout : decide() 실행을 위해 policy_sandbox.run_decide_code()에 넘기는 하드 타임아웃(초, 기본 5.0)

self.generated_code : submit_policy_code로 제출되어 accepted된 decide() 코드 원문 (str). 아직 생성 전이면 None. 한 번 생성되면 이후 매 decide() 호출마다 재사용(서브프로세스 실행만 매번 새로)됨

self.last_error : 가장 최근 decide() 호출에서 발생한 예외의 문자열 (없으면 None). noop으로 조용히 대체되는 실패의 원인을 밖에서 확인할 수 있게 함

self.stall_limit : 위치가 이 step 수만큼 연속으로 그대로면 코드를 재생성 (기본 3)

self.max_replans : 회차당 재생성 최대 횟수 (기본 10). 다 쓰면 기존 코드를 계속 사용

self.replans : 재생성 기록 목록 [{"step", "reason"}]

self.last_replan : 이번 decide() 호출에서 재생성했으면 그 기록 {"step", "reason"}, 아니면 None (benchmark.py가 manifest의 decision.replan으로 기록)

- 재생성(replan) 조건

캐시된 코드는 같은 관찰에 같은 행동을 내므로, 막히면 같은 자리에서 영원히 반복됨. 그래서 다음 경우 LLM에게 이유/이전 코드/현재 관찰(CODE_REPLAN_PROMPT)을 보여주고 코드를 다시 짜게 함
  * 즉시(stuck): decide() 실행 오류(예외/타임아웃/잘못된 action) - 이때는 같은 step 안에서 새 코드로 바로 다시 실행. 또는 move(dx/dy가 0이 아님)를 했는데 위치가 그대로(벽/잠긴 문/coop 운반에 막힘)
  * 누적(정지): stall_limit step 연속으로 위치가 그대로. 단 known_objects의 압력판 위에 서 있으면 의도된 대기이므로 제외

- 함수

__init__(self, model: str, task_description: str, base_url: str = None, api_key: str = "not-needed", temperature: float = 0.0, max_tokens: int = 4000, extra_params: dict = None, sandbox_timeout: float = 5.0, stall_limit: int = 3, max_replans: int = 10) -> None : client 생성 및 설정 저장

reset(self) -> None : generated_code, last_error, 재생성 기록과 정지 판정 상태를 모두 비워, 다음 decide() 호출에서 정책 코드를 새로 생성하도록 함

_generate_code(self, user_content: str = None) -> str : 모듈 함수 _generate_code_with_submission_gate(client, model, CODE_POLICY_SYSTEM_PROMPT, user_content 또는 task_description, temperature, max_tokens, extra_params)에 위임

_stuck_reason(self, observation: dict) -> str | None : 직전 위치/행동과 비교해 정지 횟수를 갱신하고, 위 재생성 조건에 해당하면 이유 문장을 반환 (아니면 None)

_on_pressure_plate(observation: dict, pos) -> bool : (staticmethod) pos가 known_objects의 압력판 radius 안인지

_replan(self, observation: dict, reason: str) -> bool : CODE_REPLAN_PROMPT로 코드를 재생성하고 replans/last_replan에 기록, 정지 횟수 초기화. max_replans를 다 썼으면 아무것도 안 하고 False

decide(self, observation: dict) -> dict : generated_code가 없으면 _generate_code()로 먼저 채우고, 있으면 _stuck_reason()이 이유를 내면 _replan(). 그 뒤 policy_sandbox.run_decide_code()로 서브프로세스에서 실행하고, 실행 오류면 _replan() 후 한 번 더 실행. 성공하면 last_error를 None으로 초기화하고 결과 action을 반환. 그래도 오류(에러 문자열, 타임아웃, 잘못된 반환값, 코드 생성 실패 포함)면 last_error에 기록하고 {"type": "noop"} 반환. 다음 판정을 위해 이번 위치와 반환한 action을 기억

전역 함수/상수 (모듈 레벨)

CODE_POLICY_SYSTEM_PROMPT : CodePolicy가 코드 생성 시 사용하는 system 프롬프트 (tools.TOOLS 기반 액션 스키마 설명 + 규칙 + 예시 포함)

_OBSERVATION_DOC : CodePolicy/LiveCodePolicy 프롬프트에 들어가는 observation 형식 설명 (self의 필드, visible_objects/known_objects/walls/memory/inbox의 의미, 오브젝트 type별 필드, facing 각도 기준, action에 "memory"를 넣어 메모를 남기는 법, 상호작용 거리). Environment.get_observation이 바뀌면 같이 갱신해야 함

MAX_TOOL_ROUNDS : submit_policy_code 제출이 거부됐을 때(컴파일/안전성 검사 실패) 같은 _generate_code_with_submission_gate() 호출 안에서 재시도할 수 있는 최대 라운드 수 (기본 4)

SUBMIT_POLICY_TOOL_SCHEMA : 모듈 상수(dict). "이 tool 호출만이 유일한 답변 방법"이라고 명시하는 submit_policy_code function-calling 스키마 (parameters: {"code": string})

_action_schema_docs() -> str : TOOLS를 사람이 읽을 수 있는 액션 스키마 설명 텍스트로 변환

_check_code_safety(code: str) -> None : ast로 파싱해 import문, __로 시작하는 이름/속성 참조(예: __builtins__ 뿐 아니라 ({}).__class__ 같은 속성 접근도 포함), exec/eval/open/__import__/compile/input 호출을 발견하면 ValueError 발생. 문법 자체가 잘못됐으면 ast.parse()가 SyntaxError를 그대로 냄

_safety_check_error(code: str) -> str | None : _check_code_safety()를 호출해 통과하면 None, SyntaxError/ValueError면 그 메시지를 문자열로 반환 (submit_policy_code 게이트에서 tool 결과로 그대로 돌려주는 용도)

_extract_code(text: str) -> str : LLM 응답에서 마크다운 코드펜스(```python ... ``` 등, 언어 태그는 알파벳 단어면 아무거나 인식)를 제거해 순수 코드(또는 순수 JSON) 텍스트만 추출

_generate_code_with_submission_gate(client, model, system_prompt, user_content, temperature, max_tokens, extra_params) -> str : submit_policy_code tool-call 루프를 최대 MAX_TOOL_ROUNDS회 진행 - 모델이 tool을 호출하지 않으면 nudge 메시지를 넣고 재시도, 호출했지만 코드가 _safety_check_error()를 통과 못 하면 그 에러를 tool 결과로 돌려주고 재시도, 통과하면 그 코드를 즉시 반환. 라운드를 다 썼거나 프로바이더가 tools/tool_choice 자체를 거부하면(예외 발생) 평문 한 번 호출 + _extract_code()로 펜스 제거하는 예전 방식으로 대체(fallback). CodePolicy._generate_code(), LiveCodePolicy._generate_code()가 공통으로 사용

### LiveCodePolicy(Class, Policy 상속)

CodePolicy는 코드를 처음 한 번만 생성해 재사용하므로, 생성 이후 들어오는 메시지(inbox)에 맞춰 판단 로직 자체를 바꾸지 못한다(고정된 반응형 컨트롤러). LiveCodePolicy는 반대로 매 decide() 호출마다 그 시점의 observation(및 inbox 메시지)을 LLM에게 보여주고 decide() 코드를 새로 쓰게 해서, 에이전트가 매 스텝 "대화하며" 판단을 바꿀 수 있게 한다. 대신 스텝마다 LLM 호출이 발생하므로 LLMPolicy와 비슷한 속도/비용 특성을 가짐(CodePolicy보다 느리고 API 호출량이 많음). 생성은 CodePolicy와 동일하게 submit_policy_code 게이트를 거치고, 실행도 동일하게 policy_sandbox.run_decide_code()로 서브프로세스에서 이뤄짐(매 스텝 새 코드를 새 서브프로세스에서 실행).

- 변수

self.client : openai.OpenAI 클라이언트 인스턴스

self.model : 코드 생성에 쓸 모델 이름

self.task_description : 매 스텝 user 메시지에 관찰(observation)과 함께 전달하는 작업 설명 (자연어). 전체 계획을 한 번에 담을 필요 없이 "지금 무엇을 해야 하는가"에 집중해도 됨 (다음 스텝에 다시 물어보기 때문)

self.temperature : 코드 생성 temperature (기본 0.2)

self.max_tokens : 코드 생성 요청의 최대 출력 토큰 수 (기본 1500, 스텝당 짧은 코드 하나만 생성하므로 CodePolicy보다 작게 설정)

self.extra_params : chat.completions.create()에 그대로 전달되는 프로바이더 전용 옵션 (dict). 예: Groq의 gpt-oss 계열에서 reasoning_effort="low"

self.sandbox_timeout : decide() 실행을 위해 policy_sandbox.run_decide_code()에 넘기는 하드 타임아웃(초, 기본 5.0)

self.generated_code : 가장 최근 스텝에서 제출/수락된 decide() 코드 원문 (str). 매 스텝 덮어써짐. 표시/디버깅용

self.last_error : 가장 최근 decide() 호출에서 발생한 예외의 문자열 (없으면 None)

- 함수

__init__(self, model: str, task_description: str, base_url: str = None, api_key: str = "not-needed", temperature: float = 0.2, max_tokens: int = 1500, extra_params: dict = None, sandbox_timeout: float = 5.0) -> None : client 생성 및 설정 저장 (캐시 없음 - 매 스텝 _generate_code()를 다시 호출)

_generate_code(self, observation: dict) -> str : 모듈 함수 _generate_code_with_submission_gate(client, model, CODE_STEP_SYSTEM_PROMPT, f"Task: ...\\n\\nCurrent observation: ...", temperature, max_tokens, extra_params)에 위임

decide(self, observation: dict) -> dict : 매 호출마다 _generate_code()로 코드를 새로 받아 self.generated_code에 저장한 뒤 policy_sandbox.run_decide_code(code, observation, timeout=sandbox_timeout)로 즉시 서브프로세스 실행. 오류(에러 문자열/타임아웃/잘못된 반환값 포함)가 있으면 last_error에 기록하고 {"type": "noop"} 반환, 성공하면 last_error를 None으로 초기화

전역 상수 (모듈 레벨)

CODE_STEP_SYSTEM_PROMPT : LiveCodePolicy가 매 스텝 코드 생성 시 사용하는 system 프롬프트. CODE_POLICY_SYSTEM_PROMPT와 액션 스키마/안전 규칙은 동일하지만, "매 스텝 다시 호출되니 이번 한 스텝만 결정하면 된다"는 점을 명시

### HybridPolicy(Class, Policy 상속)

LiveCodePolicy(매 스텝 코드 재생성)와 CodePolicy(한 번 생성 후 고정 재사용)의 중간 지점. 평소엔 캐시된 코드를 그대로 실행해 LLM을 호출하지 않다가, 그 코드 스스로 {"type": "replan"}을 반환할 때만(상황이 바뀌어 더 이상 처리 못 할 때) LLM을 다시 불러 새로 판단한다. 또한 LLM은 매번 코드를 쓸 필요 없이, 그 자리에서 끝나는 단순한 행동이면 코드 없이 action(JSON) 하나만 답해도 된다 - "코드"는 복잡한 행동(추적/회피/다단계 조건)이 필요할 때만 쓰는 도구가 됨. OpenAI의 tools(function-calling) API는 전혀 쓰지 않고 텍스트만 파싱하므로 tool-calling 미지원 모델(OpenRouter 무료 모델 등)에서도 동작 - CodePolicy/LiveCodePolicy의 submit_policy_code 게이트와 달리 생성 자체는 그대로 평문이지만, 코드로 판단되면 실행만은 동일하게 policy_sandbox.run_decide_code()로 서브프로세스에서 이뤄짐(캐시된 코드도 매 스텝 새 서브프로세스에서 재실행 - 더 이상 컴파일된 함수를 프로세스 안에 들고 있지 않음).

- 변수

self.client : openai.OpenAI 클라이언트 인스턴스

self.model : 호출할 모델 이름

self.task_description : LLM에게 매번(직접 행동/코드 응답 요청 시) observation과 함께 전달하는 작업 설명

self.temperature : 응답 temperature (기본 0.2)

self.max_tokens : 응답의 최대 출력 토큰 수 (기본 1500)

self.extra_params : chat.completions.create()에 그대로 전달되는 프로바이더 전용 옵션 (dict)

self.sandbox_timeout : 코드 모드 decide() 실행을 위해 policy_sandbox.run_decide_code()에 넘기는 하드 타임아웃(초, 기본 5.0)

self.generated_code : 현재 캐시된 코드 원문 (str). 코드 모드가 아니면(직접 행동으로 응답 중이거나 아직 캐시가 없으면) None

self.last_error : 가장 최근 decide() 호출에서 발생한 예외/사유 (없으면 None)

- 함수

__init__(self, model: str, task_description: str, base_url: str = None, api_key: str = "not-needed", temperature: float = 0.2, max_tokens: int = 1500, extra_params: dict = None, sandbox_timeout: float = 5.0) -> None : client 생성 및 설정 저장

_ask_llm(self, observation: dict) -> str : HYBRID_POLICY_SYSTEM_PROMPT + task_description + 현재 observation(JSON)으로 LLM을 호출(max_tokens, extra_params 반영)해 응답 텍스트를 반환. finish_reason이 "length"이면 ValueError 발생

decide(self, observation: dict) -> dict : (1) 캐시된 generated_code가 있으면 policy_sandbox.run_decide_code()로 서브프로세스 실행 - 에러 없이 반환된 action이 {"type":"replan"}이 아니면 그대로 반환(LLM 호출 없음), 에러가 있거나 replan이면 캐시를 비우고(에러면 noop 반환, replan이면 이번 호출 안에서 바로 (2)로 진행). (2) 캐시가 없으면 _ask_llm()으로 응답을 받아 _extract_code()로 펜스를 벗긴 뒤, "def decide("가 포함돼 있으면 코드로 간주해 _safety_check_error()로 정적 검사 후 policy_sandbox.run_decide_code()로 첫 실행까지 해 보고(성공 + replan이 아니면) generated_code에 캐싱, 아니면 순수 JSON으로 간주해 json.loads() 후 그 action을 바로 반환. 반환값이 유효한 action(dict, "type" 포함)이 아니거나 안전성 검사/실행 중 오류가 나면 last_error에 기록하고 {"type": "noop"} 반환(캐시도 비움), 성공하면 last_error를 None으로 초기화

전역 상수 (모듈 레벨)

HYBRID_POLICY_SYSTEM_PROMPT : HybridPolicy가 사용하는 system 프롬프트. 매 응답을 "단순 행동 하나(JSON)" 또는 "재사용 가능한 decide() 코드(```python)" 중 하나로만 하도록 지시하고, 코드 안에서만 의미 있는 {"type": "replan"} 규약을 설명

---

## policy_sandbox.py

CodePolicy/LiveCodePolicy/HybridPolicy가 생성한 decide() 코드를 시뮬레이션 프로세스 안에서 직접 exec()하는 대신, 격리된 서브프로세스에서 하드 타임아웃과 함께 실행하기 위한 모듈. decide() 코드는 관찰(observation)만의 순수 함수여야 한다는 기존 설계 전제가 그대로 유지되므로(문서 앞부분 CodePolicy 설명 참고), 스텝마다 새 서브프로세스에서 다시 실행해도 잃는 것이 없다 - 대신 서브프로세스 기동 비용(수십 ms)을 스텝마다 지불하지만, 무한루프나 크래시가 나는 decide()가 자기 자신만 멈추게 하고 시뮬레이션 루프 전체를 절대 멈추지 못하게 하는 것과의 트레이드오프.

- 변수

HARNESS_PATH : _policy_harness.py의 절대 경로 (서브프로세스로 실행할 대상)

DEFAULT_TIMEOUT_SEC : run_decide_code()의 timeout 기본값 (5.0)

- 함수

run_decide_code(code: str, observation: dict, timeout: float = DEFAULT_TIMEOUT_SEC) -> dict : code와 observation을 임시 JSON 파일에 담아 `python -I -S _policy_harness.py <파일경로>`를 subprocess.run(timeout=timeout)으로 실행. 정상 종료하면 표준출력 마지막 줄을 JSON으로 파싱해 {"action": dict|None, "error": str|None}을 그대로 반환. subprocess.TimeoutExpired가 나면 {"action": None, "error": "timed out after {timeout}s ..."}, 비정상 종료(exit code != 0)면 stderr 일부를 담아 반환, 출력 파싱에 실패해도 에러로 반환. 임시 파일은 finally에서 항상 삭제

---

## _policy_harness.py

policy_sandbox.run_decide_code()가 `python -I -S`(isolated 모드, site 모듈 로드 안 함)로 실행하는 서브프로세스 진입점. 단독 실행/임포트 대상이 아니며, argv[1]에 담긴 JSON 파일 경로에서 {"code": ..., "observation": ...}를 읽어 decide()를 실행하고 결과 JSON 한 줄을 stdout에 출력한다.

policy.py의 _check_code_safety()와 동일한 정적 검사(ast 기반 - import문, __로 시작하는 이름/속성, exec/eval/open/__import__/compile/input 호출 금지)를 이 파일 안에도 독립적으로 복사해 두고 있다 - 생성 단계(submit_policy_code 게이트)의 검사를 우회하는 경로(예: 이미 캐시된 코드의 재실행)가 있어도 실행 시점에 한 번 더 걸러지도록 하는 이중 방어. 다만 이 정적 검사도, 아래의 제한된 builtins도 진짜 캡슐화된 샌드박스는 아니다 - 진짜 안전장치는 OS 수준: 별도의 소모성 프로세스로 실행되고 호출자가 하드 타임아웃을 걸어 두므로, 악성/버그 있는 decide()가 할 수 있는 최악의 일은 자기 자신을 멈추거나 죽이는 것뿐이며 시뮬레이션 프로세스에는 영향이 없다.

- 변수

SAFE_BUILTINS : 모듈 상수(dict). decide() 코드가 exec되는 스코프의 `__builtins__`로 주어지는, 허용된 이름만 담은 축소된 builtins (import 관련 이름 없음 - `__import__`가 없으므로 import 문이 있어도 정적 검사 전에 이미 막힘)

- 함수

_check_code_safety(code: str) -> None : policy.py의 동일 이름 함수와 같은 검사 (독립 사본 - 서브프로세스는 policy.py를 import하지 않음)

main() -> None : argv[1] JSON을 읽어 _check_code_safety() 통과 후 SAFE_BUILTINS(+math)만 있는 스코프 하나를 globals/locals 겸용으로 써서 code를 exec(그래야 코드 최상단에 둔 상수/보조 함수가 decide() 안에서 보임 - 둘을 나누면 NameError), scope에서 decide 함수를 찾아 observation으로 호출한 뒤 반환값을 검증(dict + "type" 필드 필수)해 {"action": ..., "error": None}을 stdout에 출력. 어느 단계에서든 예외가 나면 {"action": None, "error": "<예외타입>: <메시지>"}를 출력 (프로세스 자체는 정상 종료 - 타임아웃은 이 프로세스가 아니라 호출자인 policy_sandbox.py가 감지)

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

실제 물리 엔진이 준비되기 전까지 쓰는 자리표시자(placeholder) 기본 구현. 맵 경계로 좌표를 clamp하고, 벽(environment._walls())에 닿으면 그 직전에서 멈추며, 잠긴 문의 radius 안쪽으로는 진입을 막는 것 외에는 아무 충돌 처리도 하지 않음(에이전트끼리는 서로 통과 가능). 벽 등 정적 물리 구조는 world_core 쪽 물리 엔진이 맡을 영역이라 다루지 않음. Environment 생성 시 physics를 지정하지 않으면 기본값으로 사용됨.

- 함수

WALL_STANDOFF : 벽에 막혔을 때 벽면에서 띄워 멈추는 거리 (0.5, 클래스 상수)

resolve_move(self, environment, agent, dx: float, dy: float) -> tuple[float, float] : 새 좌표를 맵 경계 안으로 clamp하고, 이동 경로 중간에 벽이 있으면(_first_wall_hit - 한 번에 크게 움직여 벽을 뛰어넘는 경우 포함) 벽 직전(WALL_STANDOFF)까지만 이동시킨 뒤, _blocked_by_door()로 막히면 원래 좌표를 그대로 반환

_first_wall_hit(walls, x0: float, y0: float, x1: float, y1: float) -> float | None : (staticmethod) (x0, y0)->(x1, y1) 선분이 벽 안으로 처음 들어가는 지점의 비율 t(0~1), 안 부딪히면 None. 시작점이 이미 벽 내부면 그 벽은 무시(빠져나올 수 있게). 도착점이 벽 가장자리에 정확히 닿는 경우도 1.0(부딪힘)으로 처리 - 벽 표면 위에 서면 벽을 따라 미끄러지는 이동이 전부 막히기 때문

_blocked_by_door(self, environment, x: float, y: float) -> bool : 해당 좌표가 environment.objects 중 잠긴 문(locked)의 radius 안인지 판정

---

## agent.py

### Agent(Class)

- 변수

self.agent_id : 에이전트 고유 식별자

self.x : 에이전트의 x좌표 (연속값)

self.y : 에이전트의 y좌표 (연속값)

self.facing : 에이전트가 바라보는 방향 (도, 0~360). 0=오른쪽(+x), 90=아래(+y), 180=왼쪽, 270=위. move 시 이동 방향으로 자동 갱신되고, turn action으로 제자리에서 바꿀 수 있음 (Environment.move_agent/turn_agent)

self.view_radius : 에이전트의 시야 반경

self.view_angle : 에이전트의 시야각 (전체 폭, 도)

self.inventory : 에이전트가 보유한 아이템 목록

self.inbox : 에이전트가 수신한 메시지 목록

self.memory : 에이전트가 action에 "memory": {...}를 넣어 직접 남기는 메모장 (dict). 관찰의 memory로 돌려받음 (Environment._store_memory 참고)

self.policy : 에이전트에 탑재된 AI (policy.py의 Policy 구현체, 예: NoopPolicy, RandomPolicy, 추후 실제 AI)

self.rules : 이 에이전트에게만 적용되는 강제 규칙 목록 (list[Rule]), 환경 전역 규칙에 추가로 적용됨

- 함수

__init__(self, agent_id: str, x: float, y: float, facing: float = 0.0, view_radius: float = 100.0, view_angle: float = 90.0) -> None : 에이전트 기본 정보 정의

set_policy(self, policy: Policy) -> None : 에이전트에 AI(Policy 구현체)를 탑재

decide(self, observation: dict) -> dict : 탑재된 policy.decide(observation)을 호출해 action을 반환 (policy 없으면 {"type": "noop"})

add_rule(self, rule: Rule) -> None : 이 에이전트 전용 강제 규칙을 추가

---

## scoring.py

한 회차가 끝난 Environment의 event_log/decision_log를 읽어 점수를 매기는 모듈. 개인 점수(각 에이전트가 일으킨 이벤트별 가점/감점)와 단체 점수(클리어 여부, 클리어 시간, 헛된 시도 횟수)를 합산해 회차 총점을 만듦. 같은 항목을 반복해서 쌓는 것(레버를 계속 당기기, 판을 밟았다 내렸다 하기)을 막기 위해 개인 가점은 (에이전트, 이벤트 종류, 대상 오브젝트) 조합마다 한 번만 주고, 감점은 매번 적용.

- 모듈 상수

ATTEMPT_EFFECTS : 시도로 세는 상호작용 action type -> 그 시도가 성공했을 때 같은 step에 그 에이전트 이름으로 남는 이벤트 종류 집합 (dict[str, set[str]]). pick_up->item_picked_up, drop->item_dropped, use_key->door_unlocked, press_button->door_unlocked/door_locked, pull_lever->lever_pulled

### ScoreConfig(Class, dataclass)

점수 배점 설정. 모든 값은 생성 시 바꿀 수 있음 (예: ScoreConfig(trap_penalty=-50))

- 변수 (기본값)

seen_points = 1.0 : 물체를 처음 목격 (object_seen)

seen_points_by_type = {"clue": 3.0} : 목격 점수를 물체 type별로 다르게 줄 때 (없는 type은 seen_points)

pickup_points = 3.0 : normal 물품/열쇠 습득

coop_pickup_points = 8.0 : coop 물품 습득 (함께 들어준 에이전트도 같은 점수)

lever_points = 3.0 : 레버 당기기

door_unlock_points = 10.0 : 문 열기 (압력판이면 밟고 있던 전원)

plate_points = 2.0 : 압력판에 올라서기

portal_points = 1.0 : 포탈 사용

trap_penalty = -30.0 : trap 발동 (개인 감점, 매번)

clear_bonus = 50.0 : 클리어 시 단체 점수

time_bonus_max = 30.0 : 클리어 시간 보너스 최댓값. time_bonus_max * (1 - (clear_step - 1) / max_steps)로 1 step 클리어면 전부, 늦을수록 선형 감소

failed_attempt_penalty = -1.0 : 상태를 바꾸지 못한 상호작용 시도 1회당 단체 감점 (헛된 시도가 없으면 감점 0)

failed_attempt_penalty_cap = -20.0 : 헛된 시도 감점의 하한

- 함수 (모듈 레벨)

_target_of(event: dict) -> str | None : 이벤트의 대상 오브젝트 id (object_id/door_id/lever_id/plate_id/portal_id 중 있는 것). 중복 가점 판정 키로 사용

_individual_points(event: dict, config: ScoreConfig) -> tuple[float, str] | None : 이벤트 하나가 agent_ids의 각 에이전트에게 주는 (점수, 사유). 점수 대상이 아닌 이벤트(item_dropped, plate_left, door_locked, *_blocked 등)와 trap 물품의 item_picked_up(감점은 trap_triggered에서)은 None

_matches(event: dict, objective: dict) -> bool : objective(클리어 조건 dict)의 모든 키/값이 EventLog 항목에 그대로 있으면 True (예: {"type": "door_unlocked", "door_id": "gate"})

clear_step(events: list[dict], objectives: list[dict]) -> int | None : 모든 objective가 한 번씩 충족된 step(각 objective가 처음 충족된 step 중 가장 늦은 것). 하나라도 미충족이면 None. 회차 도중 조기 종료 판정(benchmark.run_episode)에도 사용

count_attempts(env) -> tuple[int, int] : decision_log의 final_action 중 ATTEMPT_EFFECTS에 있는 상호작용 시도 수와, 그중 같은 step에 대응 이벤트가 그 에이전트 이름으로 남지 않은 헛된 시도 수를 (attempts, failed)로 반환

score_episode(env, max_steps: int, objectives: list[dict], config: ScoreConfig = None) -> dict : 회차 점수 계산. objectives는 클리어 조건 목록(형식은 _matches 참고)으로, clear_step()이 돌려준 step을 클리어 시간으로 씀. 반환 형식:
{"agents": {agent_id: {"score", "items": [{"step", "reason", "target", "points"}]}}, "team": {"cleared", "clear_step", "clear_bonus", "time_bonus", "attempts", "failed_attempts", "attempt_penalty", "score"}, "individual_total", "total"}. total = individual_total + team.score

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

### EventLog(Class)

환경의 상태를 실제로 바꾼 사건과 그 사건을 일으킨 에이전트를 기록. DecisionLog가 "무엇을 하려 했나"라면 EventLog는 "실제로 무슨 일이 일어났고 누구 덕/탓인가"로, 마일스톤 기반 채점과 에이전트별 기여도(credit) 산정에 사용. 상태가 바뀌지 않은 시도(이미 열린 문에 열쇠 사용 등)는 기록하지 않고, 협력 판단에 의미 있는 실패(coop 물품 단독 습득/이동 시도)만 따로 기록함. Environment가 각 처리 지점에서 자동으로 기록함.

- 변수

self.entries : 기록된 사건 목록 (list[dict]). 각 항목은 {"step", "type", "agent_ids", ...사건별 필드}

- 이벤트 종류 (type: agent_ids의 의미 / 추가 필드)

object_seen : 그 물체를 처음 목격한 에이전트 / object_id, object_type. step()에서 에이전트가 실제로 받은 관찰 기준으로, 에이전트마다 물체당 한 번만 기록

plate_entered : 판에 올라선 에이전트 / plate_id

plate_left : 판에서 내려간 에이전트 / plate_id

door_unlocked : 문을 연 에이전트(압력판이면 그 순간 연결된 판들을 밟고 있던 전원) / door_id, cause("key"/"button"/"lever"/"pressure_plate"), source(원인 오브젝트 id, 압력판이면 연결된 plate_id 목록)

door_locked : 문을 닫은 에이전트(압력판이면 이번에 판에서 내려간 에이전트, trap이면 trap을 주운 에이전트) / door_id, cause("button"/"lever"/"pressure_plate"/"trap"), source

lever_pulled : 레버를 당긴 에이전트 / lever_id, on(당긴 뒤 상태). 연결된 문의 상태가 안 바뀌어도 기록

item_picked_up : 주운 에이전트(coop이면 함께 들어준 에이전트 포함) / object_id, object_type("item"/"key"), category, helper_ids(함께 들어준 에이전트만)

item_dropped : 내려놓은 에이전트 / object_id, position

pickup_blocked : coop 물품을 혼자 주우려다 실패한 에이전트 / object_id, reason("not_enough_helpers")

move_blocked : coop 물품을 들고 혼자 이동하려다 막힌 에이전트 / object_id, reason("not_enough_helpers")

portal_used : 순간이동한 에이전트 / portal_id, origin, dest

trap_triggered : trap을 주운 에이전트 / object_id, sealed_doors

- 함수

__init__(self) -> None : 빈 로그로 초기화

record(self, step: int, event_type: str, agent_ids: list[str], **fields) -> None : 사건 하나를 기록 (fields는 deep copy). agent_ids는 사건을 일으킨(공로/책임이 있는) 에이전트 목록

filter(self, event_type: str = None, agent_id: str = None, step: int = None) -> list[dict] : event_type/agent_id(agent_ids에 포함되는지)/step 중 지정한 조건만 만족하는 항목을 반환 (모두 생략하면 전체)

clear(self) -> None : 기록을 모두 비움

---

## enviroment.py

Agent(agent.py), MessageLog/DecisionLog/EventLog(history.py), PhysicsEngine(physics.py), Rule(rule.py)을 import해서 사용. 맵 자체는 만들지 않고 world_core.GameMap을 참조만 함.

- 모듈 상수 (add_item의 물품 분류)

ITEM_NORMAL = "normal" : 혼자 줍고 옮길 수 있는 일반 물품

ITEM_COOP = "coop" : 여러 명(required_agents)이 함께 있어야만 줍고 옮길 수 있는 물품

ITEM_TRAP = "trap" : 줍는 순간 지정된 문을 영구 봉인해 게임을 불가능하게 만드는 물품

ITEM_CATEGORIES : 위 세 값의 튜플 (add_item의 category 검증용)

### Environment(Class)

- 변수

self.game_map : 에이전트 이동 범위를 정의하는 맵 객체 (world_core.GameMap, 맵 자체는 environment에서 생성하지 않고 참조만 함)

self.agents : 환경에 등록된 에이전트 목록 (dict[str, Agent])

self.objects : 환경에 배치된 상호작용 가능한 물체 목록 (dict[str, dict], 다른 에이전트는 포함하지 않음). type이 "item"/"key"/"door"/"button"/"lever"/"pressure_plate"/"clue"/"portal", 또는 add_mover로 만든 임의의 type(기본 "hazard")

self.interact_radius : 문/버튼 등과 상호작용(use_key, press_button)할 수 있는 최대 거리

self.max_move : 한 번의 move로 갈 수 있는 최대 거리 (기본 20, None이면 제한 없음). 더 크게 요청하면 같은 방향으로 max_move만큼만 이동. 제한이 없으면 한 step에 맵을 가로지를 수 있어 클리어 시간 점수가 의미를 잃으므로 기본으로 제한

self._known : agent_id -> object_id -> 그 에이전트가 마지막으로 본 물체 상태 (dict[str, dict[str, dict]]). 관찰의 known_objects를 step 사이에 이어가기 위한 내부 변수

self.physics : 이동/충돌 계산을 위임할 physics.py의 PhysicsEngine 구현체. 생성 시 physics를 안 주면 SimplePhysicsEngine(자리표시자)을 기본으로 사용하며, 나중에 실제 물리 엔진이 준비되면 이 값만 교체하면 됨 (agent/policy/rule/tools는 그대로 유지)

self.rules : 모든 에이전트에게 동일하게 적용되는 전역 강제 규칙 목록 (list[Rule])

self.step_count : step()이 몇 번 실행됐는지 (1부터 증가). 메시지 기록에 시점을 남기는 용도

self.message_log : 오간 메시지를 전부 기록하는 history.py의 MessageLog 인스턴스 (반사실적 재현 분석용)

self.decision_log : 매 step 각 에이전트의 관찰/결정/실제 실행(Rule 적용 후)을 기록하는 history.py의 DecisionLog 인스턴스 (반사실적 재현 분석용)

self.failure : trap 물품이 발동해 게임이 불가능해진 경우 그 원인 {"step", "agent_id", "object_id", "sealed_doors"} (dict | None). 처음 발동한 trap만 기록됨. "누가 언제 실패를 확정지었나" 분석용

self._portals_inside : agent_id -> 그 에이전트가 현재 서 있는 portal_id 집합 (dict[str, set[str]]). 포탈이 진입 순간에만 발동하도록 이전 상태를 기억하는 내부 변수

self.event_log : 실제로 일어난 상태 변화와 그걸 일으킨 에이전트를 기록하는 history.py의 EventLog 인스턴스 (마일스톤 채점/에이전트별 기여도 산정용, 이벤트 종류는 EventLog 참고)

self._seen : agent_id -> 지금까지 그 에이전트의 관찰에 한 번이라도 나타난 object_id 집합 (dict[str, set[str]]). object_seen 이벤트를 물체당 한 번만 남기기 위한 내부 변수

self._plate_occupants : plate_id -> 지난 판정 때 그 판 위에 서 있던 agent_id 집합 (dict[str, set[str]]). plate_entered/plate_left 이벤트와 압력판 문을 닫은 원인(이탈한 에이전트)을 판정하기 위한 내부 변수

- 함수

__init__(self, game_map, interact_radius: float = 15.0, physics: PhysicsEngine = None, max_move: float | None = 20.0) -> None : 환경 초기화, 맵 객체 연결, physics 미지정 시 SimplePhysicsEngine() 사용, max_move로 한 번의 이동 거리 제한

add_agent(self, agent_id: str, x: float, y: float, facing: float = 0.0, view_radius: float = 100.0, view_angle: float = 90.0, policy=None, rules: list[Rule] = None) -> Agent : 새 에이전트를 환경에 등록(원하면 policy와 에이전트별 rules 동시 지정)하고 생성된 Agent 반환. 시작 위치가 포탈 위여도 바로 순간이동되지 않도록 self._portals_inside를 초기화

remove_agent(self, agent_id: str) -> None : 에이전트를 환경에서 제거

add_rule(self, rule: Rule) -> None : 모든 에이전트에게 적용되는 전역 규칙 추가

add_agent_rule(self, agent_id: str, rule: Rule) -> None : 특정 에이전트에게만 적용되는 규칙 추가

set_hierarchy(self, commander_id: str, subordinate_ids: list[str]) -> None : 중심-주변 구조 설정 편의 함수. subordinate_ids 각각에 ObeyCommandRule(commander_id)를 걸어, commander_id의 명령을 무조건 따르게 만듦. 호출하지 않으면 기존처럼 모든 에이전트가 동등한 구조

_enforce_rules(self, agent: Agent, observation: dict, action: dict) -> dict : 전역 규칙 → 해당 에이전트 전용 규칙 순서로 action을 통과시켜 최종 action을 반환

turn_agent(self, agent_id: str, facing: float) -> None : 제자리에서 바라보는 방향만 facing(도, 360으로 나눈 나머지로 정규화)으로 바꿈. 시야가 facing 중심의 부채꼴이므로 주변을 둘러볼 때 사용. apply_action의 {"type": "turn", "facing": ..}이 호출함

move_agent(self, agent_id: str, dx: float, dy: float) -> None : 에이전트 이동을 self.physics.resolve_move()에 위임하고 그 결과 좌표를 적용 (실제 경계/충돌 계산은 physics.py 참고). coop 물품을 들고 있는데 주변(interact_radius)에 required_agents명(본인 포함)이 없으면 이동하지 않음. 이동 후 _check_portals()로 포탈 진입을 판정. coop 때문에 막히면 move_blocked 이벤트 기록. dx/dy가 0이 아니면 이동 방향(atan2(dy, dx))으로 facing을 먼저 갱신 - 막혀서 실제로 못 움직여도 그 방향을 돌아봄. 요청한 (dx, dy)의 길이가 max_move보다 크면 같은 방향으로 max_move만큼으로 줄인 뒤 처리

add_object(self, object_id: str, x: float, y: float, object_type: str = "item") -> None : 환경에 일반 상호작용 물체 배치 (category가 없으므로 normal 물품으로 취급)

add_item(self, item_id: str, x: float, y: float, category: str = ITEM_NORMAL, required_agents: int = 2, seals: list[str] = None, disguised: bool = False) -> None : 분류가 있는 물품(type "item") 배치. category가 ITEM_CATEGORIES에 없으면 ValueError. normal은 혼자 다룰 수 있음. coop은 required_agents명(본인 포함)이 물품의 interact_radius 안에 있어야 주울 수 있고, 들고 있는 동안에도 그만큼 곁에 있어야 이동 가능. trap은 줍는 순간 seals의 문들을 잠그고 영구 봉인(sealed)하며 self.failure에 원인을 기록. disguised=True인 trap은 관찰(visible_objects/inventory)에 category "normal"로 보이고 seals/disguised 필드가 숨겨짐

_helpers_near(self, agent: Agent, x: float, y: float) -> list[str] : (x, y)의 interact_radius 안에 있는, agent 본인을 제외한 다른 에이전트 id 목록 (coop 물품용 - 본인 포함 인원은 len()+1)

_log(self, event_type: str, agent_ids: list[str], **fields) -> None : 현재 step_count로 self.event_log에 기록하는 단축 함수

_trigger_trap(self, agent_id: str, trap: dict) -> None : trap_triggered 이벤트를 기록한 뒤 trap의 seals 문들을 잠그고 sealed=True로 표시, self.failure가 비어 있으면 원인 기록

_set_door_locked(self, door: dict, locked: bool, cause: str, agent_ids: list[str], source) -> None : 문의 잠금 상태 변경. sealed 문이면 아무것도 하지 않음 - use_key/press_button/pull_lever/_update_pressure_plates/_trigger_trap이 모두 이 함수를 거치므로 봉인된 문은 어떤 수단으로도 열리지 않음. 상태가 실제로 바뀐 경우에만 door_unlocked/door_locked 이벤트를 cause/agent_ids/source와 함께 기록

add_portal(self, portal_id: str, x: float, y: float, dest_x: float, dest_y: float, radius: float = 10.0) -> None : 포탈 배치. 별도 action 없이 이동으로 radius 안에 진입하는 순간 (dest_x, dest_y)로 순간이동. 진입 시점에만 발동하므로 포탈 위에 계속 서 있거나 도착 지점이 다른 포탈 위여도 연쇄/왕복 이동이 없음(벗어났다 다시 들어와야 재발동). 목적지가 잠긴 문의 radius 안이면 발동하지 않음. 두 포탈을 서로의 위치로 연결하면 양방향 포탈이 됨

_portals_at(self, x: float, y: float) -> set[str] : (x, y)를 radius 안에 포함하는 portal_id 집합

_check_portals(self, agent: Agent) -> None : 이번에 새로 진입한 포탈이 있으면 순간이동시키고(portal_used 이벤트 기록) self._portals_inside 갱신

remove_object(self, object_id: str) -> None : 환경에서 물체 제거

pick_up(self, agent_id: str, object_id: str) -> None : 에이전트가 근처(interact_radius 이내)의 물체(item/key만 가능, door/button/lever/pressure_plate/portal 불가)를 습득, objects에서 제거하고 inventory에 추가. coop 물품은 required_agents명이 곁에 없으면 실패(조용히 무시), trap 물품은 습득 직후 _trigger_trap() 발동. object_id가 존재하지 않거나 None이면 조용히 무시(예외 없음) 습득 성공 시 item_picked_up 이벤트(coop이면 곁에 있던 에이전트를 helper_ids와 agent_ids에 포함), coop 인원 부족으로 실패 시 pickup_blocked 이벤트 기록

drop(self, agent_id: str, object_id: str) -> None : 에이전트가 물체를 내려놓음, inventory에서 제거하고 현재 위치의 objects에 추가. object_id가 inventory에 없으면 조용히 무시(예외 없음). 내려놓으면 item_dropped 이벤트 기록

add_door(self, door_id: str, x: float, y: float, locked: bool = True, radius: float = 10.0, hidden: bool = False) -> None : 문 배치. locked면 radius 반경 안으로 이동 불가, hidden이면 아주 가까이 가야 관찰에 드러나는 "숨겨진 문"

add_key(self, key_id: str, x: float, y: float, unlocks: str) -> None : 특정 door_id(unlocks)를 여는 열쇠 배치

add_button(self, button_id: str, x: float, y: float, linked_door_id: str) -> None : 특정 door_id(linked_door_id)와 연결된 버튼 배치

add_lever(self, lever_id: str, x: float, y: float, linked_door_ids: list[str]) -> None : 레버 배치. 버튼과 달리 on/off 상태를 유지하며, 여러 door_id(linked_door_ids)를 한 번에 제어 가능

add_pressure_plate(self, plate_id: str, x: float, y: float, linked_door_id: str, radius: float = 10.0) -> None : 압력판 배치. 별도 action 없이 매 step마다 자동 판정되는 수동 트리거형 장치. 같은 linked_door_id로 여러 판을 배치하면(예: 서로 떨어진 위치에 하나씩) 그 문은 연결된 판 전부가 동시에 밟혀야만 열림(AND 조건) - 여러 에이전트가 동시에 협력해야 하는 상황을 만들 때 사용

add_clue(self, clue_id: str, x: float, y: float, content, hidden: bool = True) -> None : 정보 오브젝트 배치. content는 실험 설계자가 정의하는 임의의 값(문자열/딕셔너리 등)으로 게임 로직에는 아무 영향 없이 observation에 그대로 노출됨. hidden=True(기본값)면 add_door의 hidden 오브젝트와 동일하게 interact_radius 안까지 가야만 관찰에 나타나므로, 한 에이전트만 우연히 발견하고 나머지는 메시지로 전달받아야만 아는 정보 비대칭 상황을 만들 수 있음. hidden=False면 일반 물체처럼 시야각 안에서 멀리서도 보임

add_mover(self, mover_id: str, x: float, y: float, waypoints: list[tuple[float, float]], speed: float = 5.0, object_type: str = "hazard", loop: bool = True, extra: dict = None) -> None : waypoints를 순서대로 순회하며 매 step마다 자동으로 위치가 갱신되는 오브젝트 배치(물리적 충돌/차단은 없음 - 정적/동적 충돌 구조는 world_core 물리 엔진의 몫). object_type은 원하는 값 아무거나 가능(기본 "hazard"), extra로 추가 필드(dict)를 오브젝트에 병합 가능(예: 움직이는 열쇠를 만들려면 object_type="key", extra={"unlocks": "d1"}). 목표가 매 스텝 위치를 바꾸므로, 한 번의 판단이 아니라 추적/예측하는 반복문·조건문(코드)이 있어야 따라잡을 수 있는 상황을 만들 수 있음

use_key(self, agent_id: str, key_object_id: str) -> None : 인벤토리의 열쇠를 사용해 근처의 대응 문을 잠금 해제, 열쇠는 소모됨. 거리 판정은 문 중심이 아니라 문의 가장자리 기준(interact_radius + door["radius"] 이내)으로 함 - _blocked_by_door가 잠긴 문의 radius 안쪽 진입 자체를 막으므로, 중심 기준으로만 재면 door["radius"] >= interact_radius일 때 영원히 도달 불가능한 상태가 됨. 문 상태 변경은 _set_door_locked()를 거치므로 trap으로 봉인(sealed)된 문은 변하지 않음

press_button(self, agent_id: str, button_id: str) -> None : 근처(interact_radius 이내) 버튼을 눌러 연결된 문의 잠금 상태를 토글. 문 상태 변경은 _set_door_locked()를 거치므로 trap으로 봉인(sealed)된 문은 변하지 않음

pull_lever(self, agent_id: str, lever_id: str) -> None : 근처(interact_radius 이내) 레버를 당겨 on/off 상태를 뒤집고, linked_door_ids의 모든 문 잠금 상태를 그 상태(on=잠금 해제)에 맞춤. 문 상태 변경은 _set_door_locked()를 거치므로 trap으로 봉인(sealed)된 문은 변하지 않음. 당길 때마다 lever_pulled 이벤트 기록

_update_pressure_plates(self) -> None : 모든 pressure_plate에 대해 radius 안에 서 있는 에이전트가 있는지 판정한 뒤, 같은 linked_door_id를 공유하는 판들의 점유 여부를 AND로 묶어 그 문을 잠금/해제. 판이 하나뿐인 문은 기존과 동일(점유 시 해제, 아니면 잠금), 여러 판이 연결된 문은 전부 동시에 점유돼야만 해제됨. step()의 마지막(모든 행동 적용 후)에 자동 호출됨 (에이전트의 action 없이 동작). 문 상태 변경은 _set_door_locked()를 거치므로 trap으로 봉인(sealed)된 문은 변하지 않음. 판마다 올라서고 내려간 에이전트를 plate_entered/plate_left 이벤트로 기록하고, 문이 열리면 연결된 판들을 밟고 있던 전원을, 닫히면 이번에 판에서 내려간 에이전트를 door_unlocked/door_locked의 agent_ids로 기록

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

_is_visible(self, agent: Agent, obj_x: float, obj_y: float) -> bool : 해당 좌표가 에이전트의 시야(반경 view_radius + 시야각 view_angle, facing 기준) 안에 있고 벽에 가려지지 않았는지(_has_line_of_sight) 판정

_walls(self) -> list[tuple[float, float, float, float]] : 시야를 가리는 벽 목록을 (x, y, width, height)로 반환. 벽은 world_core 담당이므로 self.game_map.walls를 읽기만 함 - 항목은 world_core.Wall처럼 .rect(pygame.Rect)를 가지거나 .x/.y/.width/.height를 직접 가진 객체. game_map에 walls가 없거나 비어 있으면 가리는 것 없음

_has_line_of_sight(self, x0: float, y0: float, x1: float, y1: float) -> bool : (x0, y0)에서 (x1, y1)까지의 선분이 어떤 벽 내부도 통과하지 않으면 True (Liang-Barsky 선분 클리핑). 선분 끝이 벽 가장자리에 닿거나 모서리를 스치는 것은 가린 것으로 치지 않고, 끝점이 벽 내부에 있으면 가린 것으로 침

get_observation(self, agent_id: str) -> dict : 에이전트의 관찰 생성. 자신의 위치/방향/inventory, 시야 내 물체 목록(숨겨진 문은 interact_radius 이내에서만 노출, 일반/숨겨진 물체 모두 벽에 가려지면 제외), inbox만 포함하며 다른 에이전트 정보는 제공하지 않음 (협력 평가를 위해 의도적으로 배제). inventory와 visible_objects는 _disguise()를 거친 deep copy로 반환(policy/생성된 코드가 observation을 직접 mutate해서 pick_up/use_key 등을 거치지 않고 환경을 조작하는 것을 막기 위함, 위장된 trap은 normal로 보임). inbox는 목록만 복사하고 메시지 객체는 공유(동시 실행 중 같은 step에 도착한 메시지가 이미 만든 관찰에 끼어들지 않게 하면서도, ObeyCommandRule이 표시하는 message["handled"]=True는 실제 inbox에 반영되도록). 메시지마다 전달 시점 "step"이 붙어 있음. 추가 필드: self.step(현재 step_count)/self.map_width/self.map_height, known_objects(지금까지 본 모든 물체의 마지막 상태 + last_seen_step - 저장된 _known에 지금 보이는 것을 덮어써 계산만 하고, 저장은 _record_sightings가 함), walls(_walls_near로 구한 시야 반경 안에 걸친 벽 [x, y, width, height] - 벽은 이동을 막으므로 길찾기용), memory(agent.memory 사본). CodePolicy 코드는 매 step 새 프로세스에서 실행되어 스스로 기억을 못 하므로 known_objects/memory로 기억을 제공

_walls_near(self, x: float, y: float, radius: float) -> list[list[float]] : (x, y)에서 radius 안에 일부라도 걸친 벽 목록 [x, y, width, height]

_record_sightings(self, agent_id: str, observation: dict) -> None : observation의 visible_objects 중 그 에이전트가 처음 보는 물체마다 object_seen 이벤트 기록. step()에서만 호출됨(apply_action 안의 Rule 검사용 관찰은 에이전트에게 전달되지 않으므로 세지 않음). 관찰의 known_objects를 self._known에 저장해 다음 step으로 이어감

_disguise(self, obj: dict) -> dict : obj의 deep copy 반환. disguised=True인 trap이면 category를 "normal"로 바꾸고 seals/disguised 필드를 제거

apply_action(self, agent_id: str, action: dict, observation: dict = None) -> dict : action을 _enforce_rules()로 먼저 강제 검사/교체한 뒤(ObeyCommandRule이 걸려 있으면 여기서 명령으로 치환됨. 규칙 검사에는 observation을 쓰며, 생략하면 지금 상태로 새로 만듦 - step()은 결정에 쓴 step 시작 시점의 관찰을 넘김), _is_well_formed()로 필드 타입(dx/dy/facing은 유한한 실수, object_id 등 id는 문자열)을 확인해 잘못됐으면 invalid_action 이벤트를 남기고 noop으로 처리, 아니면 move/turn/pick_up/drop/use_key/press_button/pull_lever/send_message/share_belief/request_info/confirm/claim_role/claim_task/issue_command 중 해당 처리로 라우팅. step() 없이 직접 호출해도 규칙은 항상 적용됨. 강제 적용 후 실제로 실행된 action을 반환(step()이 이 값을 DecisionLog에 final_action으로 기록)

step(self) -> None : 한 틱을 동시 실행으로 진행. step_count를 1 증가시키고 _update_movers()로 움직이는 오브젝트를 갱신한 뒤, (1) 모든 에이전트의 관찰을 같은 시점에 만들고(_record_sightings()로 목격 이벤트 기록) (2) 각 policy의 decide()를 스레드로 병렬 호출해 행동을 정하고 (3) 그 행동들을 apply_action(결정에 쓴 관찰을 넘김)으로 적용하고(_store_memory()로 memory 저장, decision_log에 observation/action/final_action 기록) (4) 마지막에 _update_pressure_plates()로 압력판을 판정. 따라서 이번 step에 보낸 메시지는 상대가 다음 step 관찰에서 처음 보고, 압력판은 올라선 그 step에 바로 문을 엶. 같은 물건을 동시에 집는 것처럼 적용 순서가 결과를 가르는 충돌이 있어, 적용 순서를 step마다 한 칸씩 돌림(step_count % 에이전트 수만큼 회전 - 결정적이라 재현 가능)

MEMORY_MAX_CHARS : 저장할 수 있는 memory의 최대 크기 (JSON 직렬화 20000자, 클래스 상수)

_store_memory(self, agent_id: str, action) -> None : policy가 고른 원래 action(Rule이 바꿔치기해도 원래 것 기준)에 "memory": dict가 있으면 agent.memory로 저장. dict가 아니거나 직렬화가 안 되거나 MEMORY_MAX_CHARS를 넘으면 무시
