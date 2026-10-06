import copy
import json
import math
from concurrent.futures import ThreadPoolExecutor

from agent import Agent
from history import DecisionLog, EventLog, MessageLog
from physics import PhysicsEngine, SimplePhysicsEngine
from rule import Rule, ObeyCommandRule

# add_item()의 물품 분류 (자세한 의미는 add_item 주석 참고)
ITEM_NORMAL = "normal"  # 혼자 다룰 수 있는 일반 물품
ITEM_COOP = "coop"      # 여러 명이 함께 있어야만 줍고 옮길 수 있는 물품
ITEM_TRAP = "trap"      # 줍는 순간 문을 영구 봉인해 게임을 불가능하게 만드는 물품
ITEM_CATEGORIES = (ITEM_NORMAL, ITEM_COOP, ITEM_TRAP)


class Environment:
    def __init__(
        self,
        game_map,
        interact_radius: float = 15.0,
        physics: PhysicsEngine = None,
        max_move: float | None = 20.0
    ) -> None:
        self.game_map = game_map
        self.interact_radius = interact_radius  # 버튼/문 상호작용 가능 거리
        # 한 번의 move로 갈 수 있는 최대 거리 (None이면 제한 없음). 제한이 없으면 한 step에 맵을
        # 가로지를 수 있어 클리어 시간 점수가 의미를 잃으므로 기본으로 제한
        self.max_move = max_move
        self.physics = physics or SimplePhysicsEngine()  # 이동/충돌 계산 위임 대상 (교체 가능)
        self.agents: dict[str, Agent] = {}
        self.objects: dict[str, dict] = {}
        self.rules: list[Rule] = []  # 모든 에이전트에게 동일하게 적용되는 전역 강제 규칙
        self.step_count = 0  # step()이 몇 번 진행됐는지 (메시지 기록에 시점 표시용)
        self.message_log = MessageLog()  # 오간 메시지 전부 기록 (반사실적 재현 분석용)
        self.decision_log = DecisionLog()  # 매 step 각 에이전트의 관찰/결정/실제 실행 기록 (반사실적 재현 분석용)
        self.event_log = EventLog()  # 실제로 일어난 상태 변화와 그걸 일으킨 에이전트 기록 (마일스톤 채점/기여도 산정용)
        # trap 물품이 발동해 게임이 불가능해진 경우 그 원인 기록 (None이면 아직 진행 가능).
        # {"step", "agent_id", "object_id", "sealed_doors"} - "누가 언제 실패를 확정지었나" 분석용
        self.failure: dict | None = None
        self._portals_inside: dict[str, set[str]] = {}  # agent_id -> 현재 서 있는 portal_id 집합 (재발동 방지)
        self._plate_occupants: dict[str, set[str]] = {}  # plate_id -> 지난 판정 때 위에 서 있던 agent_id 집합 (진입/이탈 이벤트용)
        self._seen: dict[str, set[str]] = {}  # agent_id -> 지금까지 관찰에 한 번이라도 나타난 object_id 집합 (object_seen 이벤트용)
        self._known: dict[str, dict[str, dict]] = {}  # agent_id -> object_id -> 마지막으로 본 상태 (관찰의 known_objects)

    # Register a new agent into the environment
    def add_agent(
        self,
        agent_id: str,
        x: float,
        y: float,
        facing: float = 0.0,
        view_radius: float = 100.0,
        view_angle: float = 90.0,
        policy=None,
        rules: list[Rule] | None = None
    ) -> Agent:
        agent = Agent(agent_id, x, y, facing, view_radius, view_angle)
        if policy is not None:
            agent.set_policy(policy)
        for rule in rules or []:
            agent.add_rule(rule)
        self.agents[agent_id] = agent
        self._portals_inside[agent_id] = self._portals_at(x, y)  # 포탈 위에서 시작해도 바로 발동하지 않도록
        return agent

    # Add a rule that applies to every agent in the environment, unconditionally
    def add_rule(self, rule: Rule) -> None:
        self.rules.append(rule)

    # Add a rule that applies only to one specific agent
    def add_agent_rule(self, agent_id: str, rule: Rule) -> None:
        self.agents[agent_id].add_rule(rule)

    # Convenience for a central-agent setup: every subordinate is given an
    # ObeyCommandRule bound to commander_id, so any command it later receives
    # from that agent overrides its own policy. Agents stay symmetric/equal
    # by default; nothing calls this unless a hierarchy is explicitly wanted.
    def set_hierarchy(self, commander_id: str, subordinate_ids: list[str]) -> None:
        for subordinate_id in subordinate_ids:
            self.add_agent_rule(subordinate_id, ObeyCommandRule(commander_id))

    # Run an action through every applicable rule (global, then agent-specific),
    # letting each rule inspect/override it in turn. This is what makes rules
    # binding regardless of what the agent's own AI decided.
    def _enforce_rules(self, agent: Agent, observation: dict, action: dict) -> dict:
        for rule in self.rules:
            action = rule.enforce(agent, observation, action)
        for rule in agent.rules:
            action = rule.enforce(agent, observation, action)
        return action

    def remove_agent(self, agent_id: str) -> None:
        del self.agents[agent_id]

    # 실제 이동 계산(경계/충돌 처리)은 physics.py의 PhysicsEngine에 위임
    # coop 물품을 들고 있으면 주변에 도와줄 에이전트가 모자랄 때 이동 자체가 막힘.
    # 이동 후 포탈 진입 여부를 판정. 이동하려는 방향으로 몸을 돌림(막혀서 못 움직여도 돌아봄)
    def move_agent(self, agent_id: str, dx: float, dy: float, *, preserve_facing: bool = False) -> None:
        agent = self.agents[agent_id]
        start_x, start_y = agent.x, agent.y
        distance = math.hypot(dx, dy)
        requested_distance = distance
        if self.max_move is not None and distance > self.max_move:
            dx, dy = dx / distance * self.max_move, dy / distance * self.max_move
        distance = math.hypot(dx, dy)
        if (dx or dy) and not preserve_facing:
            agent.facing = math.degrees(math.atan2(dy, dx)) % 360
        blocked_by_helpers = False
        for obj in agent.inventory:
            if obj.get("category") == ITEM_COOP and len(self._helpers_near(agent, agent.x, agent.y)) + 1 < obj["required_agents"]:
                self._log("move_blocked", [agent_id], object_id=obj["object_id"], reason="not_enough_helpers")
                blocked_by_helpers = True
                break
        if not blocked_by_helpers:
            agent.x, agent.y = self.physics.resolve_move(self, agent, dx, dy)
        actual_dx, actual_dy = agent.x - start_x, agent.y - start_y
        actual_distance = math.hypot(actual_dx, actual_dy)
        agent.last_move = {
            "step": self.step_count,
            "requested_distance": requested_distance,
            "distance": actual_distance,
            "dx": actual_dx,
            "dy": actual_dy,
            "blocked": not math.isclose(actual_distance, distance, rel_tol=1e-9, abs_tol=1e-9),
            "limited": requested_distance > distance,
        }
        if blocked_by_helpers:
            return
        self._check_portals(agent)

    def move_forward(self, agent_id: str, distance: float) -> None:
        """Move a nonnegative fractional distance along the current heading."""
        if (
            not isinstance(distance, (int, float)) or isinstance(distance, bool)
            or not math.isfinite(distance) or distance < 0
        ):
            raise ValueError("distance must be a finite, nonnegative number")
        dx, dy = self.agents[agent_id].heading
        self.move_agent(agent_id, distance * dx, distance * dy, preserve_facing=True)

    # 제자리에서 바라보는 방향만 바꿈 (주변 둘러보기용). facing은 도 단위 절대 방향으로
    # 0=오른쪽(+x), 90=아래(+y), 180=왼쪽, 270=위 - _is_visible의 atan2(dy, dx) 기준과 동일
    def turn_agent(self, agent_id: str, facing: float) -> None:
        self.agents[agent_id].facing = facing % 360

    # ---- Plain interactable objects (items) ----

    # Place an interactable object into the environment (not another agent)
    def add_object(self, object_id: str, x: float, y: float, object_type: str = "item") -> None:
        self.objects[object_id] = {
            "object_id": object_id,
            "x": x,
            "y": y,
            "type": object_type
        }

    # 분류가 있는 물품 배치. category:
    #   ITEM_NORMAL("normal") - 혼자 줍고 옮길 수 있는 일반 물품 (add_object로 만든 item과 동일)
    #   ITEM_COOP("coop")     - required_agents명(본인 포함)이 interact_radius 안에 함께 있어야만
    #                           주울 수 있고, 들고 있는 동안에도 그만큼 곁에 있어야 이동 가능
    #   ITEM_TRAP("trap")     - 줍는 순간 seals의 문들이 영구 봉인(sealed)되어 어떤 수단으로도
    #                           열리지 않게 되고, env.failure에 원인이 기록됨 (게임 불가능 상태)
    # disguised=True(trap 전용): 관찰에는 일반 물품(normal)으로 보임 - 정보를 공유/검증하지
    # 않으면 함정을 구분할 수 없는 상황을 만들 때 사용 (clue와 조합)
    def add_item(
        self,
        item_id: str,
        x: float,
        y: float,
        category: str = ITEM_NORMAL,
        required_agents: int = 2,
        seals: list[str] = None,
        disguised: bool = False
    ) -> None:
        if category not in ITEM_CATEGORIES:
            raise ValueError(f"unknown item category: {category!r} (expected one of {ITEM_CATEGORIES})")
        item = {
            "object_id": item_id,
            "x": x,
            "y": y,
            "type": "item",
            "category": category
        }
        if category == ITEM_COOP:
            item["required_agents"] = required_agents
        elif category == ITEM_TRAP:
            item["seals"] = list(seals or [])
            item["disguised"] = disguised
        self.objects[item_id] = item

    def remove_object(self, object_id: str) -> None:
        del self.objects[object_id]

    # (x, y)의 interact_radius 안에 있는, agent 본인을 제외한 다른 에이전트 id 목록 (coop 물품용)
    def _helpers_near(self, agent: Agent, x: float, y: float) -> list[str]:
        return [
            other.agent_id for other in self.agents.values()
            if other is not agent and math.hypot(other.x - x, other.y - y) <= self.interact_radius
        ]

    # 현재 step_count로 event_log에 기록하는 단축 함수
    def _log(self, event_type: str, agent_ids: list[str], **fields) -> None:
        self.event_log.record(self.step_count, event_type, agent_ids, **fields)

    # Only free-standing items/keys within interact_radius can be picked up
    # (doors, buttons, levers, pressure plates cannot)
    def pick_up(self, agent_id: str, object_id: str) -> None:
        agent = self.agents[agent_id]
        obj = self.objects.get(object_id)
        if obj is None or obj["type"] not in ("item", "key"):
            return
        if math.hypot(agent.x - obj["x"], agent.y - obj["y"]) > self.interact_radius:
            return
        category = obj.get("category", ITEM_NORMAL)
        helpers = self._helpers_near(agent, obj["x"], obj["y"]) if category == ITEM_COOP else []
        if category == ITEM_COOP and len(helpers) + 1 < obj["required_agents"]:
            self._log("pickup_blocked", [agent_id], object_id=object_id, reason="not_enough_helpers")
            return
        self.objects.pop(object_id)
        agent.inventory.append(obj)
        # coop 물품은 함께 들어준 에이전트도 공로자로 agent_ids에 포함 (helper_ids로 구분 가능)
        self._log("item_picked_up", [agent_id, *helpers], object_id=object_id,
                  object_type=obj["type"], category=category, helper_ids=helpers)
        if category == ITEM_TRAP:
            self._trigger_trap(agent_id, obj)

    # trap 발동: 연결된 문을 잠그고 영구 봉인. 최초 실패 원인만 failure에 남김
    def _trigger_trap(self, agent_id: str, trap: dict) -> None:
        self._log("trap_triggered", [agent_id], object_id=trap["object_id"], sealed_doors=list(trap["seals"]))
        for door_id in trap["seals"]:
            door = self.objects.get(door_id)
            if door is not None:
                self._set_door_locked(door, True, "trap", [agent_id], trap["object_id"])
                door["sealed"] = True
        if self.failure is None:
            self.failure = {
                "step": self.step_count,
                "agent_id": agent_id,
                "object_id": trap["object_id"],
                "sealed_doors": list(trap["seals"])
            }

    # 봉인된(sealed) 문은 열쇠/버튼/레버/압력판 어느 것으로도 잠금 상태가 바뀌지 않음.
    # 상태가 실제로 바뀐 경우에만 door_unlocked/door_locked 이벤트를 남김
    # cause: "key"/"button"/"lever"/"pressure_plate"/"trap", source: 원인 오브젝트 id(압력판은 id 목록)
    def _set_door_locked(self, door: dict, locked: bool, cause: str, agent_ids: list[str], source) -> None:
        if door.get("sealed") or door["locked"] == locked:
            return
        door["locked"] = locked
        self._log("door_locked" if locked else "door_unlocked", agent_ids,
                  door_id=door["object_id"], cause=cause, source=source)

    # ---- Portal ----

    # 반경 안으로 진입하면 (dest_x, dest_y)로 즉시 순간이동하는 바닥 장치. 별도 action 없음.
    # "진입하는 순간"에만 발동하므로 포탈 위에 계속 서 있거나, 도착 지점이 다른 포탈 위여도
    # 연쇄/왕복 이동이 일어나지 않음 (한 번 벗어났다가 다시 들어와야 재발동).
    # 목적지가 잠긴 문 안쪽이면 발동하지 않음
    def add_portal(
        self,
        portal_id: str,
        x: float,
        y: float,
        dest_x: float,
        dest_y: float,
        radius: float = 10.0
    ) -> None:
        self.objects[portal_id] = {
            "object_id": portal_id,
            "x": x,
            "y": y,
            "type": "portal",
            "dest_x": dest_x,
            "dest_y": dest_y,
            "radius": radius
        }

    def _portals_at(self, x: float, y: float) -> set[str]:
        return {
            obj["object_id"] for obj in self.objects.values()
            if obj["type"] == "portal" and math.hypot(x - obj["x"], y - obj["y"]) <= obj["radius"]
        }

    def _check_portals(self, agent: Agent) -> None:
        inside_before = self._portals_inside.get(agent.agent_id, set())
        inside_now = self._portals_at(agent.x, agent.y)
        entered = sorted(inside_now - inside_before)
        if entered:
            portal = self.objects[entered[0]]
            dest = (portal["dest_x"], portal["dest_y"])
            if not any(
                obj["type"] == "door" and obj["locked"]
                and math.hypot(dest[0] - obj["x"], dest[1] - obj["y"]) <= obj["radius"]
                for obj in self.objects.values()
            ):
                origin = (agent.x, agent.y)
                agent.x, agent.y = dest
                self._log("portal_used", [agent.agent_id], portal_id=portal["object_id"], origin=origin, dest=dest)
                inside_now = self._portals_at(agent.x, agent.y)
        self._portals_inside[agent.agent_id] = inside_now

    def drop(self, agent_id: str, object_id: str) -> None:
        agent = self.agents[agent_id]
        obj = next((o for o in agent.inventory if o["object_id"] == object_id), None)
        if obj is None:
            return
        agent.inventory.remove(obj)
        obj["x"], obj["y"] = agent.x, agent.y
        self.objects[object_id] = obj
        self._log("item_dropped", [agent_id], object_id=object_id, position=(agent.x, agent.y))

    # ---- Game elements: door / key / button ----

    # locked=True and hidden=True can be combined to make a locked, hidden door
    def add_door(
        self,
        door_id: str,
        x: float,
        y: float,
        locked: bool = True,
        radius: float = 10.0,
        hidden: bool = False
    ) -> None:
        self.objects[door_id] = {
            "object_id": door_id,
            "x": x,
            "y": y,
            "type": "door",
            "locked": locked,
            "radius": radius,   # 이 반경 안으로는 잠긴 동안 이동 불가
            "hidden": hidden    # 숨겨진 문: 아주 가까이 가야 관찰에 드러남
        }

    # unlocks: 이 열쇠가 여는 door_id
    def add_key(self, key_id: str, x: float, y: float, unlocks: str) -> None:
        self.objects[key_id] = {
            "object_id": key_id,
            "x": x,
            "y": y,
            "type": "key",
            "unlocks": unlocks
        }

    # linked_door_id: 이 버튼이 여닫는 door_id
    def add_button(self, button_id: str, x: float, y: float, linked_door_id: str) -> None:
        self.objects[button_id] = {
            "object_id": button_id,
            "x": x,
            "y": y,
            "type": "button",
            "linked_door_id": linked_door_id
        }

    # linked_door_ids: 이 레버가 함께 여닫는 door_id 목록 (여러 문 동시 제어 가능)
    def add_lever(self, lever_id: str, x: float, y: float, linked_door_ids: list[str]) -> None:
        self.objects[lever_id] = {
            "object_id": lever_id,
            "x": x,
            "y": y,
            "type": "lever",
            "on": False,
            "linked_door_ids": list(linked_door_ids)
        }

    # linked_door_id: 이 압력판이 여는 door_id. 별도 action 없이 매 step마다 자동 판정
    def add_pressure_plate(
        self,
        plate_id: str,
        x: float,
        y: float,
        linked_door_id: str,
        radius: float = 10.0
    ) -> None:
        self.objects[plate_id] = {
            "object_id": plate_id,
            "x": x,
            "y": y,
            "type": "pressure_plate",
            "radius": radius,
            "linked_door_id": linked_door_id
        }

    # content: 실험 설계자가 정의하는 임의의 정보(문자열/딕셔너리 등, 게임 로직에는 아무
    # 영향 없음). hidden=True(기본값)면 add_door의 hidden 오브젝트와 동일하게 interact_radius
    # 안까지 가야만 observation의 visible_objects에 나타남 - 한 에이전트만 우연히 가까이
    # 가서 내용을 보고, 나머지는 그 에이전트가 메시지로 전달해줘야만 알 수 있는 정보
    # 비대칭 상황을 만들기 위한 용도. hidden=False로 두면 일반 물체처럼 시야각 안에서
    # 멀리서도 보임(예: 멀리서도 읽히는 표지판)
    def add_clue(self, clue_id: str, x: float, y: float, content, hidden: bool = True) -> None:
        self.objects[clue_id] = {
            "object_id": clue_id,
            "x": x,
            "y": y,
            "type": "clue",
            "content": content,
            "hidden": hidden
        }

    # waypoints를 순서대로 순회하며 매 step마다 자동으로 위치가 갱신되는 오브젝트.
    # 물리적 충돌(막힘)은 없음(정적/동적 충돌 구조는 world_core 물리 엔진의 몫) - 그냥
    # 시간에 따라 위치가 바뀌는 정보만 제공. 에이전트는 이 움직임을 관찰해서 추적/예측/회피
    # 하는 로직을 스스로 짜야 하므로, 목표가 가만히 있을 때보다 훨씬 더 코드(반복/조건)가
    # 필요한 상황을 만들 수 있음.
    # object_type: 이 오브젝트의 type (기본 "hazard", 원하는 이름 아무거나 가능)
    # extra: 필요하면 추가 필드(dict)를 그대로 오브젝트에 병합 (예: 움직이는 열쇠를 만들고
    # 싶으면 object_type="key", extra={"unlocks": "d1"})
    def add_mover(
        self,
        mover_id: str,
        x: float,
        y: float,
        waypoints: list[tuple[float, float]],
        speed: float = 5.0,
        object_type: str = "hazard",
        loop: bool = True,
        extra: dict = None
    ) -> None:
        self.objects[mover_id] = {
            "object_id": mover_id,
            "x": x,
            "y": y,
            "type": object_type,
            "waypoints": [tuple(w) for w in waypoints],
            "target_index": 0,
            "speed": speed,
            "loop": loop,
            **(extra or {})
        }

    # 등록된 mover(waypoints가 있는 오브젝트) 전부를 한 스텝만큼 목표 waypoint 쪽으로
    # 이동시키고, 도착하면 다음 waypoint로(마지막이면 loop 여부에 따라 처음으로 순환하거나
    # 그대로 정지) 넘어감. step() 시작 시 자동 호출됨 (에이전트의 action과 무관하게 동작)
    def _update_movers(self) -> None:
        for obj in self.objects.values():
            waypoints = obj.get("waypoints")
            if not waypoints:
                continue

            target_x, target_y = waypoints[obj["target_index"]]
            dx, dy = target_x - obj["x"], target_y - obj["y"]
            distance = math.hypot(dx, dy)

            if distance <= obj["speed"]:
                obj["x"], obj["y"] = target_x, target_y
                if obj["target_index"] + 1 < len(waypoints):
                    obj["target_index"] += 1
                elif obj["loop"]:
                    obj["target_index"] = 0
            else:
                scale = obj["speed"] / distance
                obj["x"] += dx * scale
                obj["y"] += dy * scale

    # Consume a key from inventory to unlock its matching door (must be nearby)
    def use_key(self, agent_id: str, key_object_id: str) -> None:
        agent = self.agents[agent_id]
        key = next((o for o in agent.inventory if o["object_id"] == key_object_id), None)
        if key is None or key["type"] != "key":
            return

        door = self.objects.get(key["unlocks"])
        if door is None:
            return
        # A locked door's own radius keeps the agent from physically reaching its
        # center (see physics.py), so reach must be measured from the door's edge,
        # not its center - otherwise any door with radius >= interact_radius could
        # never be approached close enough to satisfy this check.
        reach = self.interact_radius + door.get("radius", 0.0)
        if math.hypot(agent.x - door["x"], agent.y - door["y"]) > reach:
            return

        self._set_door_locked(door, False, "key", [agent_id], key_object_id)
        agent.inventory.remove(key)

    # Press a nearby button to toggle its linked door's locked state
    def press_button(self, agent_id: str, button_id: str) -> None:
        agent = self.agents[agent_id]
        button = self.objects.get(button_id)
        if button is None or button["type"] != "button":
            return
        if math.hypot(agent.x - button["x"], agent.y - button["y"]) > self.interact_radius:
            return

        door = self.objects.get(button["linked_door_id"])
        if door is not None:
            self._set_door_locked(door, not door["locked"], "button", [agent_id], button_id)

    # Pull a nearby lever: flips its on/off state and locks/unlocks every
    # linked door to match (on -> unlocked). Unlike a button, the state
    # persists explicitly and can drive several doors at once.
    def pull_lever(self, agent_id: str, lever_id: str) -> None:
        agent = self.agents[agent_id]
        lever = self.objects.get(lever_id)
        if lever is None or lever["type"] != "lever":
            return
        if math.hypot(agent.x - lever["x"], agent.y - lever["y"]) > self.interact_radius:
            return

        lever["on"] = not lever["on"]
        self._log("lever_pulled", [agent_id], lever_id=lever_id, on=lever["on"])
        for door_id in lever["linked_door_ids"]:
            door = self.objects.get(door_id)
            if door is not None:
                self._set_door_locked(door, not lever["on"], "lever", [agent_id], lever_id)

    # Passive trigger, checked every step (no explicit action): a pressure
    # plate's linked door stays unlocked only while an agent is standing on it.
    # 같은 door_id에 압력판이 여러 개 연결된 경우, 전부 동시에 밟혀야만 문이 열리도록
    # (AND 조건) 판정한다 - 서로 떨어진 위치의 판을 각자 다른 에이전트가 동시에 밟고
    # 있어야 하는 "무거운 문"류 협력 퍼즐을 add_pressure_plate를 여러 번 호출하는 것만으로
    # 만들 수 있게 하기 위함. 판이 하나뿐인 문은 기존과 동일하게 동작
    # 판마다 위에 선 에이전트가 바뀌면 plate_entered/plate_left 이벤트를 남김. 문이 열리면 그
    # 순간 연결된 판들을 밟고 있던 에이전트 전원을, 닫히면 이번에 판에서 내려간 에이전트를
    # 원인으로 기록 (남아서 버티던 쪽이 아니라 이탈한 쪽이 문을 닫은 것이므로)
    def _update_pressure_plates(self) -> None:
        door_all_occupied: dict[str, bool] = {}
        door_plates: dict[str, list[str]] = {}
        door_occupants: dict[str, set[str]] = {}
        door_leavers: dict[str, set[str]] = {}
        for obj in self.objects.values():
            if obj["type"] != "pressure_plate":
                continue

            plate_id = obj["object_id"]
            occupants = {
                agent.agent_id for agent in self.agents.values()
                if math.hypot(agent.x - obj["x"], agent.y - obj["y"]) <= obj["radius"]
            }
            before = self._plate_occupants.get(plate_id, set())
            for agent_id in sorted(occupants - before):
                self._log("plate_entered", [agent_id], plate_id=plate_id)
            for agent_id in sorted(before - occupants):
                self._log("plate_left", [agent_id], plate_id=plate_id)
            self._plate_occupants[plate_id] = occupants

            door_id = obj["linked_door_id"]
            door_all_occupied[door_id] = door_all_occupied.get(door_id, True) and bool(occupants)
            door_plates.setdefault(door_id, []).append(plate_id)
            door_occupants.setdefault(door_id, set()).update(occupants)
            door_leavers.setdefault(door_id, set()).update(before - occupants)

        for door_id, all_occupied in door_all_occupied.items():
            door = self.objects.get(door_id)
            if door is not None:
                causers = door_occupants[door_id] if all_occupied else door_leavers[door_id]
                self._set_door_locked(door, not all_occupied, "pressure_plate", sorted(causers), door_plates[door_id])

    # ---- Messaging ----

    def _deliver(self, receiver_id: str, message: dict) -> None:
        if not isinstance(receiver_id, str) or receiver_id not in self.agents:  # 존재하지 않는/누락된 receiver_id는 조용히 무시
            return
        # inbox는 비워지지 않고 계속 쌓이므로, 새 메시지와 예전 메시지를 구분할 수 있게 전달 시점을 붙임
        message["step"] = self.step_count
        self.agents[receiver_id].inbox.append(message)
        self.message_log.record(self.step_count, receiver_id, message)

    def _broadcast(self, sender_id: str, message: dict) -> None:
        for other_id in self.agents:
            if other_id != sender_id:
                self._deliver(other_id, message)

    # Free-text message from one agent to another
    def send_message(self, sender_id: str, receiver_id: str, content: str) -> None:
        self._deliver(receiver_id, {
            "type": "text",
            "from": sender_id,
            "content": content
        })

    # Assert a fact/claim about something (subject) to another agent.
    # Kept separate from send_message so failure analysis can tell "an agent
    # stated X" apart from ordinary chatter, and check whether the claim was true.
    def share_belief(self, sender_id: str, receiver_id: str, subject: str, claim) -> None:
        self._deliver(receiver_id, {
            "type": "belief",
            "from": sender_id,
            "subject": subject,
            "claim": claim
        })

    # Ask another agent for information about something (subject)
    def request_info(self, sender_id: str, receiver_id: str, subject: str) -> None:
        self._deliver(receiver_id, {
            "type": "request",
            "from": sender_id,
            "subject": subject
        })

    # Acknowledge/agree (or disagree) with a prior belief or request (subject)
    def confirm(self, sender_id: str, receiver_id: str, subject: str, agree: bool = True) -> None:
        self._deliver(receiver_id, {
            "type": "confirm",
            "from": sender_id,
            "subject": subject,
            "agree": agree
        })

    # ---- Coordination / planning declarations ----
    # Broadcast to every other agent, since roles/tasks are public commitments
    # rather than a private exchange between two agents.

    def claim_role(self, agent_id: str, role: str) -> None:
        self._broadcast(agent_id, {"type": "role_claim", "from": agent_id, "role": role})

    def claim_task(self, agent_id: str, task: str) -> None:
        self._broadcast(agent_id, {"type": "task_claim", "from": agent_id, "task": task})

    # Send a directive to another agent. On its own this is just a delivered
    # message (like belief/request) with no special effect; it only becomes
    # binding for a receiver that has an ObeyCommandRule pointed at sender_id
    # (see Environment.set_hierarchy). command should be an action dict
    # (e.g. {"type": "move", "dx": 5, "dy": 0}) for ObeyCommandRule to execute.
    def issue_command(self, sender_id: str, receiver_id: str, command) -> None:
        self._deliver(receiver_id, {
            "type": "command",
            "from": sender_id,
            "command": command,
            "handled": False
        })

    # ---- Observation ----

    # Whether obj_x, obj_y falls inside agent's view cone (radius + angle)
    def _is_visible(self, agent: Agent, obj_x: float, obj_y: float) -> bool:
        dx = obj_x - agent.x
        dy = obj_y - agent.y
        distance = math.hypot(dx, dy)
        if distance > agent.view_radius:
            return False
        if distance == 0:
            return True

        angle_to_obj = math.degrees(math.atan2(dy, dx)) % 360
        facing = agent.facing % 360
        diff = abs((angle_to_obj - facing + 180) % 360 - 180)
        if diff > agent.view_angle / 2:
            return False
        return self._has_line_of_sight(agent.x, agent.y, obj_x, obj_y)

    # 시야를 가리는 벽 목록을 (x, y, width, height)로 반환. 벽 자체는 world_core 담당이므로
    # game_map.walls를 읽기만 함 - 항목은 world_core.Wall처럼 .rect(pygame.Rect)를 가지거나,
    # .x/.y/.width/.height를 직접 가진 객체. game_map에 walls가 없으면 가리는 것 없음
    def _walls(self) -> list[tuple[float, float, float, float]]:
        walls = []
        for wall in getattr(self.game_map, "walls", None) or []:
            rect = getattr(wall, "rect", wall)
            walls.append((rect.x, rect.y, rect.width, rect.height))
        return walls

    # (x0, y0)에서 (x1, y1)까지의 선분이 어떤 벽도 통과하지 않으면 True (Liang-Barsky 선분 클리핑).
    # 선분 양 끝이 벽 가장자리에 살짝 닿는 것(벽에 붙여 놓은 물체 등)은 가린 것으로 치지 않음
    def _has_line_of_sight(self, x0: float, y0: float, x1: float, y1: float) -> bool:
        dx, dy = x1 - x0, y1 - y0
        eps = 1e-6
        for wx, wy, ww, wh in self._walls():
            t_enter, t_exit = 0.0, 1.0
            for p, q in ((-dx, x0 - wx), (dx, wx + ww - x0), (-dy, y0 - wy), (dy, wy + wh - y0)):
                if p == 0:
                    if q < 0:  # 이 축과 평행하고 벽 범위 밖 -> 이 벽과는 만나지 않음
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

    # Build one agent's observation: own state + visible objects only.
    # Other agents are intentionally NOT included, since MACI evaluates
    # whether agents can coordinate without directly reading each other's state.
    # Objects marked "hidden" (e.g. hidden doors) only appear once the agent
    # is within interact_radius, regardless of the normal view cone.
    # 일반 물체든 hidden 물체든 벽에 가려지면 보이지 않음
    def get_observation(self, agent_id: str) -> dict:
        agent = self.agents[agent_id]
        visible_objects = []

        for obj in self.objects.values():
            if obj.get("hidden", False):
                distance = math.hypot(obj["x"] - agent.x, obj["y"] - agent.y)
                if distance <= self.interact_radius and self._has_line_of_sight(agent.x, agent.y, obj["x"], obj["y"]):
                    visible_objects.append(obj)
            elif self._is_visible(agent, obj["x"], obj["y"]):
                visible_objects.append(obj)

        # 위장된 trap은 관찰상 일반 물품으로 보이게 함 (실제 objects는 그대로)
        visible_objects = [self._disguise(obj) for obj in visible_objects]

        # 기억: 예전에 본 물체의 "마지막으로 본 상태"에 지금 보이는 것을 덮어씀. 저장은
        # _record_sightings()가 step()에서 함 (여기서는 계산만 - Rule 검사용 관찰과 구분)
        known_objects = copy.deepcopy(self._known.get(agent_id, {}))
        for obj in visible_objects:
            known_objects[obj["object_id"]] = {**copy.deepcopy(obj), "last_seen_step": self.step_count}

        return {
            "self": {
                **agent.spatial_state(),
                "max_move": self.max_move,
                # deep copy: policy 코드가 observation을 직접 mutate해서(예: inventory에
                # 아이템을 그냥 append) pick_up 없이 인벤토리를 조작하는 걸 막기 위함
                "inventory": [self._disguise(obj) for obj in agent.inventory],
                "step": self.step_count,
                "map_width": self.game_map.map_width,
                "map_height": self.game_map.map_height
            },
            # deep copy: policy 코드가 visible_objects의 오브젝트를 직접 mutate해서(예:
            # door["locked"] = False) Rule/interact_radius 검사를 우회해 환경을 직접
            # 조작하는 걸 막기 위함 - 생성된 코드가 action(dict)만 반환하는 순수 함수여야
            # 한다는 전제를 실제로 강제함
            "visible_objects": visible_objects,  # _disguise()가 이미 deep copy함
            # 지금까지 본 적 있는 모든 물체의 마지막으로 본 상태 (object_id -> 물체 + last_seen_step).
            # CodePolicy 코드는 매 step 새 프로세스에서 실행되어 스스로 기억을 못 하므로 환경이 제공
            "known_objects": known_objects,
            # 시야 반경 안에 걸친 벽 [x, y, width, height] - 벽은 이동을 막으므로 길찾기용
            "walls": self._walls_near(agent.x, agent.y, agent.view_radius),
            # 에이전트가 직접 쓰는 메모장: action에 "memory": {...}를 넣어 반환하면 다음 step부터
            # 여기로 돌아옴 (탐색한 곳, 계획 등 자유롭게 저장)
            "memory": copy.deepcopy(agent.memory),
            # inbox는 목록만 복사하고 메시지 객체는 그대로 공유: 동시 실행에서 이번 step에 다른
            # 에이전트가 보낸 메시지가 이미 만든 관찰에 끼어들면 안 되지만, ObeyCommandRule이 처리한
            # 명령 메시지에 표시하는 message["handled"] = True는 실제 agent.inbox에 반영돼야 함
            "inbox": list(agent.inbox)
        }

    # (x, y)에서 radius 안에 일부라도 걸친 벽 목록 [x, y, width, height]
    def _walls_near(self, x: float, y: float, radius: float) -> list[list[float]]:
        near = []
        for wx, wy, ww, wh in self._walls():
            nearest_x = min(max(x, wx), wx + ww)
            nearest_y = min(max(y, wy), wy + wh)
            if math.hypot(x - nearest_x, y - nearest_y) <= radius:
                near.append([wx, wy, ww, wh])
        return near

    # deep copy를 반환. 위장된 trap이면 normal 물품과 구분되지 않게 trap 전용 필드를 제거
    def _disguise(self, obj: dict) -> dict:
        obj = copy.deepcopy(obj)
        if obj.get("category") == ITEM_TRAP and obj.get("disguised"):
            obj["category"] = ITEM_NORMAL
            obj.pop("seals", None)
            obj.pop("disguised", None)
        return obj

    # 에이전트가 실제로 받은 관찰(step()에서 만든 것)에 처음 나타난 물체마다 object_seen 이벤트를
    # 남김. apply_action 안의 Rule 검사용 관찰은 에이전트에게 전달되지 않으므로 여기서 세지 않음
    def _record_sightings(self, agent_id: str, observation: dict) -> None:
        self._known[agent_id] = copy.deepcopy(observation["known_objects"])
        seen = self._seen.setdefault(agent_id, set())
        for obj in observation["visible_objects"]:
            if obj["object_id"] not in seen:
                seen.add(obj["object_id"])
                self._log("object_seen", [agent_id], object_id=obj["object_id"], object_type=obj["type"])

    # ---- Action routing / simulation loop ----

    # Route a decided action to the matching environment operation.
    # Rules are enforced here (not just in step()), so any action reaching
    # the environment is already filtered/overridden — agents cannot bypass
    # their rules by any path.
    # observation: Rule 검사에 쓸 관찰. step()은 결정에 쓴 step 시작 시점의 관찰을 넘겨, 같은 step에
    # 먼저 적용된 다른 에이전트의 행동(예: 방금 보낸 명령)이 적용 순서에 따라 끼어들지 않게 함.
    # 생략하면 지금 상태로 새로 만듦
    def apply_action(self, agent_id: str, action: dict, observation: dict = None) -> dict:
        agent = self.agents[agent_id]
        if observation is None:
            observation = self.get_observation(agent_id)
        action = self._enforce_rules(agent, observation, action)
        if not self._is_well_formed(action):
            # LLM이 짠 코드가 {"dx": "5"}나 {"object_id": [...]}를 반환하면 아래 처리에서
            # TypeError로 회차 전체가 죽거나 NaN 좌표가 생기므로, 그 에이전트의 이번 행동만 무효 처리
            self._log("invalid_action", [agent_id], action=action)
            return {"type": "noop"}
        action_type = action.get("type", "noop")

        if action_type == "move":
            self.move_agent(agent_id, action.get("dx", 0), action.get("dy", 0))
        elif action_type == "move_forward":
            self.move_forward(agent_id, action["distance"])
        elif action_type == "turn":
            self.turn_agent(agent_id, action.get("facing", self.agents[agent_id].facing))
        elif action_type == "pick_up":
            self.pick_up(agent_id, action.get("object_id"))
        elif action_type == "drop":
            self.drop(agent_id, action.get("object_id"))
        elif action_type == "use_key":
            self.use_key(agent_id, action.get("key_id"))
        elif action_type == "press_button":
            self.press_button(agent_id, action.get("button_id"))
        elif action_type == "pull_lever":
            self.pull_lever(agent_id, action.get("lever_id"))
        elif action_type == "send_message":
            self.send_message(agent_id, action.get("receiver_id"), action.get("content"))
        elif action_type == "share_belief":
            self.share_belief(agent_id, action.get("receiver_id"), action.get("subject"), action.get("claim"))
        elif action_type == "request_info":
            self.request_info(agent_id, action.get("receiver_id"), action.get("subject"))
        elif action_type == "confirm":
            self.confirm(agent_id, action.get("receiver_id"), action.get("subject"), action.get("agree", True))
        elif action_type == "claim_role":
            self.claim_role(agent_id, action.get("role"))
        elif action_type == "claim_task":
            self.claim_task(agent_id, action.get("task"))
        elif action_type == "issue_command":
            self.issue_command(agent_id, action.get("receiver_id"), action.get("command"))

        return action

    # 숫자 필드는 유한한 실수(bool 제외), id 필드는 문자열(또는 생략)이어야 함
    _NUMBER_FIELDS = ("dx", "dy", "facing", "distance")
    _ID_FIELDS = ("object_id", "key_id", "button_id", "lever_id", "receiver_id")

    def _is_well_formed(self, action) -> bool:
        if not isinstance(action, dict):
            return False
        for key in self._NUMBER_FIELDS:
            value = action.get(key, 0)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                return False
        if action.get("type") == "move_forward" and ("distance" not in action or action["distance"] < 0):
            return False
        return all(isinstance(action.get(key), (str, type(None))) for key in self._ID_FIELDS)

    # 한 틱을 동시 실행으로 진행: 모든 에이전트가 같은 시점의 세계를 관찰하고, 각자의 policy가
    # 병렬로(스레드) 결정한 뒤, 그 행동들을 한꺼번에 적용하고 마지막에 압력판을 판정함.
    # 같은 물건을 동시에 집는 것처럼 적용 순서가 결과를 가르는 충돌이 있으므로, 한 에이전트가
    # 늘 먼저 적용되는 편향이 없도록 적용 순서를 step마다 한 칸씩 돌림 (결정적이라 재현 가능)
    def step(self) -> None:
        self.step_count += 1
        self._update_movers()
        agent_ids = list(self.agents.keys())
        if not agent_ids:
            self._update_pressure_plates()
            return

        observations = {}
        for agent_id in agent_ids:
            observations[agent_id] = self.get_observation(agent_id)
            self._record_sightings(agent_id, observations[agent_id])

        with ThreadPoolExecutor(max_workers=len(agent_ids)) as pool:
            decided = pool.map(lambda a: self.agents[a].decide(observations[a]), agent_ids)
            actions = dict(zip(agent_ids, decided))

        shift = self.step_count % len(agent_ids)
        for agent_id in agent_ids[shift:] + agent_ids[:shift]:
            final_action = self.apply_action(agent_id, actions[agent_id], observations[agent_id])
            self._store_memory(agent_id, actions[agent_id])
            self.decision_log.record(self.step_count, agent_id, observations[agent_id], actions[agent_id], final_action)

        self._update_pressure_plates()

    # policy가 고른 action에 "memory": dict가 있으면 다음 관찰의 memory로 저장. Rule이 action을
    # 바꿔치기해도 메모는 에이전트 자신의 기록이므로 원래 action 기준. 너무 크면(직렬화 20000자
    # 초과) 무시해 관찰/로그가 비대해지는 것을 막음
    MEMORY_MAX_CHARS = 20000

    def _store_memory(self, agent_id: str, action) -> None:
        memory = action.get("memory") if isinstance(action, dict) else None
        if not isinstance(memory, dict):
            return
        try:
            if len(json.dumps(memory)) > self.MEMORY_MAX_CHARS:
                return
        except (TypeError, ValueError):
            return
        self.agents[agent_id].memory = copy.deepcopy(memory)
