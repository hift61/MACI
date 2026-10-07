import random
import math

from enviroment import Environment

# 두 방 순서 퍼즐 환경.
# 가운데 벽으로 완전히 나뉜 두 방에 에이전트가 한 명씩 갇혀 있고, 방마다 숫자가 적힌 번호판
# (number_pad)이 여러 개 있음. 전체 정답은 "두 방을 오가는 하나의 입력 순서"인데, 각 에이전트는
# 자기 방 안내판(clue)에서 "자기가 몇 번째 순서에 어떤 숫자를 눌러야 하는지"만 볼 수 있음
# (방마다 숫자가 서로 다르고, 상대 방 번호판/안내판은 벽에 가려 보이지 않음).
# 그래서 "내가 3번째를 눌렀으니 이제 네 차례" 같은 메시지로 순서를 맞춰야만 풀 수 있음.
#   - 순서에 맞는 입력: number_accepted 이벤트, 진행도 +1
#   - 틀린 입력(엉뚱한 숫자/자기 차례가 아닌데 누름): sequence_reset 이벤트, 두 방 모두 처음부터 다시
#   - 전부 맞게 누르면 vault 문이 열림(door_unlocked) - 클리어 조건
#   - max_turns step 안에 못 풀면 vault가 영구 봉인되고 env.failure에 기록 (실행 턴 제한)
# 번호판 접촉 범위에 진입하면 자동 입력. 머물러 있는 동안에는 다시 입력하지 않음.

ROOM_IDS = ("A", "B")


class RoomsMap:
    # Environment가 쓰는 맵 정보만 가진 최소 맵 객체 (mapgen.builder.GeneratedMap과 같은 역할)
    class _Wall:
        def __init__(self, x, y, width, height) -> None:
            self.x, self.y, self.width, self.height = x, y, width, height

    def __init__(self, width: float, height: float, walls: list[tuple]) -> None:
        self.map_width = width
        self.map_height = height
        self.walls = [self._Wall(*wall) for wall in walls]


