import copy
import math

from .generator import _is_reachable
from .hints import auto_hints, mechanisms_for
from .spec import MapSpec

# 맵 에디터의 편집 동작(배치/이동/삭제/연결/목표 지정/검증/저장)만 담당. pygame에 전혀 의존하지
# 않으므로 화면(editor.py) 없이 단독으로 쓰거나 테스트할 수 있고, 다른 UI를 붙일 수도 있음.
# 데이터는 MapSpec 형식 그대로 다룸 (spec.py 참고).

# 도구 이름 -> (오브젝트 kind, id 접두사, 기본 params). trap은 id로 정체가 드러나지 않도록
# 일반 물품과 같은 접두사(item)를 씀
OBJECT_TOOLS = {
    "door": ("door", "door", {"locked": True, "radius": 10.0, "hidden": False}),
    "key": ("key", "key", {"unlocks": None}),
    "button": ("button", "button", {"linked_door_id": None}),
    "lever": ("lever", "lever", {"linked_door_ids": []}),
    "plate": ("pressure_plate", "plate", {"linked_door_id": None, "radius": 12.0}),
    "item": ("item", "item", {"category": "normal"}),
    "coop": ("item", "crate", {"category": "coop", "required_agents": 2}),
    "trap": ("item", "item", {"category": "trap", "seals": None, "disguised": True}),
    "clue": ("clue", "clue", {"content": "", "hidden": True}),
}
LINKABLE = ("key", "button", "lever", "pressure_plate")


def door_objective(door_id: str) -> dict:
    return {"type": "door_unlocked", "door_id": door_id}


def pickup_objective(object_id: str) -> dict:
    return {"type": "item_picked_up", "object_id": object_id}


