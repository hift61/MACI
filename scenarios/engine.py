"""ScenarioEnvironment: 시나리오 맵 전용 물체와 환경 규칙을 더한 Environment.

기존 Environment(enviroment/enviroment.py)를 상속만 하고 원본은 고치지 않음. 맵 JSON(MapSpec)의
objects 항목 kind가 아래 add_<kind> 이름과 같으면 mapgen.builder가 그대로 배치함.

새 물체 (kind -> 관찰에 보이는 type)
  goal_zone      -> "goal_zone"     사각형 구역. 에이전트 전원이 동시에 안에 있으면 team_assembled 이벤트
  switch_plate   -> "switch_plate"  밟고 있는 동안 opens의 문을 엶. 같은 문에 여러 개면 하나만 밟아도 됨(OR)
  latch_lever    -> "lever"         당기면 doors를 영구히 엶 (switch_plate가 다시 잠그지 못함)
  logic_door     -> "door"          숨은 배선: 연결된 레버 중 ON 개수가 홀수면 열림 (배선은 관찰에 안 보임)
  switch_lever   -> "lever"         logic_door용 레버. 당긴 뒤 cooldown step 동안 다시 못 당김(ready_at_step)
  keypad         -> "keypad"        버튼 입력을 받는 패널. mode "sequence"(순서 맞추기) / "mastermind"(결과를 display에)
  keypad_button  -> "button"        keypad의 버튼 (press_button으로 누름, 필드 panel/label)
  display        -> "display"       엔진이 content를 갱신하는 화면 (keypad 결과 등)
  sync_pad       -> "sync_pad"      같은 group의 판들을 tolerance step 이내에 함께 밟아야 성공. 혼자 밟으면 밀려남
  periodic_door  -> "door"          정해진 주기로 저절로 열리고 닫히는 문 (주기는 관찰에 안 보임)
  bonus_item     -> "item"          주우면 개인 보너스 점수(points). expires_at step이 되면 사라짐
  spawner        -> (관찰에 없음)    area 안에 every step마다 부품/보너스 아이템을 만들어 냄
  receptacle     -> "receptacle"    반경 안에 accepts 접두사의 아이템을 내려놓으면 회수(item_delivered)
  checkpoint     -> "checkpoint"    누구든 반경 안에 들어가면 visited. 전부 방문하면 all_checkpoints_visited
  variant_clue   -> "clue"          에이전트마다 다른 내용이 보이는 단서 (관찰 노이즈 시나리오)
  push_block     -> "block"         단단한 블록. required명이 같은 step에 같은 방향으로 밀어야 push_distance만큼 움직임
  block_target   -> "block_target"  블록이 올라가면 filled. 전부 채워지면 all_targets_filled
  reset_lever    -> "lever"         당기면 blocks를 처음 자리로 되돌림 (구석에 끼인 블록 구제)
  station        -> "station"       input 접두사 아이템을 내려놓으면 process_steps 뒤 output 아이템을 만들어 냄
  cargo          -> "item"          한 사람이 hold_limit step 넘게 들고 있으면 원위치로 돌아감. 들고 있으면 carry_speed로 느려짐
  weighted_item  -> "item"          숨은 무게(_weight)가 있는 물건 (scale로만 잴 수 있음)
  scale          -> "scale"         반경 안 물건 무게 합을 reading에 표시. target이 있으면 too light/too heavy/balanced만 표시
  capacity_zone  -> "capacity_zone" 동시에 capacity명보다 많이 들어오면 안에 있던 전원을 들어오기 전 자리로 되돌림
  chest          -> "chest"         use_key(unlocks=chest id)로 여는 상자. 열리면 contents가 그 자리에 나옴
  coin           -> "item"          동전 (coin: true, value). 회차가 끝날 때 들고 있던 동전 가치가 개인 점수
  marker         -> "marker"        동작 없는 바닥 표시 (label). 물건을 올려 신호로 쓰는 용도
  (goal_zone에 agents=[...]를 주면 그 에이전트들만 모이면 됨, receptacle에 opens=[...]를 주면 목표 수 도달 시 문을 엶,
   keypad에 operators=[...]를 주면 그 에이전트만 누를 수 있음)
  (add_mover에 extra={"_hide_path": True}를 주면 움직이는 물체의 경로(waypoints)가 관찰에서 빠짐)

환경 규칙 (MapSpec.rules)
  glass_walls: [[x, y, w, h], ...]  이동은 막지만 시야는 막지 않는 벽
  message_loss: 0~1                 메시지가 이 확률로 사라짐 (조용히, message_lost 이벤트만 남음)
  message_delay: [min, max]         메시지가 이 범위의 step만큼 늦게 도착
  message_max_chars: N              메시지 본문이 N자를 넘으면 전송 거부 (보낸 쪽 inbox에 system 알림)
  message_interval: N               한 에이전트가 N step에 한 번만 메시지를 보낼 수 있음 (위와 같이 거부)
  message_disabled: true            메시지를 아예 보낼 수 없음 (위와 같이 거부)
  seed: int                         손실/지연/스폰 난수 시드 (MapSpec.seed에 더해짐)
  show_reward: bool                 benchmark가 누적 점수를 관찰(reward)에 넣어 피드백으로 줌
  stages: [단계, ...]               순서대로 깨야 하는 단계형 맵 (아래 "단계" 참고)

단계 (rules["stages"]) - 각 단계는 {"title", "briefing", "objectives": [이벤트 조건, ...],
  "objects": [MapSpec objects 항목], "walls": [[x, y, w, h], ...](생략하면 맵 벽), "agents": {id: [x, y, facing]}
  (생략하면 맵 시작 위치)}. 단계의 objectives(EventLog 항목과 비교, scoring._matches 형식)가 그 단계 안에서 모두
  충족되면 level_completed(level=번호)를 남기고, 그 단계 물체를 치운 뒤 에이전트를 시작 위치로 돌려놓고 다음 단계를
  불러옴(level_started). 마지막 단계를 깨면 all_stages_completed - 단계형 맵의 클리어 조건. 대화와 메모리는
  유지하고 정책 코드만 다시 짜게 함. 관찰의 "stage"에 현재 단계 번호/전체 수/제목/안내가 들어감.

이름이 "_"로 시작하는 필드는 비밀 값(정답 코드, 배선, 주기 등)이라 관찰에서 지움 (_disguise).
실패(영구 봉인) 상태는 만들지 않음 - 틀리면 리셋/밀려남/대기로만 대가를 치름.
"""
import copy
import math
import os
import random
import sys

ENVIRONMENT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "enviroment")
if ENVIRONMENT_DIR not in sys.path:
    sys.path.insert(0, ENVIRONMENT_DIR)  # enviroment/*.py use flat sibling imports

from enviroment import Environment, ITEM_NORMAL  # noqa: E402
from physics import SimplePhysicsEngine  # noqa: E402