class SequenceRoomsEnvironment(Environment):
    def __init__(self, game_map, max_turns: int = 60, max_resets: int | None = None,
                 vault_id: str = "vault", **kwargs) -> None:
        super().__init__(game_map, **kwargs)
        self.max_turns = max_turns    # 이 step 수 안에 못 풀면 실패 (None이면 제한 없음)
        self.max_resets = max_resets  # 틀린 입력이 이 횟수를 넘으면 실패 (None이면 제한 없음)
        self.vault_id = vault_id      # 순서를 다 맞추면 열리는 문 (클리어 조건)
        self.sequence: list[str] = []  # 전체 정답 순서 (pad_id 목록)
        self.progress = 0              # 지금까지 맞게 누른 개수
        self.resets = 0
        self.solved = False
        self._contributors: list[str] = []  # 이번 시도에서 맞게 누른 에이전트 (문 열림 공로자)
        self._pads_inside: dict[str, set[str]] = {}

    # number: 번호판에 적힌 숫자, room: 이 번호판이 있는 방 id
    def add_number_pad(self, pad_id: str, x: float, y: float, number: int, room: str) -> None:
        self.objects[pad_id] = {
            "object_id": pad_id,
            "x": x,
            "y": y,
            "type": "number_pad",
            "number": number,
            "room": room,
            "touch_radius": 10.0
        }

    # 각 방의 안내판(display)은 그 방 번호판의 마지막 입력 결과와 전체 리셋 횟수만 보여줌.
    # 전체 진행도는 보여주지 않음 - 상대가 눌렀는지는 메시지로만 알 수 있게 하기 위함
    def add_display(self, display_id: str, x: float, y: float, room: str) -> None:
        self.objects[display_id] = {
            "object_id": display_id,
            "x": x,
            "y": y,
            "type": "display",
            "room": room,
            "last_press": None,
            "resets": 0
        }

    def set_sequence(self, pad_ids: list[str]) -> None:
        for pad_id in pad_ids:
            if self.objects.get(pad_id, {}).get("type") != "number_pad":
                raise ValueError(f"not a number pad: {pad_id!r}")
        self.sequence = list(pad_ids)

    @property
    def finished(self) -> bool:
        return self.solved or self.failure is not None

    # Detect contact after the rule-filtered action; number pads need no press action.
    def apply_action(self, agent_id: str, action: dict, observation: dict = None) -> dict:
        agent = self.agents[agent_id]
        start = (agent.x, agent.y)
        final_action = super().apply_action(agent_id, action, observation)
        self._check_pad_contacts(agent_id, start)
        return final_action

    def _check_pad_contacts(self, agent_id, start):
        agent = self.agents[agent_id]
        dx, dy = agent.x - start[0], agent.y - start[1]
        length2 = dx * dx + dy * dy
        previous = self._pads_inside.get(agent_id, set())
        inside, entered = set(), []
        for pad_id, pad in self.objects.items():
            if pad['type'] != 'number_pad':
                continue
            radius = pad['touch_radius']
            if math.hypot(agent.x-pad['x'], agent.y-pad['y']) <= radius:
                inside.add(pad_id)
            if pad_id in previous:
                continue
            ox, oy = start[0]-pad['x'], start[1]-pad['y']
            c = ox*ox + oy*oy - radius*radius
            entry = 0.0 if c <= 0 else None
            if entry is None and length2:
                b = 2 * (ox*dx + oy*dy)
                discriminant = b*b - 4*length2*c
                if discriminant >= 0:
                    t = (-b-math.sqrt(discriminant))/(2*length2)
                    if 0 <= t <= 1:
                        entry = t
            if entry is not None:
                entered.append((entry, pad_id))
        self._pads_inside[agent_id] = inside
        for _, pad_id in sorted(entered):
            if self.finished:
                break
            self.press_number_pad(agent_id, pad_id, contact=True)

    def press_number_pad(self, agent_id: str, pad_id: str, contact: bool = False) -> None:
        agent = self.agents[agent_id]
        pad = self.objects[pad_id]
        if self.finished or not self.sequence:
            return
        if not contact and (agent.x - pad["x"]) ** 2 + (agent.y - pad["y"]) ** 2 > self.interact_radius ** 2:
            return

        correct = self.sequence[self.progress] == pad_id
        self._show(pad["room"], {"pad_id": pad_id, "number": pad["number"], "step": self.step_count,
                                 "result": "accepted" if correct else "wrong_reset"})
        if not correct:
            self._log("sequence_reset", [agent_id], object_id=pad_id, number=pad["number"],
                      expected_order=self.progress + 1)
            self.progress = 0
            self.resets += 1
            self._contributors = []
            for display in self._displays():
                display["resets"] = self.resets
            if self.max_resets is not None and self.resets > self.max_resets:
                self._fail("too_many_resets", agent_id)
            return

        self.progress += 1
        if agent_id not in self._contributors:
            self._contributors.append(agent_id)
        self._log("number_accepted", [agent_id], object_id=pad_id, number=pad["number"], order=self.progress)
        if self.progress == len(self.sequence):
            self.solved = True
            self._log("sequence_completed", list(self._contributors))
            door = self.objects.get(self.vault_id)
            if door is not None:
                self._set_door_locked(door, False, "number_sequence", list(self._contributors), list(self.sequence))

    def _displays(self) -> list[dict]:
        return [obj for obj in self.objects.values() if obj["type"] == "display"]

    def _show(self, room: str, last_press: dict) -> None:
        for display in self._displays():
            if display["room"] == room:
                display["last_press"] = last_press

    # 실패 확정: vault를 영구 봉인하고 env.failure에 원인을 남김 (trap 실패와 같은 형식이라
    # sealed_doors를 보고 조기 종료하는 benchmark 루프가 그대로 동작)
    def _fail(self, reason: str, agent_id: str | None) -> None:
        door = self.objects.get(self.vault_id)
        if door is not None:
            self._set_door_locked(door, True, reason, [agent_id] if agent_id else [], reason)
            door["sealed"] = True
        self._log("sequence_failed", [agent_id] if agent_id else [], reason=reason, progress=self.progress)
        self.failure = {
            "step": self.step_count,
            "agent_id": agent_id,
            "object_id": reason,
            "reason": reason,
            "sealed_doors": [self.vault_id]
        }

    # 끝난 뒤에는 더 진행하지 않음. max_turns번째 step까지 못 풀면 그 step에서 실패 확정
    def step(self) -> None:
        if self.finished:
            return
        super().step()
        if not self.finished and self.max_turns is not None and self.step_count >= self.max_turns:
            self._fail("turn_limit", None)


