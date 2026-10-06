"""MACI 맵 에디터 (pygame). 마우스로 벽/오브젝트/에이전트를 배치하고, 연결/목표를 정하고,
직접 조작해 테스트 플레이한 뒤 MapSpec JSON으로 저장 (benchmark.py --map-file로 바로 사용).

Usage:
    python -m mapgen.editor                                  # 빈 500x500 맵
    python -m mapgen.editor --width 600 --height 400
    python -m mapgen.editor --load map_datas/map_42.json      # 저장된 맵 편집
    python -m mapgen.editor --seed 42                         # 무작위 생성 맵에서 시작
    python -m mapgen --seed 42 --edit                         # (같음)

편집 동작은 editor_model.EditorModel이 하고, 이 파일은 화면/입력만 담당.
"""
import argparse
import datetime
import math
import os
import sys

import pygame

from .editor_model import LINKABLE, EditorModel
from .spec import MapSpec

MAP_DATAS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "map_datas")

MAP_VIEW = 720       # 맵 영역 최대 크기 (픽셀)
PAD = 20             # 맵 영역 바깥 여백
SIDEBAR_W = 360
SNAP = 5             # 좌표 격자 스냅 단위 (맵 좌표)
VIEW_RADIUS, VIEW_ANGLE = 100.0, 90.0   # 미리보기용 시야 (Environment.add_agent 기본값)

COLORS = {
    "bg": (24, 26, 31), "map": (36, 39, 46), "grid": (46, 50, 58), "wall": (150, 155, 165),
    "text": (225, 228, 235), "dim": (140, 145, 155), "warn": (240, 190, 80), "err": (240, 90, 90),
    "ok": (110, 210, 130), "goal": (255, 215, 0), "select": (255, 255, 255),
    "door": (190, 120, 60), "door_open": (110, 180, 110), "key": (240, 220, 80), "button": (80, 200, 230),
    "lever": (240, 150, 60), "pressure_plate": (110, 200, 110), "item": (200, 200, 210), "coop": (90, 140, 240),
    "trap": (230, 70, 70), "portal": (180, 110, 230), "clue": (230, 230, 120), "agent": (255, 120, 170),
    "cone": (70, 60, 80),
}

# 키 -> 도구. 오브젝트 도구 이름은 editor_model.OBJECT_TOOLS와 같음
TOOL_KEYS = {
    pygame.K_1: "wall", pygame.K_2: "door", pygame.K_3: "key", pygame.K_4: "button", pygame.K_5: "lever",
    pygame.K_6: "plate", pygame.K_7: "item", pygame.K_8: "coop", pygame.K_9: "trap", pygame.K_0: "portal",
    pygame.K_c: "clue", pygame.K_a: "agent", pygame.K_v: "select", pygame.K_l: "link", pygame.K_g: "goal",
    pygame.K_h: "hidden", pygame.K_t: "text",
}
TOOL_HELP = [
    ("V", "select", "선택/드래그로 이동"), ("1", "wall", "벽 (드래그)"), ("2", "door", "문"),
    ("3", "key", "열쇠"), ("4", "button", "버튼"), ("5", "lever", "레버"), ("6", "plate", "압력판"),
    ("7", "item", "일반 물품"), ("8", "coop", "협동 물품"), ("9", "trap", "함정 물품"),
    ("0", "portal", "포탈 (입구→출구 2번 클릭)"), ("C", "clue", "단서 (내용 입력)"), ("A", "agent", "에이전트"),
    ("L", "link", "연결: 장치→문 / 포탈→목적지"), ("G", "goal", "목표 지정/해제"),
    ("H", "hidden", "숨김(문/단서), 위장(함정)"), ("T", "text", "단서 내용 수정"),
]


class ManualPolicy:
    """테스트 플레이에서 키보드로 고른 행동을 한 번만 내보내는 정책"""
    def __init__(self) -> None:
        self.next_action = None

    def decide(self, observation: dict) -> dict:
        action, self.next_action = self.next_action or {"type": "noop"}, None
        return action


