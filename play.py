"""사람이 직접 플레이하는 창 (한 컴퓨터에서 두 사람이 번갈아 조종).

    python play.py --environment sequence_rooms --sequence-seed 3 --steps 80
    python play.py --map-file map_datas/s01_deadlock.json --steps 300

두 사람이 각자 에이전트 하나(A, B)를 맡습니다. 화면에는 LLM이 받는 관찰과 같은 정보만 그립니다.
- 지금 시야에 보이는 물체 (진하게)와 예전에 본 물체 (흐리게, 마지막으로 본 상태)
- 근처 벽, 받은 메시지, 직전 행동 결과, 알림
- 상대 에이전트는 보이지 않습니다.

턴제입니다. 매 step 두 사람이 차례로 행동을 하나씩 고르면 두 행동이 동시에 적용됩니다. 상대 차례에는
화면을 가리므로 정보 비대칭이 유지됩니다. 결과는 benchmark.py와 같은 형식(benchmark_runs/human_*.jsonl,
.score.json)으로 저장되어 뷰어, 채점, 사람 채점, 집계에 그대로 쓸 수 있습니다.

조작 (자기 차례에만)
  ← / →   15도 회전 (Shift: 45도)       ↑       20 전진 (Shift: 5)        Space  대기(noop)
  R       각도를 입력하고 Enter          F       거리를 입력하고 Enter
  E       손 닿는 곳(15)의 물체와 상호작용 (줍기, 버튼 누르기, 레버 당기기, 열쇠 쓰기)
  D       들고 있는 물건 내려놓기        T       메시지를 입력하고 Enter (상대에게 전송)
  지도 왼쪽 클릭: 물체 자세히 보기 (턴 소모 없음)    오른쪽 클릭: 그 지점 쪽으로 회전
  H       과제 설명 보기/닫기            Esc     입력 취소
"""
from __future__ import annotations

import argparse
import datetime
import json
import math
import os
import queue
import sys
import threading
from pathlib import Path

import pygame

import benchmark
from policy import Policy, PolicyGaveUp

BG, PANEL, TEXT, DIM, ACCENT, WARN = (18, 23, 33), (29, 37, 51), (227, 235, 246), (154, 171, 193), (73, 166, 228), (232, 170, 92)
PLAYER_COLORS = {"A": (255, 133, 155), "B": (87, 184, 255)}
OBJECT_COLORS = {"button": (87, 196, 219), "lever": (233, 158, 76), "key": (242, 215, 90), "item": (202, 204, 211),
                 "pressure_plate": (113, 191, 127), "switch_plate": (113, 191, 127), "sync_pad": (113, 191, 127),
                 "portal": (172, 125, 231), "clue": (241, 225, 135), "display": (166, 194, 200),
                 "number_pad": (128, 190, 236), "keypad": (166, 194, 200), "checkpoint": (190, 140, 220),
                 "receptacle": (150, 210, 170), "goal_zone": (96, 208, 138)}
INTERACT_RADIUS = 15.0
MAP_BOX = (24, 70, 760, 660)  # 지도 영역 (x, y, w, h)


# ---------------------------------------------------------------- 행동 만들기 (GUI와 분리, 테스트용)

def turn_toward(observation: dict, x: float, y: float) -> dict:
    me = observation["self"]
    target = math.degrees(math.atan2(y - me["y"], x - me["x"])) % 360
    return {"type": "turn", "angle": round((target - me["facing"] + 180) % 360 - 180, 2)}


