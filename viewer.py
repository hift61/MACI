"""Observer window: python viewer.py benchmark_runs/run.jsonl [--live]."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import time

import pygame

BG, PANEL, TEXT, DIM = (18, 23, 33), (29, 37, 51), (227, 235, 246), (154, 171, 193)
AGENT_COLORS = [(255, 133, 155), (87, 184, 255), (116, 223, 158), (229, 184, 83)]
OBJECT_COLORS = {'button': (87, 196, 219), 'lever': (233, 158, 76),
                 'key': (242, 215, 90), 'item': (202, 204, 211),
                 'pressure_plate': (113, 191, 127), 'portal': (172, 125, 231),
                 'clue': (241, 225, 135), 'display': (166, 194, 200),
                 'number_pad': (128, 190, 236)}


class TraceReader:
    """Tail only complete UTF-8 JSONL lines; keep an unfinished write for next poll."""
    def __init__(self, path):
        self.path = Path(path)
        self.offset = 0
        self.pending = b''
        self.records = []
        self.scene = None
        self.error = ''

    def poll(self):
        scene_path = self.path.with_suffix('.scene.json')
        if self.scene is None and scene_path.is_file():
            try:
                self.scene = json.loads(scene_path.read_text(encoding='utf-8'))
            except (OSError, UnicodeError, json.JSONDecodeError):
                pass  # The runner may still be writing the initial scene.
        if not self.path.is_file():
            return
        try:
            if self.path.stat().st_size < self.offset:
                self.offset, self.pending, self.records = 0, b'', []
            with self.path.open('rb') as file:
                file.seek(self.offset)
                chunk = file.read()
                self.offset = file.tell()
            parts = (self.pending + chunk).split(b'\n')
            self.pending = parts.pop()
            for line in parts:
                if not line.strip():
                    continue
                try:
                    record = json.loads(line.decode('utf-8-sig'))
                    if 'step' not in record or not isinstance(record.get('agents'), list):
                        raise ValueError('step/agents missing')
                    self.records.append(record)
                except (ValueError, UnicodeError) as exc:
                    self.error = f'읽지 못한 로그 행: {exc}'
        except OSError as exc:
            self.error = str(exc)

    def frames(self):
        initial = [dict(self.scene, step=0, events=[], messages=[], cleared=False)] if self.scene else []
        return initial + self.records


class Viewer:
    def __init__(self, path, live=False):
        pygame.init()
        self.screen = pygame.display.set_mode((1180, 850))
        pygame.display.set_caption('MACI 에이전트 이동 · 관찰자')
        font = pygame.font.match_font('malgungothic,nanumgothic,applegothic')
        self.font = pygame.font.Font(font, 18)
        self.small = pygame.font.Font(font, 14)
        self.reader = TraceReader(path)
        self.reader.poll()
        self.live = live
        self.index = 0
        self.playing = True
        self.speeds = [.5, 1, 2, 4, 8]
        self.speed_index = 2
        self.elapsed = 0.0
        self.scroll = 0
        self.widgets = []
        self.last_poll = 0

    def text(self, text, x, y, small=False, color=TEXT, width=None):
        font = self.small if small else self.font
        text = str(text).replace('\n', ' ')
        if width:
            while text and font.size(text)[0] > width:
                text = text[:-1]
        self.screen.blit(font.render(text, True, color), (x, y))

    def button(self, label, x, width, action):
        rect = pygame.Rect(x, 60, width, 38)
        pygame.draw.rect(self.screen, PANEL, rect, border_radius=6)
        self.text(label, x + 10, 69, width=width - 20)
        self.widgets.append((rect, action))

    def seek(self, index):
        self.index = max(0, min(index, len(self.reader.frames()) - 1))
        self.elapsed = 0

    def pause(self):
        self.playing = not self.playing
        self.elapsed = 0

    def tick(self, dt):
        if time.monotonic() - self.last_poll > .15:
            self.reader.poll()
            self.last_poll = time.monotonic()
        frames = self.reader.frames()
        self.index = max(0, min(self.index, len(frames) - 1))
        if self.playing and self.index + 1 < len(frames):
            self.elapsed += dt * self.speeds[self.speed_index]
            while self.elapsed >= 1 and self.index + 1 < len(frames):
                self.index += 1
                self.elapsed -= 1
        else:
            self.elapsed = 0

    def draw(self):
        self.screen.fill(BG)
        self.widgets = []
        self.text('에이전트 이동 · 실행 로그 재생', 24, 22)
        self.text(self.reader.path.name, 520, 23, small=True, color=DIM, width=620)
        self.button('일시정지' if self.playing else '재생', 24, 120, self.pause)
        self.button('처음', 156, 80, lambda: self.seek(0))
        self.button('이전', 248, 80, lambda: self.seek(self.index - 1))
        self.button('다음', 340, 80, lambda: self.seek(self.index + 1))
        self.button('최신 step', 432, 140, lambda: self.seek(len(self.reader.frames()) - 1))
        self.button(f'{self.speeds[self.speed_index]} step/초', 584, 180,
                    lambda: setattr(self, 'speed_index', (self.speed_index + 1) % len(self.speeds)))
        frames = self.reader.frames()
        if not frames:
            self.text('환경 준비 / 첫 LLM 응답을 기다리는 중입니다…' if self.live else '완료된 로그 행이 없습니다.', 24, 145)
            self.text(self.reader.error, 24, 185, small=True)
            pygame.display.flip()
            return
        frame = frames[self.index]
        world = frame.get('world') or (self.reader.scene or {}).get('world')
        if world is None:
            world = {'width': 500, 'height': 500, 'walls': [], 'objects': []}
        width, height = max(1, world['width']), max(1, world['height'])
        scale = min(720 / width, 610 / height)
        ox, oy = 24 + (740 - width * scale) / 2, 145 + (620 - height * scale) / 2

        def point(x, y):
            return round(ox + x * scale), round(oy + y * scale)

        pygame.draw.rect(self.screen, PANEL, (ox, oy, width * scale, height * scale))
        for wx, wy, ww, wh in world.get('walls', []):
            pygame.draw.rect(self.screen, (140, 151, 169), (*point(wx, wy), max(1, ww * scale), max(1, wh * scale)))
        for obj in world.get('objects', []):
            sx, sy = point(obj['x'], obj['y'])
            kind = obj['type']
            color = OBJECT_COLORS.get(kind, (185, 193, 206))
            radius = max(4, round(obj.get('radius', 6) * scale))
            if kind == 'door':
                color = (218, 112, 95) if obj.get('locked') else (96, 208, 138)
                pygame.draw.rect(self.screen, color, (sx - radius, sy - radius, radius * 2, radius * 2), 2 if not obj.get('locked') else 0)
            elif kind == 'number_pad':
                if 'touch_radius' in obj:
                    pygame.draw.circle(self.screen, tuple(c // 2 for c in color), (sx, sy),
                                       max(1, round(obj['touch_radius'] * scale)), 1)
                pygame.draw.rect(self.screen, color, (sx - 12, sy - 12, 24, 24), border_radius=4)
                self.text(obj.get('number', '?'), sx - 5, sy - 10, color=BG)
            else:
                pygame.draw.circle(self.screen, color, (sx, sy), radius, 2 if kind in ('pressure_plate', 'portal') else 0)
            if kind != 'number_pad':
                self.text(obj['object_id'], sx + radius + 3, sy - 9, small=True, color=DIM, width=115)

        future = frames[min(self.index + 1, len(frames) - 1)]
        future_agents = {a['agent']: a for a in future.get('agents', [])}
        alpha = min(1.0, self.elapsed) if self.playing else 0
        for i, agent in enumerate(frame.get('agents', [])):
            aid = agent['agent']
            color = AGENT_COLORS[i % len(AGENT_COLORS)]
            positions = [next((a['position'] for a in f.get('agents', []) if a['agent'] == aid), None)
                         for f in frames[max(0, self.index - 50):self.index + 1]]
            trail = [point(*p) for p in positions if p is not None]
            if len(trail) > 1:
                pygame.draw.lines(self.screen, tuple(c // 2 for c in color), False, trail, 2)
            x, y = agent['position']
            nx, ny = future_agents.get(aid, agent)['position']
            sx, sy = point(x + (nx - x) * alpha, y + (ny - y) * alpha)
            pygame.draw.circle(self.screen, color, (sx, sy), 10)
            facing = math.radians(agent.get('facing', 0))
            pygame.draw.line(self.screen, color, (sx, sy), (sx + math.cos(facing) * 22, sy + math.sin(facing) * 22), 2)
            self.text(aid, sx - 6, sy - 11, color=BG)

        pygame.draw.rect(self.screen, PANEL, (788, 130, 365, 650), border_radius=8)
        state = '성공' if frame.get('cleared') else ('실패' if frame.get('failure') else '진행 중')
        self.text(f"step {frame['step']} · {state}", 802, 144)
        self.text(f"수신 로그 {len(self.reader.records)} step", 802, 174, small=True, color=DIM)
        details = []
        if frame.get('failure'):
            details.append('실패: ' + str(frame['failure'].get('reason', 'trap')))
        for agent in frame.get('agents', []):
            details.append(f"{agent['agent']} 위치 {agent['position']}")
            decision = agent.get('decision', {})
            action = decision.get('final_action') or {}
            details.append('행동: ' + json.dumps(action, ensure_ascii=False))
            if decision.get('policy_error'):
                details.append('오류: ' + decision['policy_error'])
            if decision.get('recovery'):
                details.append('코드 복구: ' + json.dumps(decision['recovery'], ensure_ascii=False))
            checks = decision.get('code_checks')
            if checks:
                details.append(f"컴파일 {checks['compile_attempts']}회 / 실패 {checks['compile_failures']}회")
                details.append(f"실행 {checks['execution_attempts']}회 / 실패 {checks['execution_failures']}회")
        for label, entries in [('메시지', frame.get('messages', [])), ('이벤트', frame.get('events', []))]:
            details.append(f'── {label} ──')
            details.extend(json.dumps(e, ensure_ascii=False) for e in entries)
        # Wrap long action/message lines so complete contents can be inspected by scrolling.
        wrapped = []
        for line in details:
            rest = str(line).replace('\n', ' ')
            while rest:
                take = min(len(rest), 65)
                while take > 1 and self.small.size(rest[:take])[0] > 330:
                    take -= 1
                wrapped.append(rest[:take])
                rest = rest[take:]
        self.scroll = min(self.scroll, max(0, len(wrapped) - 24))
        for i, line in enumerate(wrapped[self.scroll:self.scroll + 24]):
            self.text(line, 802, 210 + i * 22, small=True, width=330)
        at_end = self.index == len(frames) - 1
        done = frame.get('cleared') or frame.get('failure') or self.reader.path.with_suffix('.score.json').is_file()
        note = '실행 완료 · 처음 버튼으로 다시 재생할 수 있습니다.' if at_end and done else (
            '새 로그를 기다리는 중' if self.live and at_end else '관찰자 화면 · 이동 사이를 보간해 표시')
        if world.get('objects') == [] and self.reader.scene is None:
            note = '이전 형식 로그: 위치만 표시합니다. 맵 정보는 새 실행부터 저장됩니다.'
        self.text(note, 24, 798, small=True, color=DIM, width=1110)
        if self.reader.error:
            self.text(self.reader.error, 24, 824, small=True, color=(238, 135, 123), width=1110)
        pygame.display.flip()

    def run(self):
        clock = pygame.time.Clock()
        running = True
        while running:
            self.tick(clock.tick(30) / 1000)
            self.draw()
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    for rect, action in self.widgets:
                        if rect.collidepoint(event.pos):
                            action()
                            break
                elif event.type == pygame.MOUSEWHEEL:
                    self.scroll = max(0, self.scroll - event.y * 3)
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_SPACE:
                        self.pause()
                    elif event.key == pygame.K_RIGHT:
                        self.seek(self.index + 1)
                    elif event.key == pygame.K_LEFT:
                        self.seek(self.index - 1)
        pygame.quit()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest')
    parser.add_argument('--live', action='store_true')
    args = parser.parse_args()
    if not args.live and not Path(args.manifest).is_file():
        parser.error('manifest file does not exist')
    Viewer(args.manifest, args.live).run()


if __name__ == '__main__':
    main()