class EditorModel:
    def __init__(self, spec: MapSpec = None, width: int = 500, height: int = 500) -> None:
        self.spec = copy.deepcopy(spec) if spec is not None else MapSpec(seed=0, width=width, height=height)

    # ---- 조회 ----

    def _used_ids(self) -> set[str]:
        return {o["id"] for o in self.spec.objects} | {a["id"] for a in self.spec.agents}

    def _new_id(self, prefix: str) -> str:
        used = self._used_ids()
        n = 1
        while f"{prefix}_{n}" in used:
            n += 1
        return f"{prefix}_{n}"

    def doors(self) -> list[dict]:
        return [o for o in self.spec.objects if o["kind"] == "door"]

    def _nearest_door(self, x: float, y: float):
        doors = self.doors()
        return min(doors, key=lambda d: math.hypot(d["x"] - x, d["y"] - y)) if doors else None

    def is_goal(self, obj: dict) -> bool:
        return self._objective_for(obj) in self.spec.objectives

    @staticmethod
    def _objective_for(obj: dict):
        if obj["kind"] == "door":
            return door_objective(obj["id"])
        if obj["kind"] == "item" and obj["params"].get("category") != "trap":
            return pickup_objective(obj["id"])
        return None

    # (x, y)에 있는 대상. 오브젝트/에이전트가 벽보다 우선. 반환: ("object"|"agent", dict) 또는 ("wall", index)
    def hit_test(self, x: float, y: float, radius: float = 10.0):
        best, best_d = None, radius
        for obj in self.spec.objects:
            d = math.hypot(obj["x"] - x, obj["y"] - y)
            if d <= best_d:
                best, best_d = ("object", obj), d
        for agent in self.spec.agents:
            d = math.hypot(agent["x"] - x, agent["y"] - y)
            if d <= best_d:
                best, best_d = ("agent", agent), d
        if best is not None:
            return best
        for i in range(len(self.spec.walls) - 1, -1, -1):
            wx, wy, ww, wh = self.spec.walls[i]
            if wx <= x <= wx + ww and wy <= y <= wy + wh:
                return ("wall", i)
        return None

    # ---- 배치 ----

    def _clamp(self, x: float, y: float) -> tuple[float, float]:
        return min(max(x, 0), self.spec.width), min(max(y, 0), self.spec.height)

    # tool: OBJECT_TOOLS의 이름. 열쇠/버튼/레버/압력판은 가장 가까운 문에 자동 연결(L 도구로 변경),
    # 문과 coop 물품은 자동으로 목표(objective)가 됨(G 도구로 해제)
    def add_object(self, tool: str, x: float, y: float) -> dict:
        kind, prefix, params = OBJECT_TOOLS[tool]
        x, y = self._clamp(x, y)
        obj = {"kind": kind, "id": self._new_id(prefix), "x": x, "y": y, "params": copy.deepcopy(params)}
        door = self._nearest_door(x, y)
        if door is not None and kind in LINKABLE:
            self.link(obj, door)
        self.spec.objects.append(obj)
        if kind == "door" or (kind == "item" and params.get("category") == "coop"):
            self.spec.objectives.append(self._objective_for(obj))
        return obj

    # 입구 (x1, y1)과 출구 (x2, y2)를 서로 오가는 양방향 포탈 한 쌍
    def add_portal_pair(self, x1: float, y1: float, x2: float, y2: float) -> tuple[dict, dict]:
        (x1, y1), (x2, y2) = self._clamp(x1, y1), self._clamp(x2, y2)
        a = {"kind": "portal", "id": self._new_id("portal"), "x": x1, "y": y1,
            "params": {"dest_x": x2, "dest_y": y2, "radius": 10.0}}
        self.spec.objects.append(a)
        b = {"kind": "portal", "id": self._new_id("portal"), "x": x2, "y": y2,
            "params": {"dest_x": x1, "dest_y": y1, "radius": 10.0}}
        self.spec.objects.append(b)
        return a, b

    def add_agent(self, x: float, y: float, facing: float = 0.0):
        used = {a["id"] for a in self.spec.agents}
        free = [chr(c) for c in range(ord("A"), ord("Z") + 1) if chr(c) not in used]
        if not free:
            return None
        x, y = self._clamp(x, y)
        agent = {"id": free[0], "x": x, "y": y, "facing": facing}
        self.spec.agents.append(agent)
        self.spec.agents.sort(key=lambda a: a["id"])
        return agent

    # 두 모서리로 벽 추가 (너무 작으면 무시)
    def add_wall(self, x0: float, y0: float, x1: float, y1: float, min_size: float = 4.0):
        (x0, y0), (x1, y1) = self._clamp(x0, y0), self._clamp(x1, y1)
        x, y, w, h = min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0)
        if w < min_size or h < min_size:
            return None
        wall = [x, y, w, h]
        self.spec.walls.append(wall)
        return wall

    # ---- 편집 ----

    def move_to(self, target, x: float, y: float) -> None:
        kind, ref = target
        if kind == "wall":
            wall = self.spec.walls[ref]
            wall[0] = min(max(x, 0), self.spec.width - wall[2])
            wall[1] = min(max(y, 0), self.spec.height - wall[3])
        else:
            ref["x"], ref["y"] = self._clamp(x, y)

    # 삭제하면서 그 대상을 가리키던 연결/목표도 정리
    def delete(self, target) -> None:
        kind, ref = target
        if kind == "wall":
            del self.spec.walls[ref]
            return
        if kind == "agent":
            self.spec.agents.remove(ref)
            return
        self.spec.objects.remove(ref)
        objective = self._objective_for(ref)
        if objective in self.spec.objectives:
            self.spec.objectives.remove(objective)
        if ref["kind"] == "door":
            for obj in self.spec.objects:
                params = obj["params"]
                if params.get("unlocks") == ref["id"]:
                    params["unlocks"] = None
                if params.get("linked_door_id") == ref["id"]:
                    params["linked_door_id"] = None
                if ref["id"] in params.get("linked_door_ids", []):
                    params["linked_door_ids"].remove(ref["id"])

    # source(열쇠/버튼/레버/압력판)를 door에 연결. 레버는 여러 문을 제어하므로 연결/해제를 토글
    def link(self, source: dict, door: dict) -> bool:
        if source["kind"] not in LINKABLE or door["kind"] != "door":
            return False
        params = source["params"]
        if source["kind"] == "key":
            params["unlocks"] = door["id"]
        elif source["kind"] == "lever":
            ids = params.setdefault("linked_door_ids", [])
            if door["id"] in ids:
                ids.remove(door["id"])
            else:
                ids.append(door["id"])
        else:
            params["linked_door_id"] = door["id"]
        return True

    def set_portal_dest(self, portal: dict, x: float, y: float) -> None:
        portal["params"]["dest_x"], portal["params"]["dest_y"] = self._clamp(x, y)

    # 문/일반·coop 물품의 목표 지정을 토글. 반환: 토글 후 목표인지 (대상이 아니면 None)
    def toggle_goal(self, obj: dict):
        objective = self._objective_for(obj)
        if objective is None:
            return None
        if objective in self.spec.objectives:
            self.spec.objectives.remove(objective)
            return False
        self.spec.objectives.append(objective)
        return True

    # 문/단서는 hidden(가까이 가야 보임), trap은 disguised(일반 물품처럼 보임)를 토글
    def toggle_hidden(self, obj: dict):
        params = obj["params"]
        if obj["kind"] in ("door", "clue"):
            params["hidden"] = not params.get("hidden", False)
            return params["hidden"]
        if params.get("category") == "trap":
            params["disguised"] = not params.get("disguised", True)
            return params["disguised"]
        return None

    def rotate_agent(self, agent: dict, delta: float) -> None:
        agent["facing"] = (agent["facing"] + delta) % 360

    def set_clue_text(self, clue: dict, text: str) -> None:
        clue["params"]["content"] = text

    def resize(self, width: int, height: int) -> None:
        self.spec.width, self.spec.height = width, height

    # ---- 검증/저장 ----

    # 저장/실행용 완성본: trap은 맵의 모든 문을 봉인하도록 연결, 과제 설명 자동 생성
    def finalize(self) -> MapSpec:
        spec = copy.deepcopy(self.spec)
        door_ids = [o["id"] for o in spec.objects if o["kind"] == "door"]
        for obj in spec.objects:
            if obj["kind"] == "item" and obj["params"].get("category") == "trap":
                obj["params"]["seals"] = list(door_ids)
        spec.hints = auto_hints(spec)
        spec.puzzles = ["custom"]
        spec.config = {"editor": True}
        return spec

    # 반환: (errors, warnings). errors가 있으면 실행할 수 없는 맵
    def validate(self) -> tuple[list[str], list[str]]:
        errors, warnings = [], []
        spec = self.spec
        n_agents = len(spec.agents)
        if n_agents == 0:
            errors.append("에이전트가 없음 (A 도구로 배치)")
        if not spec.objectives:
            warnings.append("목표가 없음 - 시작하자마자 클리어로 처리되지 않으니 G 도구로 목표를 지정")
        objects = {o["id"]: o for o in spec.objects}
        for objective in spec.objectives:
            if objective["type"] == "door_unlocked":
                mechs = mechanisms_for(spec, objective["door_id"])
                if not mechs:
                    warnings.append(f"{objective['door_id']}: 여는 장치가 연결되지 않음 (L 도구)")
                plates = [m for m in mechs if m["kind"] == "pressure_plate"]
                if len(plates) > n_agents and len(mechs) == len(plates):
                    warnings.append(f"{objective['door_id']}: 압력판 {len(plates)}개를 에이전트 {n_agents}명이 동시에 밟을 수 없음")
            elif objective["type"] == "item_picked_up":
                item = objects.get(objective["object_id"])
                if item and item["params"].get("required_agents", 1) > n_agents and item["params"].get("category") == "coop":
                    warnings.append(f"{item['id']}: coop 물품에 {item['params']['required_agents']}명이 필요한데 에이전트가 {n_agents}명")
        for obj in spec.objects:
            if obj["kind"] in LINKABLE:
                params = obj["params"]
                if not (params.get("unlocks") or params.get("linked_door_id") or params.get("linked_door_ids")):
                    warnings.append(f"{obj['id']}: 어떤 문에도 연결되지 않음")
            if obj["kind"] == "clue" and not obj["params"].get("content"):
                warnings.append(f"{obj['id']}: 단서 내용이 비어 있음 (T 도구)")
        if n_agents and not _is_reachable(spec):
            warnings.append("벽/잠긴 문 때문에 첫 에이전트가 걸어서 갈 수 없는 곳이 있음")
        return errors, warnings

    def save(self, path: str) -> MapSpec:
        spec = self.finalize()
        spec.save(path)
        return spec
