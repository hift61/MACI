import random
from dataclasses import asdict, dataclass, field

from .layout import Layout
from .puzzles import PUZZLES, PuzzleContext
from .spec import MapSpec

# 시드 하나로 무작위 맵(MapSpec)을 만듦. Environment를 import하지 않는 순수 데이터 생성 단계라
# builder.py 없이도 단독으로 쓸 수 있음 (같은 seed + 같은 GenConfig면 항상 같은 맵).


@dataclass
class GenConfig:
    width: int = 500
    height: int = 500
    n_agents: int = 2
    wall_count: tuple = (3, 8)            # 벽 개수 범위 (최소, 최대)
    puzzle_count: int = 2                 # 퍼즐 개수 (첫 퍼즐은 항상 문을 여는 퍼즐)
    allowed_puzzles: list = field(default_factory=lambda: list(PUZZLES))
    require_coop: bool = True             # 협력 퍼즐을 최소 하나 넣을지 (n_agents >= 2일 때만)
    portal_pairs: int = 1                 # 양방향 포탈 쌍 개수
    distractor_items: int = 1             # 목표와 무관한 일반 물품 개수
    reveal_positions: bool = False        # 과제 설명에 오브젝트의 대략적인 위치를 알려줄지


MAX_ATTEMPTS = 50  # 벽 때문에 갈 수 없는 곳이 생기면 같은 rng로 이어서 다시 만드는 최대 횟수


def generate_map(seed: int, config: GenConfig = None) -> MapSpec:
    config = config or GenConfig()
    rng = random.Random(seed)
    for _ in range(MAX_ATTEMPTS):
        spec = _generate_once(seed, rng, config)
        if _is_reachable(spec):
            return spec
    raise RuntimeError(f"seed {seed}: could not generate a fully reachable map in {MAX_ATTEMPTS} attempts")


# 벽이 이동을 막으므로, 첫 에이전트 위치에서 걸어서 모든 에이전트/오브젝트에 다가갈 수 있는지 확인.
# 잠긴 문(처음엔 전부 잠김)도 지나갈 수 없는 장애물로 취급. 문은 가장자리에서 상호작용하므로
# 중심 20 이내, 나머지는 8 이내까지 갈 수 있으면 도달 가능으로 봄
def _is_reachable(spec: MapSpec) -> bool:
    layout = Layout(random.Random(0), spec.width, spec.height)
    layout.walls = spec.walls
    doors = [o for o in spec.objects if o["kind"] == "door"]
    blockers = [(d["x"], d["y"], d["params"].get("radius", 10.0)) for d in doors]
    targets = [(a["x"], a["y"], 8.0) for a in spec.agents]
    targets += [(o["x"], o["y"], 20.0 if o["kind"] == "door" else 8.0) for o in spec.objects]
    start = (spec.agents[0]["x"], spec.agents[0]["y"])
    return layout.all_reachable(start, targets, blockers)


def _generate_once(seed: int, rng: random.Random, config: GenConfig) -> MapSpec:
    layout = Layout(rng, config.width, config.height)
    layout.generate_walls(rng.randint(*config.wall_count))

    agents = []
    for i in range(config.n_agents):
        x, y = layout.free_point()
        agents.append({"id": chr(ord("A") + i), "x": x, "y": y, "facing": float(rng.randrange(0, 360, 45))})

    names = _choose_puzzles(rng, config)
    objects, objectives, hints = [], [], []
    for index, name in enumerate(names, start=1):
        template = PUZZLES[name][0]
        part = template(layout, PuzzleContext(index, config.n_agents, config.reveal_positions))
        objects += part.objects
        objectives += part.objectives
        hints += part.hints

    # 함정은 맵의 모든 문을 봉인하도록 연결 (퍼즐 순서와 무관하게 마지막에 채움)
    door_ids = [o["id"] for o in objects if o["kind"] == "door"]
    for obj in objects:
        if obj["kind"] == "item" and obj["params"].get("category") == "trap":
            obj["params"]["seals"] = list(door_ids)

    for i in range(1, config.portal_pairs + 1):
        a, b = layout.far_pair(min(config.width, config.height) * 0.4)
        objects.append({"kind": "portal", "id": f"portal_{i}a", "x": a[0], "y": a[1],
                        "params": {"dest_x": b[0], "dest_y": b[1], "radius": 10.0}})
        objects.append({"kind": "portal", "id": f"portal_{i}b", "x": b[0], "y": b[1],
                        "params": {"dest_x": a[0], "dest_y": a[1], "radius": 10.0}})
    if config.portal_pairs:
        hints.append("Portals (type 'portal') teleport you to their partner portal when you step onto them.")

    for i in range(1, config.distractor_items + 1):
        x, y = layout.free_point()
        objects.append({"kind": "item", "id": f"item_{i}", "x": x, "y": y, "params": {"category": "normal"}})

    config_record = asdict(config)
    config_record["wall_count"] = list(config.wall_count)
    return MapSpec(
        seed=seed,
        width=config.width,
        height=config.height,
        walls=layout.walls,
        agents=agents,
        objects=objects,
        objectives=objectives,
        puzzles=names,
        hints=hints,
        config=config_record
    )


# 첫 퍼즐은 문을 여는 퍼즐(trap이 봉인할 문이 반드시 있도록), require_coop이면 협력 퍼즐을
# 최소 하나 포함, 에이전트가 1명이면 협력 퍼즐 제외. 나머지는 허용 목록에서 무작위
def _choose_puzzles(rng: random.Random, config: GenConfig) -> list[str]:
    allowed = [n for n in config.allowed_puzzles if config.n_agents >= 2 or not PUZZLES[n][2]]
    door_puzzles = [n for n in allowed if PUZZLES[n][1]]
    coop_puzzles = [n for n in allowed if PUZZLES[n][2]]
    if not door_puzzles:
        raise ValueError("allowed_puzzles must include at least one door puzzle")

    names = [rng.choice(door_puzzles)]
    if config.require_coop and coop_puzzles and not PUZZLES[names[0]][2] and config.puzzle_count >= 2:
        names.append(rng.choice(coop_puzzles))
    while len(names) < config.puzzle_count:
        names.append(rng.choice(allowed))
    rng.shuffle(names)
    return names