def interaction_action(observation: dict, reach: float = INTERACT_RADIUS) -> dict | None:
    """손 닿는 곳에서 가장 가까운 물체에 맞는 상호작용. 없으면 None (턴을 쓰지 않음)."""
    me = observation["self"]
    inventory_keys = [o for o in me.get("inventory", []) if o.get("type") == "key"]
    candidates = []
    for obj in observation.get("visible_objects", []):
        distance = math.hypot(obj["x"] - me["x"], obj["y"] - me["y"])
        kind = obj["type"]
        if kind in ("item", "key") and distance <= reach:
            action = {"type": "pick_up", "object_id": obj["object_id"]}
        elif kind == "button" and distance <= reach:
            action = {"type": "press_button", "button_id": obj["object_id"]}
        elif kind == "lever" and distance <= reach:
            action = {"type": "pull_lever", "lever_id": obj["object_id"]}
        elif kind == "door" and obj.get("locked") and distance <= reach + obj.get("radius", 0.0):
            key = next((k for k in inventory_keys if k.get("unlocks") == obj["object_id"]), None)
            if key is None:
                continue
            action = {"type": "use_key", "key_id": key["object_id"]}
        else:
            continue
        candidates.append((distance, action))
    return min(candidates, key=lambda c: c[0])[1] if candidates else None


def drop_action(observation: dict) -> dict | None:
    inventory = observation["self"].get("inventory", [])
    return {"type": "drop", "object_id": inventory[0]["object_id"]} if inventory else None


# ---------------------------------------------------------------- 게임 루프와 GUI 연결

class HumanBridge:
    """게임 루프 스레드의 decide()와 GUI(메인 스레드)를 잇는 창구."""

    def __init__(self) -> None:
        self.requests: queue.Queue = queue.Queue()
        self.closed = False

    def request(self, agent_id: str, observation: dict) -> dict:
        if self.closed:
            raise PolicyGaveUp("player quit")
        reply: queue.Queue = queue.Queue()
        self.requests.put((agent_id, observation, reply))
        action = reply.get()
        if action is None:
            raise PolicyGaveUp("player quit")
        return action

    def close(self) -> None:
        self.closed = True


class HumanPolicy(Policy):
    def __init__(self, bridge: HumanBridge, agent_id: str, task_description: str) -> None:
        self.bridge, self.agent_id, self.task_description = bridge, agent_id, task_description

    def decide(self, observation: dict) -> dict:
        return self.bridge.request(self.agent_id, observation)