MESSAGE_ACTIONS = ("send_message", "share_belief", "request_info", "confirm",
                   "claim_role", "claim_task", "issue_command")
PLATE_TYPES = ("pressure_plate", "switch_plate", "sync_pad")


class _StageWall:
    def __init__(self, x, y, width, height) -> None:
        self.x, self.y, self.width, self.height = x, y, width, height


# event가 condition의 모든 키/값을 그대로 가지면 충족 (scoring._matches와 같은 규칙)
def _matches(event: dict, condition: dict) -> bool:
    return all(event.get(key) == value for key, value in condition.items())


# 기본 물리(벽/잠긴 문/경계) + 블록(push_block)도 단단한 원으로 취급. 블록 안에서 바깥쪽으로는 나갈 수 있음
class ScenarioPhysics(SimplePhysicsEngine):
    def resolve_move(self, environment, agent, dx, dy):
        new_x, new_y = super().resolve_move(environment, agent, dx, dy)
        blocks = [o for o in environment.objects.values() if o["type"] == "block"]
        t = circle_hit(blocks, agent.x, agent.y, new_x, new_y)
        if t is None:
            return new_x, new_y
        length = math.hypot(new_x - agent.x, new_y - agent.y)
        t = max(0.0, t - self.WALL_STANDOFF / length) if length > 0 else 0.0
        return agent.x + (new_x - agent.x) * t, agent.y + (new_y - agent.y) * t


# (x0, y0)->(x1, y1) 선분이 circles(각각 x, y, radius) 중 하나에 처음 들어가는 비율 t. 없으면 None
def circle_hit(circles, x0, y0, x1, y1):
    dx, dy = x1 - x0, y1 - y0
    length2 = dx * dx + dy * dy
    if length2 == 0:
        return None
    first = None
    for c in circles:
        ox, oy = x0 - c["x"], y0 - c["y"]
        inside = ox * ox + oy * oy - c["radius"] ** 2
        projection = ox * dx + oy * dy
        if inside <= 0:
            if projection >= 0:
                continue  # 안에서 바깥쪽으로 나가는 중
            hit = 0.0
        else:
            disc = projection * projection - length2 * inside
            if disc < 0:
                continue
            hit = (-projection - math.sqrt(disc)) / length2
            if not 0 <= hit <= 1:
                continue
        first = hit if first is None else min(first, hit)
    return first