class EditorApp:
    def __init__(self, model: EditorModel, save_path: str) -> None:
        self.model = model
        self.save_path = save_path
        self.tool = "select"
        self.pending = None        # 링크 출발점 / 포탈 입구 / 벽 드래그 시작점
        self.drag = None           # (대상, 오프셋x, 오프셋y)
        self.typing = None         # 내용을 입력 중인 단서 오브젝트
        self.text_buffer = ""
        self.hover = (0.0, 0.0)    # 마우스 위치 (맵 좌표)
        self.message, self.message_color = "", COLORS["text"]
        self.validation = ([], [])
        self.dirty = True          # 검증 결과를 다시 계산해야 하는지
        self.play = None           # 테스트 플레이 상태 (None이면 편집 모드)
        self._layout()
        self.screen = pygame.display.set_mode((self.map_px_w + PAD * 2 + SIDEBAR_W, max(self.map_px_h + PAD * 2, 760)))
        pygame.display.set_caption("MACI Map Editor")
        self.font = self._font(15)
        self.small = self._font(12)

    @staticmethod
    def _font(size):
        for name in ("malgungothic", "applegothic", "nanumgothic", None):
            try:
                return pygame.font.SysFont(name, size) if name else pygame.font.Font(None, size + 4)
            except Exception:
                continue

    def _layout(self) -> None:
        spec = self.model.spec
        self.scale = min(MAP_VIEW / spec.width, MAP_VIEW / spec.height)
        self.map_px_w, self.map_px_h = int(spec.width * self.scale), int(spec.height * self.scale)

    # ---- 좌표 변환 ----

    def to_screen(self, x, y):
        return int(PAD + x * self.scale), int(PAD + y * self.scale)

    def to_map(self, px, py, snap=True):
        x, y = (px - PAD) / self.scale, (py - PAD) / self.scale
        if snap:
            x, y = round(x / SNAP) * SNAP, round(y / SNAP) * SNAP
        return x, y

    def in_map(self, px, py) -> bool:
        return PAD <= px <= PAD + self.map_px_w and PAD <= py <= PAD + self.map_px_h

    def say(self, text, color=None) -> None:
        self.message, self.message_color = text, color or COLORS["text"]

    # ---- 메인 루프 ----

    def run(self) -> None:
        clock = pygame.time.Clock()
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                else:
                    self.handle(event)
            self.draw()
            pygame.display.flip()
            clock.tick(60)
        pygame.quit()

    def handle(self, event) -> None:
        if self.typing is not None:
            self._handle_typing(event)
        elif self.play is not None:
            self._handle_play(event)
        else:
            self._handle_edit(event)

    # ---- 편집 입력 ----

    def _handle_edit(self, event) -> None:
        if event.type == pygame.KEYDOWN:
            ctrl = event.mod & pygame.KMOD_CTRL
            if ctrl and event.key == pygame.K_s:
                self.save()
            elif event.key == pygame.K_p:
                self.start_play()
            elif event.key == pygame.K_ESCAPE:
                self.pending, self.tool = None, "select"
            elif event.key in TOOL_KEYS and not ctrl:
                self.tool, self.pending = TOOL_KEYS[event.key], None
                self.say(f"도구: {self.tool}")
            return

        if event.type == pygame.MOUSEMOTION:
            self.hover = self.to_map(*event.pos)
            if self.drag is not None:
                target, ox, oy = self.drag
                x, y = self.to_map(*event.pos)
                self.model.move_to(target, x - ox, y - oy)
                self.dirty = True
            return

        if event.type == pygame.MOUSEWHEEL:
            target = self.model.hit_test(*self.hover, radius=12 / self.scale + 6)
            if target and target[0] == "agent":
                self.model.rotate_agent(target[1], -45 if event.y > 0 else 45)
            return

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self.tool == "wall" and self.pending is not None:
                x, y = self.to_map(*event.pos)
                if self.model.add_wall(*self.pending, x, y):
                    self.dirty = True
                self.pending = None
            self.drag = None
            return

        if event.type != pygame.MOUSEBUTTONDOWN or not self.in_map(*event.pos) or event.button not in (1, 3):
            return
        x, y = self.to_map(*event.pos)
        raw_x, raw_y = self.to_map(*event.pos, snap=False)
        target = self.model.hit_test(raw_x, raw_y, radius=12 / self.scale + 6)

        if event.button == 3:  # 우클릭: 진행 중인 작업 취소, 없으면 삭제
            if self.pending is not None:
                self.pending = None
            elif target is not None:
                self.model.delete(target)
                self.dirty = True
            return

        tool = self.tool
        if tool == "select":
            if target is not None:
                if target[0] == "wall":
                    wall = self.model.spec.walls[target[1]]
                    self.drag = (target, x - wall[0], y - wall[1])
                else:
                    self.drag = (target, x - target[1]["x"], y - target[1]["y"])
        elif tool == "wall":
            self.pending = (x, y)
        elif tool == "agent":
            if self.model.add_agent(x, y) is None:
                self.say("에이전트는 최대 26명", COLORS["err"])
        elif tool == "portal":
            if self.pending is None:
                self.pending = (x, y)
                self.say("포탈 출구 위치를 클릭")
            else:
                self.model.add_portal_pair(*self.pending, x, y)
                self.pending = None
        elif tool == "link":
            self._click_link(target, x, y)
        elif tool == "goal":
            if target and target[0] == "object":
                result = self.model.toggle_goal(target[1])
                self.say({True: "목표로 지정", False: "목표 해제", None: "문/물품만 목표가 될 수 있음"}[result])
        elif tool == "hidden":
            if target and target[0] == "object":
                result = self.model.toggle_hidden(target[1])
                self.say("숨김/위장 대상이 아님" if result is None else f"{target[1]['id']}: {'켜짐' if result else '꺼짐'}")
        elif tool == "text":
            if target and target[0] == "object" and target[1]["kind"] == "clue":
                self._start_typing(target[1])
        else:
            obj = self.model.add_object(tool, x, y)
            if obj["kind"] == "clue":
                self._start_typing(obj)
        self.dirty = True

    def _click_link(self, target, x, y) -> None:
        if self.pending is None:
            if target and target[0] == "object" and (target[1]["kind"] in LINKABLE or target[1]["kind"] == "portal"):
                self.pending = target[1]
                self.say("포탈 목적지를 클릭" if target[1]["kind"] == "portal" else "연결할 문을 클릭 (레버는 토글)")
            else:
                self.say("열쇠/버튼/레버/압력판/포탈을 먼저 클릭", COLORS["warn"])
            return
        source, self.pending = self.pending, None
        if source["kind"] == "portal":
            self.model.set_portal_dest(source, x, y)
            self.say(f"{source['id']} 목적지 변경")
        elif target and target[0] == "object" and self.model.link(source, target[1]):
            self.say(f"{source['id']} → {target[1]['id']}")
        else:
            self.say("문을 클릭해야 연결됨", COLORS["warn"])

    def _start_typing(self, clue) -> None:
        self.typing, self.text_buffer = clue, clue["params"].get("content", "")
        pygame.key.start_text_input()
        self.say("단서 내용 입력 후 Enter (Esc 취소)")

    def _handle_typing(self, event) -> None:
        if event.type == pygame.TEXTINPUT:
            self.text_buffer += event.text
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN:
                self.model.set_clue_text(self.typing, self.text_buffer)
                self.typing = None
                self.dirty = True
                pygame.key.stop_text_input()
            elif event.key == pygame.K_ESCAPE:
                self.typing = None
                pygame.key.stop_text_input()
            elif event.key == pygame.K_BACKSPACE:
                self.text_buffer = self.text_buffer[:-1]

    def save(self) -> None:
        errors, warnings = self.model.validate()
        if errors:
            self.say("저장 불가: " + errors[0], COLORS["err"])
            return
        os.makedirs(os.path.dirname(os.path.abspath(self.save_path)), exist_ok=True)
        self.model.save(self.save_path)
        note = f" (경고 {len(warnings)}개)" if warnings else ""
        self.say(f"저장됨: {os.path.relpath(self.save_path)}{note}", COLORS["warn"] if warnings else COLORS["ok"])

    # ---- 테스트 플레이 ----

    def start_play(self) -> None:
        errors, _ = self.model.validate()
        if errors:
            self.say("플레이 불가: " + errors[0], COLORS["err"])
            return
        from .builder import build_environment  # 플레이할 때만 Environment를 불러옴
        env, _, objectives = build_environment(self.model.finalize())
        policies = {}
        for agent_id, agent in env.agents.items():
            policies[agent_id] = ManualPolicy()
            agent.set_policy(policies[agent_id])
        self.play = {"env": env, "objectives": objectives, "policies": policies, "current": 0}
        self.say("테스트 플레이: 방향키 이동, Q/E 회전, Space 상호작용, X 내려놓기, Tab 에이전트 전환, P 종료")

    def _current_agent_id(self):
        ids = list(self.play["env"].agents)
        return ids[self.play["current"] % len(ids)]

    def _handle_play(self, event) -> None:
        if event.type != pygame.KEYDOWN:
            return
        env = self.play["env"]
        agent_id = self._current_agent_id()
        agent = env.agents[agent_id]
        step = env.max_move or 20.0
        moves = {pygame.K_LEFT: (-step, 0), pygame.K_RIGHT: (step, 0), pygame.K_UP: (0, -step), pygame.K_DOWN: (0, step),
                 pygame.K_a: (-step, 0), pygame.K_d: (step, 0), pygame.K_w: (0, -step), pygame.K_s: (0, step)}
        action = None
        if event.key in (pygame.K_p, pygame.K_ESCAPE):
            self.play = None
            self.say("편집 모드")
            return
        if event.key == pygame.K_TAB:
            self.play["current"] += 1
            return
        if event.key in moves:
            dx, dy = moves[event.key]
            action = {"type": "move", "dx": dx, "dy": dy}
        elif event.key in (pygame.K_q, pygame.K_e):
            action = {"type": "turn", "facing": agent.facing + (-45 if event.key == pygame.K_q else 45)}
        elif event.key == pygame.K_SPACE:
            action = self._smart_interact(env, agent)
        elif event.key == pygame.K_x and agent.inventory:
            action = {"type": "drop", "object_id": agent.inventory[-1]["object_id"]}
        elif event.key == pygame.K_PERIOD:
            action = {"type": "noop"}
        if action is not None:
            self.play["policies"][agent_id].next_action = action
            env.step()

    # 가까운 것부터: 열쇠 사용 → 레버/버튼 → 줍기
    @staticmethod
    def _smart_interact(env, agent) -> dict:
        def dist(o):
            return math.hypot(o["x"] - agent.x, o["y"] - agent.y)
        for key in agent.inventory:
            door = env.objects.get(key.get("unlocks")) if key["type"] == "key" else None
            if door is not None and dist(door) <= env.interact_radius + door.get("radius", 0):
                return {"type": "use_key", "key_id": key["object_id"]}
        near = sorted((o for o in env.objects.values() if dist(o) <= env.interact_radius), key=dist)
        for obj in near:
            if obj["type"] == "lever":
                return {"type": "pull_lever", "lever_id": obj["object_id"]}
            if obj["type"] == "button":
                return {"type": "press_button", "button_id": obj["object_id"]}
            if obj["type"] in ("item", "key"):
                return {"type": "pick_up", "object_id": obj["object_id"]}
        return {"type": "noop"}

    # ---- 그리기 ----

    def text(self, s, pos, color=None, font=None) -> None:
        self.screen.blit((font or self.font).render(str(s), True, color or COLORS["text"]), pos)

    def draw(self) -> None:
        self.screen.fill(COLORS["bg"])
        pygame.draw.rect(self.screen, COLORS["map"], (PAD, PAD, self.map_px_w, self.map_px_h))
        spec = self.model.spec
        for gx in range(0, spec.width + 1, 50):
            pygame.draw.line(self.screen, COLORS["grid"], self.to_screen(gx, 0), self.to_screen(gx, spec.height))
        for gy in range(0, spec.height + 1, 50):
            pygame.draw.line(self.screen, COLORS["grid"], self.to_screen(0, gy), self.to_screen(spec.width, gy))
        if self.play is not None:
            self._draw_play()
        else:
            self._draw_edit()
        self._draw_sidebar()

    def _draw_walls(self, walls) -> None:
        for wx, wy, ww, wh in walls:
            sx, sy = self.to_screen(wx, wy)
            pygame.draw.rect(self.screen, COLORS["wall"], (sx, sy, max(1, int(ww * self.scale)), max(1, int(wh * self.scale))))

    def _draw_cone(self, x, y, facing, color) -> None:
        points = [self.to_screen(x, y)]
        for i in range(13):
            a = math.radians(facing - VIEW_ANGLE / 2 + VIEW_ANGLE * i / 12)
            points.append(self.to_screen(x + math.cos(a) * VIEW_RADIUS, y + math.sin(a) * VIEW_RADIUS))
        pygame.draw.polygon(self.screen, color, points, 1)

    def _draw_object(self, kind, category, x, y, label, locked=True, hidden=False, goal=False, highlight=False) -> None:
        sx, sy = self.to_screen(x, y)
        r = max(5, int(8 * self.scale))
        color_key = {"item": {"coop": "coop", "trap": "trap"}.get(category, "item")}.get(kind, kind)
        if kind == "door" and not locked:
            color_key = "door_open"
        color = COLORS.get(color_key, COLORS["item"])
        if kind == "door":
            pygame.draw.rect(self.screen, color, (sx - r, sy - r, r * 2, r * 2))
        elif kind == "pressure_plate":
            pygame.draw.circle(self.screen, color, (sx, sy), r + 3, 2)
        elif kind == "portal":
            pygame.draw.circle(self.screen, color, (sx, sy), r, 3)
        elif kind == "key":
            pygame.draw.polygon(self.screen, color, [(sx, sy - r), (sx + r, sy), (sx, sy + r), (sx - r, sy)])
        else:
            pygame.draw.circle(self.screen, color, (sx, sy), r)
        if hidden:
            pygame.draw.circle(self.screen, COLORS["dim"], (sx, sy), r + 6, 1)
        if goal:
            pygame.draw.circle(self.screen, COLORS["goal"], (sx, sy), r + 4, 2)
        if highlight:
            pygame.draw.circle(self.screen, COLORS["select"], (sx, sy), r + 8, 1)
        self.text(label, (sx + r + 2, sy - r - 2), COLORS["dim"], self.small)

    def _draw_agent(self, agent_id, x, y, facing, current=False) -> None:
        sx, sy = self.to_screen(x, y)
        self._draw_cone(x, y, facing, COLORS["select"] if current else COLORS["cone"])
        pygame.draw.circle(self.screen, COLORS["agent"], (sx, sy), 9)
        end = (sx + int(math.cos(math.radians(facing)) * 16), sy + int(math.sin(math.radians(facing)) * 16))
        pygame.draw.line(self.screen, COLORS["agent"], (sx, sy), end, 2)
        self.text(agent_id, (sx - 4, sy - 8), COLORS["bg"])

    def _draw_edit(self) -> None:
        spec = self.model.spec
        self._draw_walls(spec.walls)
        objects = {o["id"]: o for o in spec.objects}
        for obj in spec.objects:  # 연결선
            params = obj["params"]
            targets = [params.get("unlocks"), params.get("linked_door_id"), *params.get("linked_door_ids", [])]
            for door_id in targets:
                if door_id in objects:
                    color = COLORS.get(obj["kind"], COLORS["dim"])
                    pygame.draw.line(self.screen, color, self.to_screen(obj["x"], obj["y"]),
                                     self.to_screen(objects[door_id]["x"], objects[door_id]["y"]), 1)
            if obj["kind"] == "portal":
                pygame.draw.line(self.screen, COLORS["portal"], self.to_screen(obj["x"], obj["y"]),
                                 self.to_screen(params["dest_x"], params["dest_y"]), 1)
        for obj in spec.objects:
            params = obj["params"]
            self._draw_object(obj["kind"], params.get("category"), obj["x"], obj["y"], obj["id"],
                              hidden=params.get("hidden", False) or params.get("disguised", False),
                              goal=self.model.is_goal(obj), highlight=obj is self.pending)
        for agent in spec.agents:
            self._draw_agent(agent["id"], agent["x"], agent["y"], agent["facing"])
        if self.tool == "wall" and isinstance(self.pending, tuple):  # 벽 드래그 미리보기
            (x0, y0), (x1, y1) = self.pending, self.hover
            sx, sy = self.to_screen(min(x0, x1), min(y0, y1))
            pygame.draw.rect(self.screen, COLORS["select"], (sx, sy, int(abs(x1 - x0) * self.scale), int(abs(y1 - y0) * self.scale)), 1)
        if self.tool == "portal" and isinstance(self.pending, tuple):
            pygame.draw.line(self.screen, COLORS["portal"], self.to_screen(*self.pending), self.to_screen(*self.hover), 1)

    def _draw_play(self) -> None:
        env = self.play["env"]
        current = self._current_agent_id()
        visible = {o["object_id"] for o in env.get_observation(current)["visible_objects"]}
        self._draw_walls(env._walls())
        for obj in env.objects.values():
            self._draw_object(obj["type"], obj.get("category"), obj["x"], obj["y"], obj["object_id"],
                              locked=obj.get("locked", True), hidden=obj.get("hidden", False),
                              highlight=obj["object_id"] in visible)
        for agent_id, agent in env.agents.items():
            self._draw_agent(agent_id, agent.x, agent.y, agent.facing, current=agent_id == current)

    def _draw_sidebar(self) -> None:
        x = PAD * 2 + self.map_px_w
        y = PAD
        line = 20
        if self.play is not None:
            self._draw_play_sidebar(x, y, line)
            return
        spec = self.model.spec
        self.text("MACI 맵 에디터", (x, y)); y += line + 4
        self.text(f"맵 {spec.width}x{spec.height}  마우스 ({self.hover[0]:.0f}, {self.hover[1]:.0f})", (x, y), COLORS["dim"]); y += line
        for key, tool, desc in TOOL_HELP:
            color = COLORS["goal"] if tool == self.tool else COLORS["text"]
            self.text(f"[{key}] {desc}", (x, y), color, self.small); y += 16
        y += 6
        for s in ("우클릭: 삭제 / 진행 중 작업 취소", "휠: 에이전트 방향 회전 (45도)", "Ctrl+S: 저장   P: 테스트 플레이", "Esc: 선택 도구"):
            self.text(s, (x, y), COLORS["dim"], self.small); y += 16
        y += 8
        self.text(f"저장 경로: {os.path.relpath(self.save_path)}", (x, y), COLORS["dim"], self.small); y += line
        self.text(f"목표 {len(spec.objectives)}개  에이전트 {len(spec.agents)}명  오브젝트 {len(spec.objects)}개", (x, y)); y += line
        if self.dirty:
            self.validation, self.dirty = self.model.validate(), False
        errors, warnings = self.validation
        for msg in errors[:3]:
            y = self._wrapped(msg, x, y, COLORS["err"])
        for msg in warnings[:6]:
            y = self._wrapped(msg, x, y, COLORS["warn"])
        if not errors and not warnings:
            self.text("검증 통과", (x, y), COLORS["ok"]); y += line
        if self.typing is not None:
            y += 6
            self.text("단서 입력:", (x, y), COLORS["goal"]); y += line
            y = self._wrapped(self.text_buffer + "|", x, y, COLORS["text"])
        self.text(self.message, (x, self.screen.get_height() - PAD - 18), self.message_color, self.small)

    def _draw_play_sidebar(self, x, y, line) -> None:
        env = self.play["env"]
        current = self._current_agent_id()
        agent = env.agents[current]
        self.text("테스트 플레이", (x, y)); y += line + 4
        self.text(f"step {env.step_count}   조작 중: {current}", (x, y)); y += line
        self.text(f"위치 ({agent.x:.2f}, {agent.y:.2f})  방향 {agent.facing:.2f}°", (x, y), COLORS["dim"], self.small); y += line
        inv = ", ".join(o["object_id"] for o in agent.inventory) or "없음"
        self.text(f"인벤토리: {inv}", (x, y), COLORS["dim"], self.small); y += line
        self.text("목표:", (x, y)); y += line
        for objective in self.play["objectives"]:
            done = any(all(e.get(k) == v for k, v in objective.items()) for e in env.event_log.entries)
            label = objective.get("door_id") or objective.get("object_id")
            self.text(f"{'[v]' if done else '[ ]'} {objective['type']} {label}", (x + 8, y),
                      COLORS["ok"] if done else COLORS["text"], self.small); y += 16
        if env.failure:
            y = self._wrapped(f"실패: {env.failure['agent_id']}가 함정 {env.failure['object_id']}을 집음", x, y + 4, COLORS["err"])
        y += 8
        self.text("최근 이벤트:", (x, y)); y += line
        for e in env.event_log.entries[-12:]:
            detail = e.get("door_id") or e.get("object_id") or e.get("plate_id") or e.get("portal_id") or e.get("lever_id") or ""
            self.text(f"{e['step']:>3} {e['type']} {','.join(e['agent_ids'])} {detail}", (x + 8, y), COLORS["dim"], self.small); y += 15
        help_lines = ("방향키/WASD 이동, Q/E 회전", "Space 상호작용, X 내려놓기, . 대기", "Tab 에이전트 전환, P/Esc 편집으로")
        bottom = self.screen.get_height() - PAD - 18 - 16 * (len(help_lines) + 1)
        for i, s in enumerate(help_lines):
            self.text(s, (x, bottom + 16 * i), COLORS["dim"], self.small)
        self.text(self.message, (x, self.screen.get_height() - PAD - 18), self.message_color, self.small)

    def _wrapped(self, msg, x, y, color, width=SIDEBAR_W - 30) -> int:
        words, cur = msg.split(" "), ""
        for word in words:
            trial = (cur + " " + word).strip()
            if self.small.size(trial)[0] > width and cur:
                self.text(cur, (x, y), color, self.small)
                y, cur = y + 16, word
            else:
                cur = trial
        if cur:
            self.text(cur, (x, y), color, self.small)
            y += 16
        return y


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--load", default=None, help="편집할 맵 JSON")
    parser.add_argument("--seed", type=int, default=None, help="이 시드로 무작위 생성한 맵에서 시작")
    parser.add_argument("--width", type=int, default=500)
    parser.add_argument("--height", type=int, default=500)
    parser.add_argument("--out", default=None, help="저장 경로 (기본: 불러온 파일, 없으면 map_datas/custom_<시각>.json)")
    args = parser.parse_args(argv)

    if args.load:
        spec = MapSpec.load(args.load)
    elif args.seed is not None:
        from .generator import GenConfig, generate_map
        spec = generate_map(args.seed, GenConfig(width=args.width, height=args.height))
    else:
        spec = MapSpec(seed=0, width=args.width, height=args.height)
    save_path = args.out or args.load or os.path.join(
        MAP_DATAS_DIR, f"custom_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json")

    pygame.init()
    EditorApp(EditorModel(spec), save_path).run()


if __name__ == "__main__":
    main(sys.argv[1:])