# 시드로 두 방 순서 퍼즐을 만듦. 반환: (env, 에이전트별 과제 설명, objectives) -
# mapgen.builder.build_environment와 같은 형식이라 benchmark 쪽에서 그대로 바꿔 끼울 수 있음
#   pads_per_room: 방마다 번호판 개수 (정답에 안 쓰이는 미끼 번호 포함)
#   presses_per_room: 방마다 눌러야 하는 횟수 (전체 순서 길이 = 이 값 x 2)
def build_sequence_rooms(seed: int = 0, pads_per_room: int = 5, presses_per_room: int = 3,
                         max_turns: int = 60, max_resets: int | None = None,
                         interact_radius: float = 15.0):
    if not 1 <= presses_per_room <= pads_per_room <= 5:
        raise ValueError("need 1 <= presses_per_room <= pads_per_room <= 5")
    rng = random.Random(seed)
    width, height, wall_x, wall_w = 400, 240, 195, 10
    env = SequenceRoomsEnvironment(
        RoomsMap(width, height, [(wall_x, 0, wall_w, height)]),
        max_turns=max_turns, max_resets=max_resets, interact_radius=interact_radius
    )

    # 두 방이 같은 숫자를 쓰지 않도록 0~9를 나눠 가짐 ("번호가 서로 다름")
    digits = rng.sample(range(10), pads_per_room * 2)
    room_left = {"A": 0.0, "B": wall_x + wall_w}
    room_width = wall_x
    slots = {}  # room -> 이 방에서 순서대로 눌러야 하는 pad_id
    for index, room in enumerate(ROOM_IDS):
        left = room_left[room]
        numbers = digits[index * pads_per_room:(index + 1) * pads_per_room]
        pad_ids = []
        for i, number in enumerate(numbers):
            x = left + 40 + (room_width - 80) * i / max(1, pads_per_room - 1)
            pad_id = f"pad_{room}{number}"
            env.add_number_pad(pad_id, x, 70, number, room)
            pad_ids.append(pad_id)
        slots[room] = rng.sample(pad_ids, presses_per_room)
        center = left + room_width / 2
        env.add_display(f"display_{room}", center - 20, 115, room)
        env.add_agent(room, x=center, y=150, facing=270)

    # 두 방의 입력을 무작위로 섞은 전체 순서 (각 방 안에서의 순서는 유지)
    order = [room for room in ROOM_IDS for _ in range(presses_per_room)]
    rng.shuffle(order)
    remaining = {room: list(slots[room]) for room in ROOM_IDS}
    sequence = [remaining[room].pop(0) for room in order]
    env.set_sequence(sequence)

    for room in ROOM_IDS:
        mine = [{"order": i + 1, "number": env.objects[pad_id]["number"]}
                for i, pad_id in enumerate(sequence) if env.objects[pad_id]["room"] == room]
        content = {"total_presses": len(sequence), "your_presses": mine}
        center = room_left[room] + room_width / 2
        env.add_clue(f"clue_{room}", center + 20, 115, content, hidden=False)

    env.add_door(env.vault_id, x=wall_x + wall_w / 2, y=height - 15, locked=True, radius=10.0)

    objectives = [{"type": "door_unlocked", "door_id": env.vault_id}]
    return env, sequence_task_descriptions(env), objectives


def sequence_task_descriptions(env: SequenceRoomsEnvironment) -> dict[str, str]:
    total = len(env.sequence)
    limit = f"within {env.max_turns} steps" if env.max_turns is not None else "as fast as you can"
    descriptions = {}
    for room in ROOM_IDS:
        other = next(r for r in ROOM_IDS if r != room)
        descriptions[room] = (
            f"You are agent {room}, locked in room {room} (the left room is A, the right room is B; a wall "
            f"separates them and you cannot see or enter the other room). Agent {other} is in room {other}. "
            f"Both rooms have number pads (objects of type 'number_pad' with a 'number' field). The team must "
            f"press {total} pads in ONE shared order that alternates between the two rooms irregularly. The "
            f"clue 'clue_{room}' in your room (field 'content') lists only YOUR presses: which overall order "
            f"positions are yours and which number to press at each. {other}'s clue lists theirs, with "
            f"different numbers. Numbers and the shared order are randomized by the seed and stay fixed "
            f"throughout this episode, including after resets. Entering a pad's touch_radius (10 units) "
            f"AUTOMATICALLY presses it; press_button is unnecessary. Staying on it does not repeat the input; "
            f"leave and re-enter to press again. Crossing a pad while moving also presses it, so travel below "
            f"the pad row before approaching your target vertically to avoid other pads. "
            f"Only touch your target when every earlier position has been pressed - "
            f"use send_message to tell {other} each time you press (e.g. 'pressed order 3') and wait for "
            f"their message before pressing after their turn. Any wrong or early press resets the WHOLE "
            f"sequence for both rooms; 'display_{room}' shows your room's last press result and the reset "
            f"count. Pressing all {total} correctly unlocks door '{env.vault_id}'. You must finish {limit} "
            f"or the door is sealed forever."
        )
    return descriptions