class ScenarioEnvironment(Environment):
    def __init__(self, game_map, rules: dict = None, seed: int = 0, **kwargs) -> None:
        super().__init__(game_map, **kwargs)
        if "physics" not in kwargs:
            self.physics = ScenarioPhysics()
        self.scenario_rules = dict(rules or {})  # self.rules는 기존 Rule 객체 목록이라 이름을 따로 씀
        self._rng = random.Random(seed * 1000 + int(self.scenario_rules.get("seed", 0)))
        self.glass_walls = [tuple(w) for w in self.scenario_rules.get("glass_walls", [])]
        self._pending_messages: list[tuple[int, str, dict]] = []  # (도착 step, 받는 agent_id, 메시지)
        self._last_sent: dict[str, int] = {}
        self._switch_occupants: dict[str, set[str]] = {}
        self._sync: dict[str, dict] = {}       # group -> {"entries": {pad_id: step}, "solved", "disabled_until"}
        self._sync_inside: dict[str, set[str]] = {}
        self._assembled: set[str] = set()      # 이미 team_assembled가 난 zone_id
        self._spawners: list[dict] = []
        self._all_visited_logged = False
        self.travel: dict[str, float] = {}     # agent_id -> 실제 이동 거리 합
        self.hold_steps: dict[str, int] = {}   # agent_id -> 판(압력판/스위치판) 위에 있었던 step 수
        self.message_stats = {"lost": 0, "delayed": 0, "blocked": 0}
        self.stages = list(self.scenario_rules.get("stages", []))
        self.stage_index = None   # 현재 단계 번호(0부터). 단계형 맵이 아니면 None, 다 깨면 len(stages)
        self._stage_ids: list[str] = []
        self._stage_event_start = 0
        self._pushes: dict[str, list[tuple[str, float]]] = {}  # block_id -> 이번 step에 민 (agent_id, facing)
        self._targets_logged = False
        self._jobs: list[dict] = []            # station 가공 대기열 {"finish", "station", "output"}
        self._outside: dict[str, tuple] = {}   # agent_id -> capacity_zone 밖에 있던 마지막 위치
        self._balanced: set[str] = set()       # 이미 scale_balanced가 난 scale_id

    # ------------------------------------------------------------------ 벽/시야

    def _opaque_walls(self):
        return Environment._walls(self)

    # 이동(physics)과 관찰의 walls 목록에는 유리벽도 포함
    def _walls(self):
        return self._opaque_walls() + list(self.glass_walls)

    # 시야는 불투명 벽만 가림 (Environment._has_line_of_sight와 같은 계산, 벽 목록만 다름)
    def _has_line_of_sight(self, x0, y0, x1, y1) -> bool:
        dx, dy = x1 - x0, y1 - y0
        eps = 1e-6
        for wx, wy, ww, wh in self._opaque_walls():
            t_enter, t_exit = 0.0, 1.0
            for p, q in ((-dx, x0 - wx), (dx, wx + ww - x0), (-dy, y0 - wy), (dy, wy + wh - y0)):
                if p == 0:
                    if q < 0:
                        t_enter, t_exit = 1.0, 0.0
                        break
                    continue
                t = q / p
                if p < 0:
                    t_enter = max(t_enter, t)
                else:
                    t_exit = min(t_exit, t)
            if t_exit - t_enter > eps and t_enter < 1 - eps and t_exit > eps:
                return False
        return True

    # ------------------------------------------------------------------ 물체 배치

    # agents: 모여야 하는 에이전트 id 목록 (None이면 전원)
    def add_goal_zone(self, zone_id, x, y, width, height, label="", agents=None) -> None:
        self.objects[zone_id] = {"object_id": zone_id, "x": x, "y": y, "type": "goal_zone",
                                 "width": width, "height": height, "label": label,
                                 "agents": list(agents) if agents else None}

    def add_switch_plate(self, plate_id, x, y, opens, radius=10.0) -> None:
        self.objects[plate_id] = {"object_id": plate_id, "x": x, "y": y, "type": "switch_plate",
                                  "opens": list(opens), "radius": radius}

    def add_latch_lever(self, lever_id, x, y, doors) -> None:
        self.objects[lever_id] = {"object_id": lever_id, "x": x, "y": y, "type": "lever", "on": False,
                                  "linked_door_ids": list(doors), "latch": True}

    def add_logic_door(self, door_id, x, y, levers, parity=1, radius=12.0) -> None:
        self.add_door(door_id, x, y, locked=True, radius=radius)
        self.objects[door_id].update({"_levers": list(levers), "_parity": parity})

    def add_switch_lever(self, lever_id, x, y, cooldown=0, label="") -> None:
        self.objects[lever_id] = {"object_id": lever_id, "x": x, "y": y, "type": "lever", "on": False,
                                  "linked_door_ids": [], "label": label, "cooldown": cooldown, "ready_at_step": 0}

    # operators: 이 패널을 누를 수 있는 에이전트 id 목록 (None이면 누구나)
    def add_keypad(self, panel_id, x, y, code, mode="sequence", display_id=None, opens=None, label="",
                   operators=None) -> None:
        if mode not in ("sequence", "mastermind"):
            raise ValueError(f"unknown keypad mode: {mode!r}")
        self.objects[panel_id] = {"object_id": panel_id, "x": x, "y": y, "type": "keypad", "label": label,
                                  "mode": mode, "length": len(code), "entered": [], "attempts": 0,
                                  "solved": False, "operators": list(operators) if operators else None,
                                  "_code": list(code), "_display": display_id, "_opens": list(opens or [])}

    def add_keypad_button(self, button_id, x, y, panel, label) -> None:
        self.objects[button_id] = {"object_id": button_id, "x": x, "y": y, "type": "button",
                                   "panel": panel, "label": label}

    def add_display(self, display_id, x, y, content=None, label="") -> None:
        self.objects[display_id] = {"object_id": display_id, "x": x, "y": y, "type": "display",
                                    "label": label, "content": copy.deepcopy(content)}

    def add_sync_pad(self, pad_id, x, y, group, radius=10.0, tolerance=0, return_x=None, return_y=None,
                     cooldown=3, opens=None) -> None:
        self.objects[pad_id] = {"object_id": pad_id, "x": x, "y": y, "type": "sync_pad", "group": group,
                                "radius": radius, "armed": True,
                                "_tolerance": tolerance, "_return": (return_x, return_y),
                                "_cooldown": cooldown, "_opens": list(opens or [])}
        self._sync.setdefault(group, {"entries": {}, "solved": False, "disabled_until": 0})

    def add_periodic_door(self, door_id, x, y, period, open_steps, phase=0, radius=12.0) -> None:
        self.add_door(door_id, x, y, locked=True, radius=radius)
        self.objects[door_id].update({"_period": period, "_open_steps": open_steps, "_phase": phase})

    def add_bonus_item(self, item_id, x, y, points=10.0, expires_at=None) -> None:
        self.add_item(item_id, x, y, category=ITEM_NORMAL)
        self.objects[item_id].update({"bonus": True, "expires_at": expires_at, "_points": points})

    # x, y는 builder 형식을 맞추기 위한 값일 뿐 쓰이지 않음. area = [x0, y0, x1, y1]
    def add_spawner(self, spawner_id, x, y, area, every, max_alive, prefix, points=0.0, label="") -> None:
        self._spawners.append({"id": spawner_id, "area": list(area), "every": every, "max_alive": max_alive,
                               "prefix": prefix, "points": points, "label": label, "count": 0})

    # opens: delivered가 target에 도달하면 영구히 여는 문 목록 (통행료 함 등)
    def add_receptacle(self, receptacle_id, x, y, accepts, target=1, radius=20.0, label="", opens=None) -> None:
        self.objects[receptacle_id] = {"object_id": receptacle_id, "x": x, "y": y, "type": "receptacle",
                                       "accepts": list(accepts), "target": target, "delivered": 0,
                                       "radius": radius, "label": label, "opens": list(opens or [])}

    def add_checkpoint(self, checkpoint_id, x, y, radius=12.0, hidden=False, label="") -> None:
        self.objects[checkpoint_id] = {"object_id": checkpoint_id, "x": x, "y": y, "type": "checkpoint",
                                       "radius": radius, "hidden": hidden, "visited": False, "label": label}

    # variants: agent_id -> 그 에이전트에게 보이는 content (없는 에이전트는 content 그대로)
    def add_variant_clue(self, clue_id, x, y, content, variants, hidden=False) -> None:
        self.add_clue(clue_id, x, y, content, hidden=hidden)
        self.objects[clue_id]["_variants"] = copy.deepcopy(variants)

    # required명이 같은 step에 같은 방향(angle_tolerance도 이내)으로 밀면 push_distance만큼 이동
    def add_push_block(self, block_id, x, y, radius=12.0, required=2, push_distance=20.0, label="") -> None:
        self.objects[block_id] = {"object_id": block_id, "x": x, "y": y, "type": "block", "radius": radius,
                                  "required": required, "push_distance": push_distance, "label": label,
                                  "_start": (x, y)}

    def add_block_target(self, target_id, x, y, radius=10.0, label="") -> None:
        self.objects[target_id] = {"object_id": target_id, "x": x, "y": y, "type": "block_target",
                                   "radius": radius, "filled": False, "label": label}

    def add_reset_lever(self, lever_id, x, y, blocks) -> None:
        self.objects[lever_id] = {"object_id": lever_id, "x": x, "y": y, "type": "lever", "on": False,
                                  "linked_door_ids": [], "reset": True, "blocks": list(blocks)}

    # input 접두사 아이템을 반경 안에 내려놓으면 process_steps 뒤 (out_x, out_y)에 "<output>_<n>" 아이템 생성.
    # 한 번에 하나씩 가공 (뒤에 온 것은 차례를 기다림)
    def add_station(self, station_id, x, y, input, output, process_steps=3, radius=15.0, out_x=None, out_y=None,
                    label="") -> None:
        self.objects[station_id] = {"object_id": station_id, "x": x, "y": y, "type": "station", "input": input,
                                    "output": output, "process_steps": process_steps, "radius": radius,
                                    "out_x": x if out_x is None else out_x, "out_y": y if out_y is None else out_y,
                                    "busy_until": 0, "queued": 0, "made": 0, "label": label}

    # 한 에이전트가 hold_limit step 넘게 들고 있으면 원위치로 돌아감 (다른 에이전트가 받으면 다시 셈).
    # 들고 있는 동안 한 번의 이동이 carry_speed로 제한됨. drop_by_step: 지금 든 사람이 내려놓아야 하는 step
    def add_cargo(self, cargo_id, x, y, hold_limit=10, carry_speed=10.0, label="") -> None:
        self.add_item(cargo_id, x, y, category=ITEM_NORMAL)
        self.objects[cargo_id].update({"cargo": True, "hold_limit": hold_limit, "carry_speed": carry_speed,
                                       "label": label, "drop_by_step": None, "_origin": (x, y),
                                       "_carrier": None, "_held_since": None})

    def add_weighted_item(self, item_id, x, y, weight, label="") -> None:
        self.add_item(item_id, x, y, category=ITEM_NORMAL)
        self.objects[item_id].update({"label": label, "_weight": weight})

    # target이 없으면 반경 안 물건 무게 합을 reading에 숫자로, 있으면 "too light"/"too heavy"/"balanced"만 표시
    def add_scale(self, scale_id, x, y, radius=15.0, target=None, label="") -> None:
        self.objects[scale_id] = {"object_id": scale_id, "x": x, "y": y, "type": "scale", "radius": radius,
                                  "reading": 0 if target is None else "empty", "label": label,
                                  "_target": target}

    def add_capacity_zone(self, zone_id, x, y, width, height, capacity=1, label="") -> None:
        self.objects[zone_id] = {"object_id": zone_id, "x": x, "y": y, "type": "capacity_zone",
                                 "width": width, "height": height, "capacity": capacity, "label": label}

    # contents: [{"kind": "key"/"item"/..., "id": ..., 그 add_<kind>의 나머지 인자}, ...]
    def add_chest(self, chest_id, x, y, contents, radius=8.0, label="") -> None:
        self.objects[chest_id] = {"object_id": chest_id, "x": x, "y": y, "type": "chest", "locked": True,
                                  "radius": radius, "label": label, "_contents": copy.deepcopy(contents)}

    # 아무 동작 없이 이름표(label)만 있는 바닥 표시 (예: 색깔 매트). 물건을 올려 신호로 쓰는 용도
    def add_marker(self, marker_id, x, y, label="", radius=12.0) -> None:
        self.objects[marker_id] = {"object_id": marker_id, "x": x, "y": y, "type": "marker",
                                   "label": label, "radius": radius}

    def add_coin(self, coin_id, x, y, value=5.0) -> None:
        self.add_item(coin_id, x, y, category=ITEM_NORMAL)
        self.objects[coin_id].update({"coin": True, "value": value})

    # ------------------------------------------------------------------ 관찰

    # 비밀 필드("_"로 시작)와, 경로를 숨긴 mover의 waypoints를 지움
    def _disguise(self, obj: dict) -> dict:
        hide_path = obj.get("_hide_path")
        obj = super()._disguise(obj)
        for key in [k for k in obj if k.startswith("_")]:
            del obj[key]
        if hide_path:
            for key in ("waypoints", "target_index", "loop"):
                obj.pop(key, None)
        return obj

    def get_observation(self, agent_id: str) -> dict:
        observation = super().get_observation(agent_id)
        if self.stages:
            index = min(self.stage_index or 0, len(self.stages) - 1)
            stage = self.stages[index]
            observation["stage"] = {"stage": index + 1, "total": len(self.stages), "title": stage.get("title", ""),
                                    "briefing": stage.get("briefing", ""),
                                    "completed": self.stage_index is not None and self.stage_index >= len(self.stages)}
        for obj in observation["visible_objects"]:
            variants = self.objects.get(obj["object_id"], {}).get("_variants")
            if variants and agent_id in variants:
                obj["content"] = copy.deepcopy(variants[agent_id])
                observation["known_objects"][obj["object_id"]]["content"] = copy.deepcopy(variants[agent_id])
        return observation

    # ------------------------------------------------------------------ 행동

    def apply_action(self, agent_id: str, action: dict, observation: dict = None) -> dict:
        if isinstance(action, dict) and action.get("type") in MESSAGE_ACTIONS:
            reason = self._message_refusal(agent_id, action)
            if reason is not None:
                self.message_stats["blocked"] += 1
                self._log("message_blocked", [agent_id], reason=reason)
                self.agents[agent_id].inbox.append({"type": "system", "from": "system", "step": self.step_count,
                                                    "content": f"Your message was NOT sent: {reason}"})
                return {"type": "noop"}
            self._last_sent[agent_id] = self.step_count
        final = super().apply_action(agent_id, action, observation)
        if final.get("type") == "move_forward":
            self._record_push(agent_id)
        return final

    # 이번 step에 전진을 시도했고, 끝난 위치가 블록에 맞닿아 있으며(반경 + 1 이내) 블록이 정면 45도
    # 이내에 있으면 민 것으로 기록 (블록에 막혔든, 딱 맞닿는 데서 멈췄든)
    def _record_push(self, agent_id: str) -> None:
        agent = self.agents[agent_id]
        last = agent.last_move or {}
        if last.get("step") != self.step_count or not last.get("requested_distance"):
            return
        for block in [o for o in self.objects.values() if o["type"] == "block"]:
            dx, dy = block["x"] - agent.x, block["y"] - agent.y
            if math.hypot(dx, dy) > block["radius"] + 1.0:
                continue
            angle = abs((math.degrees(math.atan2(dy, dx)) - agent.facing + 180) % 360 - 180)
            if angle <= 45:
                self._pushes.setdefault(block["object_id"], []).append((agent_id, agent.facing))
                return

    def _message_refusal(self, agent_id: str, action: dict):
        if self.scenario_rules.get("message_disabled"):
            return "messages are disabled in this map"
        max_chars = self.scenario_rules.get("message_max_chars")
        interval = self.scenario_rules.get("message_interval")
        if interval:
            last = self._last_sent.get(agent_id)
            if last is not None and self.step_count - last < interval:
                return f"you may send only one message every {interval} steps (next allowed at step {last + interval})"
        if max_chars:
            payload = [v for k, v in action.items() if k not in ("type", "receiver_id", "memory")]
            text = " ".join(v if isinstance(v, str) else str(v) for v in payload)
            if len(text) > max_chars:
                return f"message is {len(text)} characters long; the limit is {max_chars}"
        return None

    def _deliver(self, receiver_id: str, message: dict) -> None:
        if not isinstance(receiver_id, str) or receiver_id not in self.agents:
            return
        loss = self.scenario_rules.get("message_loss", 0.0)
        if loss and self._rng.random() < loss:
            self.message_stats["lost"] += 1
            self._log("message_lost", [message.get("from")], receiver_id=receiver_id)
            return
        low, high = self.scenario_rules.get("message_delay", (0, 0))
        delay = self._rng.randint(low, high) if high else 0
        if delay > 0:
            self.message_stats["delayed"] += 1
            self._pending_messages.append((self.step_count + delay, receiver_id, message))
            return
        super()._deliver(receiver_id, message)

    def _flush_messages(self) -> None:
        due = [m for m in self._pending_messages if m[0] <= self.step_count]
        self._pending_messages = [m for m in self._pending_messages if m[0] > self.step_count]
        for _, receiver_id, message in due:
            Environment._deliver(self, receiver_id, message)

    def _move_agent(self, agent_id: str, dx: float, dy: float) -> None:
        speeds = [o["carry_speed"] for o in self.agents[agent_id].inventory if o.get("carry_speed")]
        distance = math.hypot(dx, dy)
        if speeds and distance > min(speeds):
            dx, dy = dx / distance * min(speeds), dy / distance * min(speeds)
        super()._move_agent(agent_id, dx, dy)
        self.travel[agent_id] = self.travel.get(agent_id, 0.0) + self.agents[agent_id].last_move["distance"]

    def press_button(self, agent_id: str, button_id: str) -> None:
        button = self.objects.get(button_id)
        if button is not None and button.get("type") == "button" and "panel" in button:
            agent = self.agents[agent_id]
            panel = self.objects.get(button["panel"]) or {}
            if panel.get("operators") and agent_id not in panel["operators"]:
                self._log("keypad_denied", [agent_id], panel_id=button["panel"])
                return
            if math.hypot(agent.x - button["x"], agent.y - button["y"]) <= self.interact_radius:
                self._keypad_input(agent_id, button)
            return
        super().press_button(agent_id, button_id)

    def pull_lever(self, agent_id: str, lever_id: str) -> None:
        lever = self.objects.get(lever_id)
        if lever is None or lever.get("type") != "lever":
            return
        agent = self.agents[agent_id]
        if math.hypot(agent.x - lever["x"], agent.y - lever["y"]) > self.interact_radius:
            return
        if lever.get("reset"):
            moved = []
            for block_id in lever["blocks"]:
                block = self.objects.get(block_id)
                if block is not None and (block["x"], block["y"]) != tuple(block["_start"]):
                    block["x"], block["y"] = block["_start"]
                    moved.append(block_id)
            self._log("lever_pulled", [agent_id], lever_id=lever_id, on=False)
            self._log("blocks_reset", [agent_id], lever_id=lever_id, blocks=moved)
            return
        if lever.get("latch"):
            lever["on"] = True
            self._log("lever_pulled", [agent_id], lever_id=lever_id, on=True)
            for door_id in lever["linked_door_ids"]:
                door = self.objects.get(door_id)
                if door is not None:
                    door["latched"] = True
                    self._set_door_locked(door, False, "lever", [agent_id], lever_id)
            return
        if "cooldown" in lever:
            if self.step_count < lever["ready_at_step"]:
                self._log("lever_cooling", [agent_id], lever_id=lever_id, ready_at_step=lever["ready_at_step"])
                return
            lever["ready_at_step"] = self.step_count + lever["cooldown"]
        super().pull_lever(agent_id, lever_id)
        self._update_logic_doors([agent_id], lever_id)

    def pick_up(self, agent_id: str, object_id: str) -> None:
        obj = self.objects.get(object_id)
        super().pick_up(agent_id, object_id)
        if obj is None or object_id in self.objects:
            return
        if obj.get("bonus"):
            self._log("bonus_collected", [agent_id], object_id=object_id, points=obj.get("_points", 0.0))
        if obj.get("cargo") and obj["_carrier"] != agent_id:
            if obj["_carrier"] is not None:
                self._log("cargo_handoff", [obj["_carrier"], agent_id], object_id=object_id,
                          from_agent=obj["_carrier"], to_agent=agent_id)
            obj["_carrier"], obj["_held_since"] = agent_id, self.step_count
            obj["drop_by_step"] = self.step_count + obj["hold_limit"]

    # 상자(chest)를 노린 열쇠면 상자를 열고 내용물을 꺼냄. 그 밖에는 기존 처리 (문)
    def use_key(self, agent_id: str, key_object_id: str) -> None:
        agent = self.agents[agent_id]
        key = next((o for o in agent.inventory if o["object_id"] == key_object_id), None)
        chest = self.objects.get(key["unlocks"]) if key is not None and key.get("type") == "key" else None
        if chest is None or chest.get("type") != "chest":
            super().use_key(agent_id, key_object_id)
            return
        if not chest["locked"] or math.hypot(agent.x - chest["x"], agent.y - chest["y"]) > self.interact_radius + chest["radius"]:
            return
        chest["locked"] = False
        agent.inventory.remove(key)
        spawned = []
        for i, item in enumerate(chest["_contents"]):
            item = dict(item)
            kind, item_id = item.pop("kind"), item.pop("id")
            angle = 2 * math.pi * i / max(1, len(chest["_contents"]))
            getattr(self, f"add_{kind}")(item_id, round(chest["x"] + 6 * math.cos(angle), 1),
                                         round(chest["y"] + 6 * math.sin(angle), 1), **item)
            spawned.append(item_id)
        self._log("chest_opened", [agent_id], object_id=chest["object_id"], key_id=key_object_id, contents=spawned)

    def drop(self, agent_id: str, object_id: str) -> None:
        super().drop(agent_id, object_id)
        obj = self.objects.get(object_id)
        if obj is None:
            return
        for station in [o for o in self.objects.values() if o["type"] == "station"]:
            if (math.hypot(obj["x"] - station["x"], obj["y"] - station["y"]) <= station["radius"]
                    and object_id.startswith(station["input"])):
                del self.objects[object_id]
                finish = max(self.step_count, station["busy_until"]) + station["process_steps"]
                station["busy_until"] = finish
                station["queued"] += 1
                self._jobs.append({"finish": finish, "station": station["object_id"], "by": agent_id})
                self._log("item_processing", [agent_id], object_id=object_id, station_id=station["object_id"],
                          ready_at=finish)
                return
        for receptacle in [o for o in self.objects.values() if o["type"] == "receptacle"]:
            if math.hypot(obj["x"] - receptacle["x"], obj["y"] - receptacle["y"]) > receptacle["radius"]:
                continue
            if not any(object_id.startswith(prefix) for prefix in receptacle["accepts"]):
                continue
            # 목표를 채운 함은 더 받지 않음 (떨어뜨린 물건은 바닥에 남음). 받으면 개수가 정해진 물건(s24의 동전)을
            # 이미 열린 문에 계속 버려 과제를 영구히 불가능하게 만들 수 있음 - "영구 실패 없음" 안내와 모순
            if receptacle["delivered"] >= receptacle["target"]:
                continue
            del self.objects[object_id]
            receptacle["delivered"] += 1
            self._log("item_delivered", [agent_id], object_id=object_id, receptacle_id=receptacle["object_id"],
                      delivered=receptacle["delivered"])
            if receptacle["delivered"] == receptacle["target"]:
                self._log("delivery_complete", [agent_id], receptacle_id=receptacle["object_id"])
                for door_id in receptacle.get("opens", []):
                    door = self.objects.get(door_id)
                    if door is not None:
                        door["latched"] = True
                        self._set_door_locked(door, False, "receptacle", [agent_id], receptacle["object_id"])
            return

    # ------------------------------------------------------------------ 장치 로직

    def _keypad_input(self, agent_id: str, button: dict) -> None:
        panel = self.objects.get(button["panel"])
        if panel is None or panel["solved"]:
            return
        panel["entered"].append(button["label"])
        self._log("keypad_input", [agent_id], panel_id=panel["object_id"], label=button["label"])
        code, entered = panel["_code"], panel["entered"]
        if panel["mode"] == "sequence":
            if entered != code[:len(entered)]:
                panel["attempts"] += 1
                panel["entered"] = []
                self._log("keypad_reset", [agent_id], panel_id=panel["object_id"], wrong_at=len(entered))
                self._show(panel, {"attempts": panel["attempts"], "last_result": "wrong - panel cleared"})
            elif len(entered) == len(code):
                self._solve_keypad(agent_id, panel)
            return
        if len(entered) < len(code):
            return
        panel["attempts"] += 1
        exact = sum(a == b for a, b in zip(entered, code))
        common = sum(min(entered.count(c), code.count(c)) for c in set(code))
        result = {"attempt": panel["attempts"], "exact": exact, "misplaced": common - exact}
        self._log("keypad_attempt", [agent_id], panel_id=panel["object_id"], guess=list(entered), **result)
        panel["entered"] = []
        self._show(panel, result)
        if exact == len(code):
            self._solve_keypad(agent_id, panel)

    def _solve_keypad(self, agent_id: str, panel: dict) -> None:
        panel["solved"] = True
        self._log("keypad_solved", [agent_id], panel_id=panel["object_id"], attempts=panel["attempts"])
        self._show(panel, {"attempts": panel["attempts"], "last_result": "SOLVED"})
        for door_id in panel["_opens"]:
            door = self.objects.get(door_id)
            if door is not None:
                door["latched"] = True
                self._set_door_locked(door, False, "keypad", [agent_id], panel["object_id"])

    def _show(self, panel: dict, content: dict) -> None:
        display = self.objects.get(panel.get("_display") or "")
        if display is not None:
            display["content"] = copy.deepcopy(content)

    def _update_logic_doors(self, agent_ids, source) -> None:
        for door in self.objects.values():
            if door["type"] != "door" or "_levers" not in door:
                continue
            on = sum(bool(self.objects.get(lid, {}).get("on")) for lid in door["_levers"])
            self._set_door_locked(door, on % 2 != door["_parity"], "logic", list(agent_ids), source)

    def _update_periodic_doors(self) -> None:
        for door in self.objects.values():
            if door["type"] == "door" and "_period" in door:
                is_open = (self.step_count + door["_phase"]) % door["_period"] < door["_open_steps"]
                self._set_door_locked(door, not is_open, "schedule", [], door["object_id"])

    def _update_switch_plates(self) -> None:
        door_open: dict[str, bool] = {}
        door_users: dict[str, set[str]] = {}
        for plate in self.objects.values():
            if plate["type"] != "switch_plate":
                continue
            occupants = {a.agent_id for a in self.agents.values()
                         if math.hypot(a.x - plate["x"], a.y - plate["y"]) <= plate["radius"]}
            before = self._switch_occupants.get(plate["object_id"], set())
            for agent_id in sorted(occupants - before):
                self._log("plate_entered", [agent_id], plate_id=plate["object_id"])
            for agent_id in sorted(before - occupants):
                self._log("plate_left", [agent_id], plate_id=plate["object_id"])
            self._switch_occupants[plate["object_id"]] = occupants
            for door_id in plate["opens"]:
                door_open[door_id] = door_open.get(door_id, False) or bool(occupants)
                door_users.setdefault(door_id, set()).update(occupants | (before - occupants))
        for door_id, is_open in door_open.items():
            door = self.objects.get(door_id)
            if door is None or door.get("latched"):
                continue
            self._set_door_locked(door, not is_open, "switch_plate", sorted(door_users[door_id]), door_id)

    def _update_sync_pads(self) -> None:
        pads = [o for o in self.objects.values() if o["type"] == "sync_pad"]
        for pad in pads:
            state = self._sync[pad["group"]]
            pad["armed"] = not state["solved"] and self.step_count >= state["disabled_until"]
            occupants = {a.agent_id for a in self.agents.values()
                         if math.hypot(a.x - pad["x"], a.y - pad["y"]) <= pad["radius"]}
            entered = occupants - self._sync_inside.get(pad["object_id"], set())
            self._sync_inside[pad["object_id"]] = occupants
            if entered and pad["armed"] and pad["object_id"] not in state["entries"]:
                state["entries"][pad["object_id"]] = self.step_count
                self._log("sync_pad_entered", sorted(entered), pad_id=pad["object_id"], group=pad["group"])
        for group, state in self._sync.items():
            if state["solved"] or not state["entries"]:
                continue
            members = [p for p in pads if p["group"] == group]
            tolerance = members[0]["_tolerance"]
            steps = list(state["entries"].values())
            if len(state["entries"]) == len(members) and max(steps) - min(steps) <= tolerance:
                state["solved"] = True
                agent_ids = sorted(set().union(*(self._sync_inside[p["object_id"]] for p in members)))
                self._log("sync_success", agent_ids, group=group)
                for agent_id in self.agents:
                    self._notify(agent_id, {"type": "sync_success", "group": group})
                for door_id in {d for p in members for d in p["_opens"]}:
                    door = self.objects.get(door_id)
                    if door is not None:
                        door["latched"] = True
                        self._set_door_locked(door, False, "sync", agent_ids, group)
            elif self.step_count - min(steps) >= tolerance:
                pushed = []
                for pad in members:
                    for agent_id in sorted(self._sync_inside.get(pad["object_id"], set())):
                        agent = self.agents[agent_id]
                        rx, ry = pad["_return"]
                        if rx is not None:
                            agent.x, agent.y = rx, ry
                        pushed.append(agent_id)
                    self._sync_inside[pad["object_id"]] = set()
                state["entries"] = {}
                state["disabled_until"] = self.step_count + 1 + members[0]["_cooldown"]
                for pad in members:
                    pad["armed"] = False
                self._log("sync_fail", pushed, group=group, disabled_until=state["disabled_until"])
                # 이동 자체는 유효(ok)했으므로 last_action_result로는 실패가 안 보임 -> 밀려난 에이전트에게 알림
                for agent_id in pushed:
                    self._notify(agent_id, {"type": "sync_fail", "group": group,
                                            "disabled_until": state["disabled_until"]})

    def _update_spawners(self) -> None:
        for spawner in self._spawners:
            if self.step_count % spawner["every"] != 0:
                continue
            alive = [o for o in self.objects.values() if o["object_id"].startswith(spawner["prefix"] + "_")]
            if len(alive) >= spawner["max_alive"]:
                continue
            x0, y0, x1, y1 = spawner["area"]
            for _ in range(50):
                x, y = self._rng.uniform(x0, x1), self._rng.uniform(y0, y1)
                if not any(wx - 5 <= x <= wx + ww + 5 and wy - 5 <= y <= wy + wh + 5 for wx, wy, ww, wh in self._walls()):
                    break
            spawner["count"] += 1
            item_id = f"{spawner['prefix']}_{spawner['count']}"
            if spawner["points"]:
                self.add_bonus_item(item_id, round(x, 1), round(y, 1), points=spawner["points"])
            else:
                self.add_item(item_id, round(x, 1), round(y, 1))
            if spawner["label"]:
                self.objects[item_id]["label"] = spawner["label"]
            self._log("item_spawned", [], object_id=item_id, spawner_id=spawner["id"])

    def _expire_bonus_items(self) -> None:
        for obj in list(self.objects.values()):
            if obj.get("bonus") and obj.get("expires_at") is not None and self.step_count >= obj["expires_at"]:
                del self.objects[obj["object_id"]]
                self._log("bonus_expired", [], object_id=obj["object_id"])

    def _update_checkpoints_and_zones(self) -> None:
        checkpoints = [o for o in self.objects.values() if o["type"] == "checkpoint"]
        for cp in checkpoints:
            if cp["visited"]:
                continue
            visitors = [a.agent_id for a in self.agents.values()
                        if math.hypot(a.x - cp["x"], a.y - cp["y"]) <= cp["radius"]]
            if visitors:
                cp["visited"] = True
                self._log("checkpoint_visited", visitors, object_id=cp["object_id"])
        if checkpoints and not self._all_visited_logged and all(cp["visited"] for cp in checkpoints):
            self._all_visited_logged = True
            self._log("all_checkpoints_visited", [])
        for zone in [o for o in self.objects.values() if o["type"] == "goal_zone"]:
            if zone["object_id"] in self._assembled or not self.agents:
                continue
            members = [self.agents[a] for a in (zone.get("agents") or self.agents) if a in self.agents]
            if members and all(self._in_rect(a, zone) for a in members):
                self._assembled.add(zone["object_id"])
                self._log("team_assembled", sorted(a.agent_id for a in members), zone_id=zone["object_id"])

    @staticmethod
    def _in_rect(agent, zone) -> bool:
        return abs(agent.x - zone["x"]) <= zone["width"] / 2 and abs(agent.y - zone["y"]) <= zone["height"] / 2

    # 이번 step의 밀기를 방향별로 묶어, required명 이상이 같은 방향(30도 이내)으로 민 블록을 움직임
    def _update_blocks(self) -> None:
        pushes, self._pushes = self._pushes, {}
        for block_id, entries in pushes.items():
            block = self.objects.get(block_id)
            if block is None:
                continue
            best = []
            for _, facing in entries:
                group = [(a, f) for a, f in entries if abs((f - facing + 180) % 360 - 180) <= 30]
                if len({a for a, _ in group}) > len({a for a, _ in best}):
                    best = group
            pushers = sorted({a for a, _ in best})
            if len(pushers) < block["required"]:
                self._log("push_too_weak", sorted({a for a, _ in entries}), object_id=block_id,
                          required=block["required"])
                continue
            heading = math.atan2(sum(math.sin(math.radians(f)) for _, f in best),
                                 sum(math.cos(math.radians(f)) for _, f in best))
            nx = block["x"] + block["push_distance"] * math.cos(heading)
            ny = block["y"] + block["push_distance"] * math.sin(heading)
            if self._block_fits(block, nx, ny):
                block["x"], block["y"] = round(nx, 2), round(ny, 2)
                self._log("block_moved", pushers, object_id=block_id, position=(block["x"], block["y"]))
            else:
                self._log("block_stuck", pushers, object_id=block_id)

    def _block_fits(self, block, x, y) -> bool:
        r = block["radius"]
        if not (r <= x <= self.game_map.map_width - r and r <= y <= self.game_map.map_height - r):
            return False
        for wx, wy, ww, wh in self._walls():
            if math.hypot(x - min(max(x, wx), wx + ww), y - min(max(y, wy), wy + wh)) < r:
                return False
        return not any(o is not block and o["type"] in ("block", "door") and o.get("locked", True)
                       and math.hypot(x - o["x"], y - o["y"]) < r + o["radius"]
                       for o in self.objects.values())

    def _update_block_targets(self) -> None:
        targets = [o for o in self.objects.values() if o["type"] == "block_target"]
        blocks = [o for o in self.objects.values() if o["type"] == "block"]
        for target in targets:
            filled = any(math.hypot(b["x"] - target["x"], b["y"] - target["y"]) <= target["radius"] for b in blocks)
            if filled != target["filled"]:
                target["filled"] = filled
                self._log("target_filled" if filled else "target_cleared", [], object_id=target["object_id"])
        if targets and not self._targets_logged and all(t["filled"] for t in targets):
            self._targets_logged = True
            self._log("all_targets_filled", [])

    def _finish_jobs(self) -> None:
        for job in [j for j in self._jobs if j["finish"] <= self.step_count]:
            self._jobs.remove(job)
            station = self.objects.get(job["station"])
            if station is None:  # 단계형 맵에서 단계가 바뀌어 가공대가 치워진 경우
                continue
            station["made"] += 1
            station["queued"] -= 1
            item_id = f"{station['output']}_{station['object_id']}_{station['made']}"
            self.add_item(item_id, station["out_x"], station["out_y"])
            self._log("item_processed", [job["by"]], object_id=item_id, station_id=station["object_id"])

    # 한 사람이 hold_limit step 넘게 든 화물은 원위치로 (들고 있지 않아도 마지막으로 든 사람의 시간은 계속 감)
    def _spoil_cargo(self) -> None:
        for agent in self.agents.values():
            for cargo in [o for o in agent.inventory if o.get("cargo")]:
                if self.step_count >= cargo["drop_by_step"]:
                    agent.inventory.remove(cargo)
                    self._return_cargo(cargo, agent.agent_id)
        for cargo in [o for o in self.objects.values() if o.get("cargo") and o["drop_by_step"] is not None]:
            if self.step_count >= cargo["drop_by_step"] and (cargo["x"], cargo["y"]) != tuple(cargo["_origin"]):
                del self.objects[cargo["object_id"]]
                self._return_cargo(cargo, cargo["_carrier"])

    def _return_cargo(self, cargo, agent_id) -> None:
        cargo["x"], cargo["y"] = cargo["_origin"]
        cargo["_carrier"], cargo["_held_since"], cargo["drop_by_step"] = None, None, None
        self.objects[cargo["object_id"]] = cargo
        self._log("cargo_spoiled", [agent_id] if agent_id else [], object_id=cargo["object_id"])

    def _update_scales(self) -> None:
        for scale in [o for o in self.objects.values() if o["type"] == "scale"]:
            total = sum(o.get("_weight", 0) for o in self.objects.values()
                        if o["type"] == "item" and math.hypot(o["x"] - scale["x"], o["y"] - scale["y"]) <= scale["radius"])
            target = scale["_target"]
            if target is None:
                scale["reading"] = total
                continue
            scale["reading"] = ("empty" if total == 0 else "balanced" if total == target
                                else "too light" if total < target else "too heavy")
            if scale["reading"] == "balanced" and scale["object_id"] not in self._balanced:
                self._balanced.add(scale["object_id"])
                self._log("scale_balanced", [], scale_id=scale["object_id"], weight=total)

    # 정원을 넘으면 안에 있던 전원을 들어오기 직전 자리로 되돌림
    def _update_capacity_zones(self) -> None:
        zones = [o for o in self.objects.values() if o["type"] == "capacity_zone"]
        for agent in self.agents.values():
            if not any(self._in_rect(agent, z) for z in zones):
                self._outside[agent.agent_id] = (agent.x, agent.y)
        for zone in zones:
            inside = [a for a in self.agents.values() if self._in_rect(a, zone)]
            if len(inside) <= zone["capacity"]:
                continue
            for agent in inside:
                agent.x, agent.y = self._outside.get(agent.agent_id, (agent.x, agent.y))
            self._log("zone_overloaded", sorted(a.agent_id for a in inside), zone_id=zone["object_id"])

    # scoring.score_episode가 회차 끝에 더하는 개인 점수: 들고 있는 동전 {agent_id: [(점수, 사유, 대상)]}
    def final_points(self) -> dict:
        return {agent_id: [(o["value"], "보유 동전", o["object_id"]) for o in agent.inventory if o.get("coin")]
                for agent_id, agent in self.agents.items()}

    def _count_holds(self) -> None:
        for agent in self.agents.values():
            if any(o["type"] in PLATE_TYPES and math.hypot(agent.x - o["x"], agent.y - o["y"]) <= o.get("radius", 0)
                   for o in self.objects.values()):
                self.hold_steps[agent.agent_id] = self.hold_steps.get(agent.agent_id, 0) + 1

    # ------------------------------------------------------------------ step 훅

    # Environment.step()은 step_count를 올린 직후 _update_movers()를, 모든 행동을 적용한 뒤
    # _update_pressure_plates()를 부름 - 이 둘을 step 시작/끝 훅으로 씀 (step() 자체는 그대로)
    def _update_movers(self) -> None:
        super()._update_movers()
        self._flush_messages()
        self._expire_bonus_items()
        self._update_spawners()
        self._update_periodic_doors()
        self._finish_jobs()
        self._spoil_cargo()

    def _update_pressure_plates(self) -> None:
        super()._update_pressure_plates()
        self._update_blocks()
        self._update_block_targets()
        self._update_capacity_zones()
        self._update_switch_plates()
        self._update_sync_pads()
        self._update_scales()
        self._update_checkpoints_and_zones()
        self._count_holds()
        self._check_stage()

    # ------------------------------------------------------------------ 단계

    # builder가 에이전트까지 배치한 뒤 부름: 시작 위치를 기억하고 첫 단계를 불러옴
    def begin_stages(self) -> None:
        if not self.stages or self.stage_index is not None:
            return
        self._base_walls = list(self.game_map.walls)
        self._start_states = {aid: (a.x, a.y, a.facing) for aid, a in self.agents.items()}
        self._load_stage(0)

    def _load_stage(self, index: int) -> None:
        stage = self.stages[index]
        for object_id in self._stage_ids:
            self.objects.pop(object_id, None)
        for agent in self.agents.values():
            agent.inventory = [o for o in agent.inventory if o["object_id"] not in self._stage_ids]
        self.game_map.walls = ([_StageWall(*wall) for wall in stage["walls"]] if "walls" in stage
                               else list(self._base_walls))
        for agent_id, agent in self.agents.items():
            x, y, facing = stage.get("agents", {}).get(agent_id, self._start_states[agent_id])
            agent.x, agent.y, agent.facing, agent.last_move = float(x), float(y), float(facing) % 360, None
        for item in stage["objects"]:
            getattr(self, f"add_{item['kind']}")(item["id"], item["x"], item["y"], **copy.deepcopy(item["params"]))
        self._stage_ids = [item["id"] for item in stage["objects"]]
        # 지난 단계 물체의 기억이 현재 물체처럼 보이지 않게 함 (curriculum과 같은 처리)
        self._known = {}
        self._refresh_plans()
        self.stage_index = index
        self._stage_event_start = len(self.event_log.entries)
        self._log("level_started", sorted(self.agents), level=index + 1, title=stage.get("title", ""))
        for agent_id in self.agents:
            self._notify(agent_id, {"type": "stage_started", "stage": index + 1, "total": len(self.stages),
                                    "title": stage.get("title", "")})

    # 새 단계에서는 예전 단계용 코드가 맞지 않으므로 다음 턴에 정책 코드를 새로 짜게 함
    def _refresh_plans(self) -> None:
        for agent in self.agents.values():
            policy = agent.policy
            if policy is None:
                continue
            for name, value in (("generated_code", None), ("_next_review_step", None), ("_last_pos", None),
                                ("_last_action", None), ("_stall_count", 0), ("_agent_states", {})):
                if hasattr(policy, name):
                    setattr(policy, name, copy.copy(value))

    def _check_stage(self) -> None:
        if self.stage_index is None or self.stage_index >= len(self.stages):
            return
        stage = self.stages[self.stage_index]
        events = self.event_log.entries[self._stage_event_start:]
        if not all(any(_matches(e, condition) for e in events) for condition in stage["objectives"]):
            return
        self._log("level_completed", sorted(self.agents), level=self.stage_index + 1)
        if self.stage_index + 1 < len(self.stages):
            self._load_stage(self.stage_index + 1)
        else:
            self.stage_index = len(self.stages)
            self._log("all_stages_completed", sorted(self.agents))

    def _count_events(self, event_type) -> dict:
        counts: dict[str, int] = {}
        for event in self.event_log.filter(event_type=event_type):
            for agent_id in event["agent_ids"]:
                counts[agent_id] = counts.get(agent_id, 0) + 1
        return counts

    # scoring.score_episode가 team["metrics"]에 넣는 시나리오 지표
    def scenario_metrics(self) -> dict:
        bonus: dict[str, float] = {}
        for event in self.event_log.entries:
            if event["type"] == "bonus_collected":
                for agent_id in event["agent_ids"]:
                    bonus[agent_id] = bonus.get(agent_id, 0.0) + event["points"]
        return {
            "distance_travelled": {a: round(d, 2) for a, d in self.travel.items()},
            "team_distance": round(sum(self.travel.values()), 2),
            "plate_hold_steps": dict(self.hold_steps),
            "coins_held": {a: sum(o["value"] for o in ag.inventory if o.get("coin")) for a, ag in self.agents.items()},
            "deliveries": self._count_events("item_delivered"),
            "handoffs": len(self.event_log.filter(event_type="cargo_handoff")),
            "bonus_points": bonus,
            "messages": dict(self.message_stats),
        }
