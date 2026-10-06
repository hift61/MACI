from dataclasses import dataclass, field

from .layout import Layout

# 퍼즐 템플릿 모음. 각 템플릿은 (layout, ctx)를 받아 PuzzlePart(배치할 오브젝트, 클리어 조건,
# 과제 설명 문장)를 돌려주는 함수이고, PUZZLES에 이름으로 등록됨. 새 퍼즐은 함수를 하나
# 만들어 PUZZLES에 추가하기만 하면 generator.py가 자동으로 고를 수 있음.
#
# 오브젝트 형식은 spec.py 참고 ({"kind", "id", "x", "y", "params"})


@dataclass
class PuzzleContext:
    index: int              # 이 맵에서 몇 번째 퍼즐인지 (오브젝트 id 중복 방지용 접미사)
    n_agents: int
    reveal_positions: bool  # 과제 설명에 대략적인 위치를 알려줄지


@dataclass
class PuzzlePart:
    objects: list = field(default_factory=list)
    objectives: list = field(default_factory=list)
    hints: list = field(default_factory=list)


def _obj(kind: str, obj_id: str, point, **params) -> dict:
    return {"kind": kind, "id": obj_id, "x": point[0], "y": point[1], "params": params}


def _where(ctx: PuzzleContext, point) -> str:
    return f" (around ({point[0]:.0f}, {point[1]:.0f}))" if ctx.reveal_positions else ""


def _door_objective(door_id: str) -> dict:
    return {"type": "door_unlocked", "door_id": door_id}


def _pickup_objective(object_id: str) -> dict:
    return {"type": "item_picked_up", "object_id": object_id}


# ---- 혼자서도 풀 수 있는 퍼즐 ----

def key_door(layout: Layout, ctx: PuzzleContext) -> PuzzlePart:
    door_id, key_id = f"door_{ctx.index}", f"key_{ctx.index}"
    door, key = layout.free_point(), layout.free_point()
    return PuzzlePart(
        objects=[_obj("door", door_id, door, locked=True, radius=10.0),
                 _obj("key", key_id, key, unlocks=door_id)],
        objectives=[_door_objective(door_id)],
        hints=[f"Unlock '{door_id}'{_where(ctx, door)}: find key '{key_id}'{_where(ctx, key)}, pick it up, "
               f"and use it next to the door."]
    )


def lever_door(layout: Layout, ctx: PuzzleContext) -> PuzzlePart:
    door_id, lever_id = f"door_{ctx.index}", f"lever_{ctx.index}"
    door, lever = layout.free_point(), layout.free_point()
    return PuzzlePart(
        objects=[_obj("door", door_id, door, locked=True, radius=10.0),
                 _obj("lever", lever_id, lever, linked_door_ids=[door_id])],
        objectives=[_door_objective(door_id)],
        hints=[f"Unlock '{door_id}'{_where(ctx, door)}: pull lever '{lever_id}'{_where(ctx, lever)} "
               f"(pulling it again closes the door)."]
    )


def button_door(layout: Layout, ctx: PuzzleContext) -> PuzzlePart:
    door_id, button_id = f"door_{ctx.index}", f"button_{ctx.index}"
    door, button = layout.free_point(), layout.free_point()
    return PuzzlePart(
        objects=[_obj("door", door_id, door, locked=True, radius=10.0),
                 _obj("button", button_id, button, linked_door_id=door_id)],
        objectives=[_door_objective(door_id)],
        hints=[f"Unlock '{door_id}'{_where(ctx, door)}: press button '{button_id}'{_where(ctx, button)} "
               f"(it toggles the door)."]
    )


# ---- 협력이 필요한 퍼즐 (n_agents >= 2) ----

def dual_plate_door(layout: Layout, ctx: PuzzleContext) -> PuzzlePart:
    door_id = f"door_{ctx.index}"
    plate_a, plate_b = f"plate_{ctx.index}a", f"plate_{ctx.index}b"
    door = layout.free_point()
    pa, pb = layout.far_pair(min(layout.width, layout.height) * 0.5)
    return PuzzlePart(
        objects=[_obj("door", door_id, door, locked=True, radius=10.0),
                 _obj("pressure_plate", plate_a, pa, linked_door_id=door_id, radius=12.0),
                 _obj("pressure_plate", plate_b, pb, linked_door_id=door_id, radius=12.0)],
        objectives=[_door_objective(door_id)],
        hints=[f"Unlock '{door_id}'{_where(ctx, door)}: two agents must stand on pressure plates "
               f"'{plate_a}'{_where(ctx, pa)} and '{plate_b}'{_where(ctx, pb)} AT THE SAME TIME."]
    )


def coop_item(layout: Layout, ctx: PuzzleContext) -> PuzzlePart:
    item_id = f"crate_{ctx.index}"
    point = layout.free_point()
    required = min(2, ctx.n_agents)
    return PuzzlePart(
        objects=[_obj("item", item_id, point, category="coop", required_agents=required)],
        objectives=[_pickup_objective(item_id)],
        hints=[f"Pick up the heavy crate '{item_id}'{_where(ctx, point)}: it needs {required} agents "
               f"standing next to it together, and the carrier cannot move unless a helper stays close."]
    )


# ---- 정보 공유가 필요한 함정 퍼즐 ----
# 똑같이 보이는 유물 두 개 중 하나는 진짜(목표), 하나는 위장된 trap. 숨겨진 단서(clue)를
# 가까이 가서 읽은 에이전트만 어느 쪽이 진짜인지 알 수 있음. trap의 seals는 generator가
# 맵의 모든 문으로 채움 (잘못 집으면 모든 문이 영구 봉인되어 클리어 불가)

def clue_trap(layout: Layout, ctx: PuzzleContext) -> PuzzlePart:
    ids = [f"relic_{ctx.index}a", f"relic_{ctx.index}b"]
    layout.rng.shuffle(ids)
    real_id, trap_id = ids
    real, trap, clue = layout.free_point(), layout.free_point(), layout.free_point()
    clue_id = f"clue_{ctx.index}"
    return PuzzlePart(
        objects=[_obj("item", real_id, real, category="normal"),
                 _obj("item", trap_id, trap, category="trap", seals=None, disguised=True),
                 _obj("clue", clue_id, clue, hidden=True,
                      content=f"The real relic is '{real_id}'. Picking up '{trap_id}' seals every door forever.")],
        objectives=[_pickup_objective(real_id)],
        hints=[f"Two identical-looking relics exist; one is a trap that permanently seals every door. "
               f"A hidden note '{clue_id}'{_where(ctx, clue)} (visible only up close) says which one is real. "
               f"Pick up only the real relic."]
    )


# 이름 -> (템플릿 함수, 문을 여는 퍼즐인지, 협력이 필요한지)
PUZZLES = {
    "key_door": (key_door, True, False),
    "lever_door": (lever_door, True, False),
    "button_door": (button_door, True, False),
    "dual_plate_door": (dual_plate_door, True, True),
    "coop_item": (coop_item, False, True),
    "clue_trap": (clue_trap, False, False),
}
