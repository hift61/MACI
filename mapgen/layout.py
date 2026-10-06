import math
import random

# 맵의 공간 배치 담당: 벽 생성과, 벽/다른 오브젝트와 겹치지 않는 빈 좌표 뽑기.
# 좌표는 Environment와 같은 맵 좌표(0~width, 0~height)를 씀 (world_core의 화면 여백 25 없음).


class Layout:
    def __init__(
        self,
        rng: random.Random,
        width: int,
        height: int,
        margin: float = 20.0,
        min_gap: float = 30.0,
        wall_clearance: float = 8.0
    ) -> None:
        self.rng = rng
        self.width = width
        self.height = height
        self.margin = margin                  # 맵 가장자리에서 띄울 거리
        self.min_gap = min_gap                # 오브젝트/스폰끼리 최소 간격
        self.wall_clearance = wall_clearance  # 벽에서 띄울 거리
        self.walls: list[list[float]] = []
        self.points: list[tuple[float, float]] = []  # 이미 사용한 좌표

    # world_core._make_random_wall과 같은 크기 규칙(가로/세로 막대)으로 서로 겹치지 않는 벽 생성
    def generate_walls(self, count: int) -> None:
        tries = 0
        while len(self.walls) < count and tries < count * 20:
            tries += 1
            if self.rng.random() < 0.5:
                w, h = self.rng.randint(80, 200), self.rng.randint(10, 25)
            else:
                w, h = self.rng.randint(10, 25), self.rng.randint(80, 200)
            w, h = min(w, self.width - 1), min(h, self.height - 1)
            x = self.rng.randint(0, self.width - w)
            y = self.rng.randint(0, self.height - h)
            if any(self._rects_overlap((x, y, w, h), wall) for wall in self.walls):
                continue
            self.walls.append([x, y, w, h])

    @staticmethod
    def _rects_overlap(a, b) -> bool:
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah

    def _in_wall(self, x: float, y: float) -> bool:
        c = self.wall_clearance
        return any(wx - c <= x <= wx + ww + c and wy - c <= y <= wy + wh + c for wx, wy, ww, wh in self.walls)

    def _free(self, x: float, y: float, gap: float) -> bool:
        return not self._in_wall(x, y) and all(math.hypot(x - px, y - py) >= gap for px, py in self.points)

    # 벽 밖이면서 기존 좌표들과 min_gap 이상 떨어진 좌표를 뽑아 사용 처리. 자리가 없으면
    # 간격 조건을 점점 완화해서라도 반환 (벽 안에는 절대 두지 않음)
    def free_point(self) -> tuple[float, float]:
        gap = self.min_gap
        while True:
            for _ in range(300):
                x = round(self.rng.uniform(self.margin, self.width - self.margin), 1)
                y = round(self.rng.uniform(self.margin, self.height - self.margin), 1)
                if self._free(x, y, gap):
                    self.points.append((x, y))
                    return x, y
            gap /= 2
            if gap < 1:
                gap = 0

    # 서로 min_distance 이상 떨어진 빈 좌표 두 개 (압력판 쌍, 포탈 쌍 등). 조건을 못 맞추면
    # 시도 중 가장 멀었던 쌍을 사용
    def far_pair(self, min_distance: float) -> tuple[tuple[float, float], tuple[float, float]]:
        best = None
        for _ in range(50):
            a = self.free_point()
            b = self.free_point()
            distance = math.hypot(a[0] - b[0], a[1] - b[1])
            if distance >= min_distance:
                if best is not None:
                    self._release(*best[1:])
                return a, b
            if best is None or distance > best[0]:
                if best is not None:
                    self._release(*best[1:])
                best = (distance, a, b)
            else:
                self._release(a, b)
        return best[1], best[2]

    def _release(self, *points) -> None:
        for p in points:
            self.points.remove(p)

    # 벽(이동을 막음)과 blockers(잠긴 문 등 원 (x, y, radius))를 피해 start에서 걸어서 갈 수 있는지
    # 격자(cell 단위) 너비 우선 탐색으로 판정. targets의 각 (x, y, reach)마다 reach 거리 안에 도달
    # 가능한 칸이 하나라도 있어야 True. 포탈로 이어지는 길은 고려하지 않음(보수적 판정)
    def all_reachable(self, start, targets, blockers=(), cell: float = 5.0) -> bool:
        cols, rows = int(self.width // cell) + 1, int(self.height // cell) + 1

        def center(c, r):
            return min(c * cell, self.width), min(r * cell, self.height)

        def blocked(c, r):
            x, y = center(c, r)
            if any(wx - 1 <= x <= wx + ww + 1 and wy - 1 <= y <= wy + wh + 1 for wx, wy, ww, wh in self.walls):
                return True
            return any(math.hypot(x - bx, y - by) <= br + 1 for bx, by, br in blockers)

        start_cell = (min(cols - 1, round(start[0] / cell)), min(rows - 1, round(start[1] / cell)))
        seen = {start_cell}
        queue = [start_cell]
        while queue:
            c, r = queue.pop()
            for nc, nr in ((c + 1, r), (c - 1, r), (c, r + 1), (c, r - 1)):
                if 0 <= nc < cols and 0 <= nr < rows and (nc, nr) not in seen and not blocked(nc, nr):
                    seen.add((nc, nr))
                    queue.append((nc, nr))

        for tx, ty, reach in targets:
            if not any(math.hypot(center(c, r)[0] - tx, center(c, r)[1] - ty) <= reach for c, r in seen):
                return False
        return True
