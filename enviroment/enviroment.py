import copy
import math

from agent import Agent
from history import DecisionLog, MessageLog
from physics import PhysicsEngine, SimplePhysicsEngine
from rule import Rule, ObeyCommandRule


class Environment:
    def __init__(self, game_map, interact_radius: float = 15.0, physics: PhysicsEngine = None) -> None:
        self.game_map = game_map
        self.interact_radius = interact_radius  # 버튼/문 상호작용 가능 거리
        self.physics = physics or SimplePhysicsEngine()  # 이동/충돌 계산 위임 대상 (교체 가능)
        self.agents: dict[str, Agent] = {}
        self.objects: dict[str, dict] = {}
        self.rules: list[Rule] = []  # 모든 에이전트에게 동일하게 적용되는 전역 강제 규칙
        self.step_count = 0  # step()이 몇 번 진행됐는지 (메시지 기록에 시점 표시용)
        self.message_log = MessageLog()  # 오간 메시지 전부 기록 (반사실적 재현 분석용)
        self.decision_log = DecisionLog()  # 매 step 각 에이전트의 관찰/결정/실제 실행 기록 (반사실적 재현 분석용)

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
    def move_agent(self, agent_id: str, dx: float, dy: float) -> None:
        agent = self.agents[agent_id]
        agent.x, agent.y = self.physics.resolve_move(self, agent, dx, dy)

    # ---- Plain interactable objects (items) ----

    # Place an interactable object into the environment (not another agent)
    def add_object(self, object_id: str, x: float, y: float, object_type: str = "item") -> None:
        self.objects[object_id] = {
            "object_id": object_id,
            "x": x,
            "y": y,
            "type": object_type
        }

    def remove_object(self, object_id: str) -> None:
        del self.objects[object_id]

    # Only free-standing items/keys within interact_radius can be picked up
    # (doors, buttons, levers, pressure plates cannot)
    def pick_up(self, agent_id: str, object_id: str) -> None:
        agent = self.agents[agent_id]
        obj = self.objects.get(object_id)
        if obj is None or obj["type"] not in ("item", "key"):
            return
        if math.hypot(agent.x - obj["x"], agent.y - obj["y"]) > self.interact_radius:
            return
        self.objects.pop(object_id)
        agent.inventory.append(obj)

    def drop(self, agent_id: str, object_id: str) -> None:
        agent = self.agents[agent_id]
        obj = next((o for o in agent.inventory if o["object_id"] == object_id), None)
        if obj is None:
            return
        agent.inventory.remove(obj)
        obj["x"], obj["y"] = agent.x, agent.y
        self.objects[object_id] = obj

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

        door["locked"] = False
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
            door["locked"] = not door["locked"]

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
        for door_id in lever["linked_door_ids"]:
            door = self.objects.get(door_id)
            if door is not None:
                door["locked"] = not lever["on"]

    # Passive trigger, checked every step (no explicit action): a pressure
    # plate's linked door stays unlocked only while an agent is standing on it.
    # 같은 door_id에 압력판이 여러 개 연결된 경우, 전부 동시에 밟혀야만 문이 열리도록
    # (AND 조건) 판정한다 - 서로 떨어진 위치의 판을 각자 다른 에이전트가 동시에 밟고
    # 있어야 하는 "무거운 문"류 협력 퍼즐을 add_pressure_plate를 여러 번 호출하는 것만으로
    # 만들 수 있게 하기 위함. 판이 하나뿐인 문은 기존과 동일하게 동작
    def _update_pressure_plates(self) -> None:
        door_all_occupied: dict[str, bool] = {}
        for obj in self.objects.values():
            if obj["type"] != "pressure_plate":
                continue

            occupied = any(
                math.hypot(agent.x - obj["x"], agent.y - obj["y"]) <= obj["radius"]
                for agent in self.agents.values()
            )
            door_id = obj["linked_door_id"]
            door_all_occupied[door_id] = door_all_occupied.get(door_id, True) and occupied

        for door_id, all_occupied in door_all_occupied.items():
            door = self.objects.get(door_id)
            if door is not None:
                door["locked"] = not all_occupied

    # ---- Messaging ----

    def _deliver(self, receiver_id: str, message: dict) -> None:
        if receiver_id not in self.agents:  # 존재하지 않는/누락된 receiver_id는 조용히 무시
            return
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
        return diff <= agent.view_angle / 2

    # Build one agent's observation: own state + visible objects only.
    # Other agents are intentionally NOT included, since MACI evaluates
    # whether agents can coordinate without directly reading each other's state.
    # Objects marked "hidden" (e.g. hidden doors) only appear once the agent
    # is within interact_radius, regardless of the normal view cone.
    def get_observation(self, agent_id: str) -> dict:
        agent = self.agents[agent_id]
        visible_objects = []

        for obj in self.objects.values():
            if obj.get("hidden", False):
                distance = math.hypot(obj["x"] - agent.x, obj["y"] - agent.y)
                if distance <= self.interact_radius:
                    visible_objects.append(obj)
            elif self._is_visible(agent, obj["x"], obj["y"]):
                visible_objects.append(obj)

        return {
            "self": {
                "x": agent.x,
                "y": agent.y,
                "facing": agent.facing,
                # deep copy: policy 코드가 observation을 직접 mutate해서(예: inventory에
                # 아이템을 그냥 append) pick_up 없이 인벤토리를 조작하는 걸 막기 위함
                "inventory": copy.deepcopy(agent.inventory)
            },
            # deep copy: policy 코드가 visible_objects의 오브젝트를 직접 mutate해서(예:
            # door["locked"] = False) Rule/interact_radius 검사를 우회해 환경을 직접
            # 조작하는 걸 막기 위함 - 생성된 코드가 action(dict)만 반환하는 순수 함수여야
            # 한다는 전제를 실제로 강제함
            "visible_objects": copy.deepcopy(visible_objects),
            # inbox는 참조를 그대로 유지: ObeyCommandRule이 처리한 명령 메시지에
            # message["handled"] = True를 표시해 같은 명령이 다시 실행되지 않도록 하는데,
            # 이게 실제 agent.inbox에 반영되려면 복사본이 아니라 같은 객체여야 함
            "inbox": agent.inbox
        }

    # ---- Action routing / simulation loop ----

    # Route a decided action to the matching environment operation.
    # Rules are enforced here (not just in step()), so any action reaching
    # the environment is already filtered/overridden — agents cannot bypass
    # their rules by any path.
    def apply_action(self, agent_id: str, action: dict) -> dict:
        agent = self.agents[agent_id]
        observation = self.get_observation(agent_id)
        action = self._enforce_rules(agent, observation, action)
        action_type = action.get("type", "noop")

        if action_type == "move":
            self.move_agent(agent_id, action.get("dx", 0), action.get("dy", 0))
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

    # Run one simulation tick: pressure plates update first (based on where
    # agents ended up last tick), then every agent observes, decides, and acts
    def step(self) -> None:
        self.step_count += 1
        self._update_pressure_plates()
        self._update_movers()
        for agent_id in list(self.agents.keys()):
            observation = self.get_observation(agent_id)
            action = self.agents[agent_id].decide(observation)
            final_action = self.apply_action(agent_id, action)
            self.decision_log.record(self.step_count, agent_id, observation, action, final_action)