class PlayApp:
    def __init__(self, bridge: HumanBridge, steps: int, log_path: Path) -> None:
        pygame.init()
        self.screen = pygame.display.set_mode((1180, 760))
        pygame.display.set_caption("MACI 사람 플레이")
        font = pygame.font.match_font("malgungothic,nanumgothic,applegothic")
        self.font, self.small = pygame.font.Font(font, 18), pygame.font.Font(font, 14)
        self.big = pygame.font.Font(font, 30)
        self.bridge, self.steps, self.log_path = bridge, steps, log_path
        self.tasks: dict[str, str] = {}
        self.pending: dict[str, tuple[dict, queue.Queue]] = {}
        self.current: str | None = None
        self.curtain = True
        self.input_mode: str | None = None   # "turn" / "forward" / "message"
        self.input_text = ""
        self.selected: str | None = None
        self.show_task = False
        self.info = ""
        self.finished = False
        self.done = False            # 게임 루프 스레드가 끝났는지
        self._swallow_text = False   # 입력창을 연 키(R/F/T)의 글자가 입력창에 들어가지 않게 함
        self.result_lines: list[str] = []

    # ---- 차례 관리
    def poll(self) -> None:
        while True:
            try:
                agent_id, observation, reply = self.bridge.requests.get_nowait()
            except queue.Empty:
                break
            self.pending[agent_id] = (observation, reply)
        if self.current is None and self.pending:
            self.current = min(self.pending)
            self.curtain, self.input_mode, self.input_text, self.selected = True, None, "", None
            self.info = ""

    @property
    def observation(self) -> dict | None:
        return self.pending[self.current][0] if self.current in self.pending else None

    def submit(self, action: dict | None) -> None:
        if action is None or self.current is None:
            return
        _, reply = self.pending.pop(self.current)
        reply.put(action)
        self.current = None

    def other_agents(self) -> list[str]:
        return [a for a in sorted(self.tasks or {"A": "", "B": ""}) if a != self.current]

    # ---- 입력 처리 (테스트에서 직접 부를 수 있게 pygame 이벤트와 분리)
    def handle_key(self, key: int, mod: int = 0, text: str = "") -> None:
        if self.finished or self.current is None:
            return
        if self.curtain:
            if key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                self.curtain = False
                self.show_task = self.show_task or not self.observation["self"].get("step", 0) > 1
            return
        if self.input_mode:
            self._handle_input(key, text)
            return
        shift = bool(mod & pygame.KMOD_SHIFT)
        observation = self.observation
        if key == pygame.K_h:
            self.show_task = not self.show_task
        elif self.show_task and key in (pygame.K_ESCAPE, pygame.K_RETURN):
            self.show_task = False
        elif key == pygame.K_LEFT:
            self.submit({"type": "turn", "angle": -45 if shift else -15})
        elif key == pygame.K_RIGHT:
            self.submit({"type": "turn", "angle": 45 if shift else 15})
        elif key == pygame.K_UP:
            self.submit({"type": "move_forward", "distance": 5 if shift else 20})
        elif key == pygame.K_SPACE:
            self.submit({"type": "noop"})
        elif key == pygame.K_e:
            action = interaction_action(observation)
            if action is None:
                self.info = f"손 닿는 곳({INTERACT_RADIUS:g})에 상호작용할 물체가 없습니다."
            self.submit(action)
        elif key == pygame.K_d:
            action = drop_action(observation)
            if action is None:
                self.info = "들고 있는 물건이 없습니다."
            self.submit(action)
        elif key in (pygame.K_r, pygame.K_f, pygame.K_t):
            self.input_mode = {pygame.K_r: "turn", pygame.K_f: "forward", pygame.K_t: "message"}[key]
            self.input_text = ""
            self._swallow_text = True

    def _handle_input(self, key: int, text: str) -> None:
        if key == pygame.K_ESCAPE:
            self.input_mode, self.input_text = None, ""
        elif key == pygame.K_BACKSPACE:
            self.input_text = self.input_text[:-1]
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            mode, value = self.input_mode, self.input_text.strip()
            self.input_mode, self.input_text = None, ""
            try:
                if mode == "turn":
                    self.submit({"type": "turn", "angle": float(value)})
                elif mode == "forward":
                    self.submit({"type": "move_forward", "distance": max(0.0, float(value))})
                elif value:
                    receiver = self.other_agents()[0]
                    self.submit({"type": "send_message", "receiver_id": receiver, "content": value})
            except ValueError:
                self.info = "숫자를 입력하세요."
        elif text:
            if self._swallow_text:  # 방금 입력창을 연 키가 만든 글자
                self._swallow_text = False
                return
            self.input_text += text

    def handle_click(self, pos, button: int) -> None:
        if self.finished or self.current is None or self.curtain or self.input_mode:
            return
        observation = self.observation
        to_world, to_screen = self._transform(observation)
        if button == 3:
            self.submit(turn_toward(observation, *to_world(pos)))
            return
        nearest = None
        for obj in observation.get("known_objects", {}).values():
            sx, sy = to_screen(obj["x"], obj["y"])
            distance = math.hypot(sx - pos[0], sy - pos[1])
            if distance <= 14 and (nearest is None or distance < nearest[0]):
                nearest = (distance, obj["object_id"])
        self.selected = nearest[1] if nearest else None

    # ---- 그리기
    def text(self, value, x, y, font=None, color=TEXT, width=None) -> None:
        font = font or self.small
        value = str(value).replace("\n", " ")
        if width:
            while value and font.size(value)[0] > width:
                value = value[:-1]
        self.screen.blit(font.render(value, True, color), (x, y))

    def wrap(self, value, width, font=None) -> list[str]:
        font = font or self.small
        lines = []
        for paragraph in str(value).split("\n"):
            rest = paragraph or " "
            while rest:
                n = min(len(rest), 200)
                while n > 1 and font.size(rest[:n])[0] > width:
                    n -= 1
                lines.append(rest[:n])
                rest = rest[n:]
        return lines

    def _transform(self, observation):
        me = observation["self"]
        bx, by, bw, bh = MAP_BOX
        scale = min(bw / max(1, me["map_width"]), bh / max(1, me["map_height"]))
        ox = bx + (bw - me["map_width"] * scale) / 2
        oy = by + (bh - me["map_height"] * scale) / 2
        return (lambda p: ((p[0] - ox) / scale, (p[1] - oy) / scale),
                lambda x, y: (round(ox + x * scale), round(oy + y * scale)))

    def draw(self) -> None:
        self.screen.fill(BG)
        if self.finished:
            self.text("게임 종료", 24, 24, self.big)
            for i, line in enumerate(self.result_lines):
                self.text(line, 24, 90 + i * 26, self.font)
            self.text("창을 닫으면 끝납니다. 결과: " + str(self.log_path), 24, 700, color=DIM)
        elif self.current is None:
            self.text("다음 step을 준비하는 중입니다…", 24, 24, self.font)
        elif self.curtain:
            color = PLAYER_COLORS.get(self.current, ACCENT)
            self.text(f"플레이어 {self.current} 차례", 380, 300, self.big, color)
            self.text("다른 플레이어는 화면을 보지 마세요. 준비되면 Enter를 누르세요.", 330, 350, self.font)
            self.text(f"step {self.observation['self']['step']} / {self.steps}", 520, 390, color=DIM)
        else:
            self._draw_view(self.observation)
        pygame.display.flip()

    def _draw_view(self, observation: dict) -> None:
        me = observation["self"]
        color = PLAYER_COLORS.get(self.current, ACCENT)
        self.text(f"플레이어 {self.current}", 24, 20, self.big, color)
        stage = observation.get("stage")
        stage_text = f"   단계 {stage['stage']}/{stage['total']} {stage.get('title', '')}" if stage else ""
        self.text(f"step {me['step']} / {self.steps}{stage_text}", 220, 30, self.font, DIM, width=560)
        _, to_screen = self._transform(observation)
        bx, by, bw, bh = MAP_BOX
        x0, y0 = to_screen(0, 0)
        x1, y1 = to_screen(me["map_width"], me["map_height"])
        pygame.draw.rect(self.screen, PANEL, (x0, y0, x1 - x0, y1 - y0))
        scale = (x1 - x0) / max(1, me["map_width"])

        # 시야 부채꼴 (90도, 200)
        cx, cy = to_screen(me["x"], me["y"])
        cone = [(cx, cy)] + [to_screen(me["x"] + 200 * math.cos(math.radians(me["facing"] + a)),
                                       me["y"] + 200 * math.sin(math.radians(me["facing"] + a))) for a in range(-45, 46, 5)]
        overlay = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        pygame.draw.polygon(overlay, (*color, 28), cone)
        self.screen.set_clip(pygame.Rect(x0, y0, x1 - x0, y1 - y0))  # 시야 부채꼴이 지도 밖으로 나가지 않게
        self.screen.blit(overlay, (0, 0))
        self.screen.set_clip(None)

        for wx, wy, ww, wh in observation.get("walls", []):
            pygame.draw.rect(self.screen, (140, 151, 169), (*to_screen(wx, wy), max(1, ww * scale), max(1, wh * scale)))
        visible = {o["object_id"] for o in observation.get("visible_objects", [])}
        for obj in observation.get("known_objects", {}).values():
            self._draw_object(obj, to_screen, scale, obj["object_id"] in visible)

        pygame.draw.circle(self.screen, color, (cx, cy), 7)
        hx, hy = me["heading"]["x"], me["heading"]["y"]
        pygame.draw.line(self.screen, color, (cx, cy), (cx + hx * 18, cy + hy * 18), 3)
        self._draw_panel(observation)
        if self.show_task:
            self._draw_task()

    def _draw_object(self, obj, to_screen, scale, visible) -> None:
        kind = obj["type"]
        base = OBJECT_COLORS.get(kind, (185, 193, 206))
        if kind == "door":
            base = (218, 112, 95) if obj.get("locked") else (96, 208, 138)
        shade = base if visible else tuple(c // 2 for c in base)
        sx, sy = to_screen(obj["x"], obj["y"])
        radius = max(4, round(obj.get("radius", 6) * scale))
        if kind == "goal_zone":
            w, h = obj.get("width", 20) * scale, obj.get("height", 20) * scale
            pygame.draw.rect(self.screen, shade, (sx - w / 2, sy - h / 2, w, h), 2)
        elif kind in ("door", "number_pad", "keypad", "display", "receptacle"):
            pygame.draw.rect(self.screen, shade, (sx - radius, sy - radius, radius * 2, radius * 2),
                             0 if obj.get("locked", True) else 2, border_radius=3)
        else:
            pygame.draw.circle(self.screen, shade, (sx, sy), radius,
                               2 if kind in ("pressure_plate", "switch_plate", "sync_pad", "portal", "checkpoint") else 0)
        label = obj.get("label") if kind == "button" else obj.get("number", obj["object_id"]) if kind == "number_pad" else obj["object_id"]
        self.text(label, sx + radius + 3, sy - 8, color=TEXT if visible else DIM, width=110)
        if obj["object_id"] == self.selected:
            pygame.draw.circle(self.screen, ACCENT, (sx, sy), radius + 5, 2)

    def _draw_panel(self, observation) -> None:
        me = observation["self"]
        x, width = 800, 356
        pygame.draw.rect(self.screen, PANEL, (x - 8, 70, width + 16, 660), border_radius=8)
        lines = [f"위치 ({me['x']:.1f}, {me['y']:.1f})  방향 {me['facing']:.0f}°",
                 "들고 있는 것: " + (", ".join(o["object_id"] for o in me.get("inventory", [])) or "없음")]
        result = observation.get("last_action_result")
        if result:
            lines.append(f"직전 행동: {result.get('action_type')} → {result.get('status')}"
                         + (f" ({result['reason']})" if result.get("reason") else ""))
        for notice in observation.get("notices", [])[-3:]:
            lines.append("알림: " + json.dumps(notice, ensure_ascii=False))
        stage = observation.get("stage")
        if stage and stage.get("briefing"):
            lines.append("단계 안내: " + stage["briefing"])
        lines.append("── 받은 메시지 (최근순) ──")
        inbox = observation.get("inbox", [])
        lines += [f"[step {m.get('step')}] {m.get('from')}: {m.get('content', m)}" for m in reversed(inbox[-6:])] or ["없음"]
        detail = observation.get("known_objects", {}).get(self.selected) if self.selected else None
        if detail is None:
            detail = next((o for o in observation.get("visible_objects", []) if o["type"] in ("clue", "display")), None)
        if detail is not None:
            lines.append("── " + ("선택한 물체" if self.selected else "보이는 안내판") + f": {detail['object_id']} ──")
            shown = {k: v for k, v in detail.items() if k not in ("object_id", "x", "y")}
            lines.append(json.dumps(shown, ensure_ascii=False))
        y = 80
        for line in lines:
            for part in self.wrap(line, width):
                if y > 600:
                    break
                self.text(part, x, y)
                y += 19
        if self.input_mode:
            label = {"turn": "회전 각도(도, 음수는 반시계)", "forward": "전진 거리", "message": "메시지"}[self.input_mode]
            pygame.draw.rect(self.screen, BG, (x - 4, 612, width + 8, 54), border_radius=5)
            self.text(label + " - Enter 전송, Esc 취소", x, 616, color=ACCENT)
            self.text(self.input_text + "|", x, 638, self.font, width=width)
        else:
            help_lines = ["←/→ 회전  ↑ 전진(Shift 작게)  Space 대기",
                          "E 상호작용  D 내려놓기  T 메시지  H 과제 설명",
                          "R 각도  F 거리  우클릭 회전  좌클릭 물체 보기"]
            for i, line in enumerate(help_lines):
                self.text(line, x, 612 + i * 19, color=DIM, width=width)
        if self.info:
            self.text(self.info, x, 704, color=WARN, width=width)

    def _draw_task(self) -> None:
        overlay = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        overlay.fill((10, 14, 20, 235))
        self.screen.blit(overlay, (0, 0))
        self.text(f"플레이어 {self.current} 과제 설명 (LLM에게 주는 것과 같은 내용) - H 또는 Esc로 닫기", 40, 30, self.font, ACCENT)
        y = 70
        for line in self.wrap(self.tasks.get(self.current, ""), 1100):
            if y > 730:
                break
            self.text(line, 40, y)
            y += 19

    def finish(self) -> None:
        self.finished = True
        score_path = self.log_path.with_suffix(".score.json")
        if not score_path.is_file():
            self.result_lines = ["점수 파일이 없습니다 (중간에 끝났을 수 있습니다)."]
            return
        score = json.loads(score_path.read_text(encoding="utf-8"))
        team = score["team"]
        self.result_lines = [f"클리어: {'예' if team['cleared'] else '아니오'}   클리어 step: {team['clear_step']}",
                             f"총점 {score['total']}   팀 {team['score']}"]
        self.result_lines += [f"플레이어 {aid}: {data['score']}점" for aid, data in score["agents"].items()]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--steps", type=int, default=80)
    parser.add_argument("--out", default=None)
    parser.add_argument("--map-file", default=None)
    parser.add_argument("--environment", choices=("map", "sequence_rooms", "blind_code", "curriculum"), default="map")
    parser.add_argument("--sequence-seed", type=int, default=42)
    parser.add_argument("--pads-per-room", type=int, default=5)
    parser.add_argument("--presses-per-room", type=int, default=3)
    parser.add_argument("--max-resets", type=int, default=None)
    parser.add_argument("--hide-goal", action="store_true")
    args = parser.parse_args()
    if args.environment != "map" and args.map_file:
        parser.error("room environments cannot be combined with --map-file")
    map_spec = benchmark.MapSpec.load(args.map_file) if args.map_file else None
    out = Path(args.out) if args.out else Path(benchmark.RUNS_DIR) / (
        "human_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + ".jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)

    bridge = HumanBridge()
    app = PlayApp(bridge, args.steps, out)

    def factory(agent_id, description):
        app.tasks[agent_id] = description
        return HumanPolicy(bridge, agent_id, description)

    def run():
        try:
            benchmark.run_episode("human", "", "", {}, args.steps, str(out), map_spec, "human", args.environment,
                                  args.sequence_seed, args.pads_per_room, args.presses_per_room, args.max_resets,
                                  reveal_goal=not args.hide_goal, score_config=benchmark.load_score_config(),
                                  policy_factory=factory)
        finally:
            app.done = True

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    clock = pygame.time.Clock()
    pygame.key.start_text_input()
    running = True
    while running:
        app.poll()
        if app.done and not app.finished:
            app.finish()
        app.draw()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                app.handle_key(event.key, event.mod)
            elif event.type == pygame.TEXTINPUT and app.input_mode:
                app.handle_key(0, 0, event.text)
            elif event.type == pygame.MOUSEBUTTONDOWN:
                app.handle_click(event.pos, event.button)
        clock.tick(30)
    # 창을 닫으면 기다리던 decide()를 풀어 회차를 미완료로 끝내고 기록을 남김
    bridge.close()
    for _, reply in app.pending.values():
        reply.put(None)
    worker.join(timeout=10)
    pygame.quit()
    print(f"Wrote manifest: {out}")


if __name__ == "__main__":
    main()
