"""무작위 맵 생성 명령행 도구.

Usage:
    python -m mapgen --seed 42                       # 생성 후 요약 + 미리보기 출력
    python -m mapgen --seed 42 --puzzles 3 --save    # map_datas/map_42.json으로 저장
    python -m mapgen --load map_datas/map_42.json    # 저장된 맵 미리보기
    python -m mapgen --seed 42 --edit                # 생성한 맵을 pygame 에디터로 열어 수정
    python -m mapgen.editor                          # 빈 맵부터 pygame 에디터로 직접 만들기
"""
import argparse
import os
import random

from .generator import GenConfig, generate_map
from .spec import MapSpec

MAP_DATAS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "map_datas")

# 미리보기 기호 (같은 칸에 여러 개면 나중 것이 덮어씀)
SYMBOLS = {"door": "D", "key": "k", "button": "b", "lever": "l", "pressure_plate": "P",
           "portal": "O", "clue": "?"}
ITEM_SYMBOLS = {"normal": "i", "coop": "C", "trap": "T"}


def render_ascii(spec: MapSpec, cols: int = 60, rows: int = 30) -> str:
    grid = [["." for _ in range(cols)] for _ in range(rows)]

    def cell(x, y):
        return min(rows - 1, int(y / spec.height * rows)), min(cols - 1, int(x / spec.width * cols))

    for wx, wy, ww, wh in spec.walls:
        r0, c0 = cell(wx, wy)
        r1, c1 = cell(wx + ww, wy + wh)
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                grid[r][c] = "#"
    for obj in spec.objects:
        r, c = cell(obj["x"], obj["y"])
        if obj["kind"] == "item":
            grid[r][c] = ITEM_SYMBOLS.get(obj["params"].get("category"), "i")
        else:
            grid[r][c] = SYMBOLS.get(obj["kind"], "o")
    for agent in spec.agents:
        r, c = cell(agent["x"], agent["y"])
        grid[r][c] = agent["id"]

    legend = "# wall  D door  k key  b button  l lever  P plate  O portal  ? clue  i item  C coop  T trap  A,B.. agent"
    return "\n".join("".join(row) for row in grid) + "\n" + legend


def summarize(spec: MapSpec) -> str:
    lines = [f"seed={spec.seed}  size={spec.width}x{spec.height}  walls={len(spec.walls)}  "
             f"agents={len(spec.agents)}  puzzles={spec.puzzles}"]
    lines.append("objectives:")
    lines += [f"  {o}" for o in spec.objectives]
    lines.append("hints:")
    lines += [f"  - {h}" for h in spec.hints]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seed", type=int, default=None, help="생략하면 무작위 6자리 시드")
    parser.add_argument("--load", default=None, help="저장된 맵 JSON을 불러와 미리보기만 함")
    parser.add_argument("--agents", type=int, default=2)
    parser.add_argument("--puzzles", type=int, default=2)
    parser.add_argument("--portals", type=int, default=1, help="양방향 포탈 쌍 개수")
    parser.add_argument("--reveal-positions", action="store_true", help="과제 설명에 대략적인 위치 포함")
    parser.add_argument("--save", action="store_true", help="map_datas/map_<seed>.json으로 저장")
    parser.add_argument("--out", default=None, help="저장 경로 지정 (--save 없이도 저장)")
    parser.add_argument("--edit", action="store_true", help="결과 맵을 pygame 에디터로 열기 (mapgen.editor)")
    args = parser.parse_args()

    if args.load:
        spec = MapSpec.load(args.load)
    else:
        seed = args.seed if args.seed is not None else random.randint(100000, 999999)
        config = GenConfig(n_agents=args.agents, puzzle_count=args.puzzles,
                           portal_pairs=args.portals, reveal_positions=args.reveal_positions)
        spec = generate_map(seed, config)

    print(summarize(spec))
    print()
    print(render_ascii(spec))

    out = args.out or (os.path.join(MAP_DATAS_DIR, f"map_{spec.seed}.json") if args.save else None)
    if out:
        spec.save(out)
        print(f"\nSaved: {out}")

    if args.edit:
        import pygame  # 에디터를 열 때만 pygame을 불러옴
        from .editor import EditorApp
        from .editor_model import EditorModel
        save_path = out or args.load or os.path.join(MAP_DATAS_DIR, f"map_{spec.seed}.json")
        pygame.init()
        EditorApp(EditorModel(spec), save_path).run()


if __name__ == "__main__":
    main()
