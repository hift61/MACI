"""Pygame launcher for MACI. Run: python launcher.py"""
from __future__ import annotations

import datetime
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading

ROOT = Path(__file__).resolve().parent

try:
    import pygame
except ImportError:
    raise SystemExit("Pygame is missing. Run: python -m pip install -r requirements.txt")

BG = (18, 23, 33)
PANEL = (29, 37, 51)
TEXT = (227, 235, 246)
DIM = (154, 171, 193)
ACCENT = (73, 166, 228)


class Launcher:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((1180, 850))
        pygame.display.set_caption("MACI 실험 실행 도구")
        font_path = pygame.font.match_font("malgungothic,nanumgothic,applegothic")
        self.font = pygame.font.Font(font_path, 18)
        self.small = pygame.font.Font(font_path, 15)
        self.title = pygame.font.Font(font_path, 27)
        self.tab = "맵"
        self.fields = {
            "seed": "42", "agents": "2", "puzzles": "2", "portals": "1",
            "map": "", "steps": "150", "model": "upstage/solar-pro4",
            "url": "https://openrouter.ai/api/v1", "manifest": "",
            "judge": "upstage/solar-pro4", "turns": "5", "agent": "",
            "pads": "5", "presses": "3", "resets": "",
        }
        self.policy = "tooluse"
        self.environment = "map"
        self.auto_view = True
        self.debug = False
        self.viewers = []
        self.reveal = False
        self.focus = None
        self.widgets = []
        self.proc = None
        self.kind = ""
        self.pending_path = None
        self.stopping = False
        self.mail = queue.Queue()
        self.logs = []
        self._log_revision = 0
        self._debug_cache_revision = -1
        self._debug_lines = []
        self.log_scroll = 0
        self.list_scroll = 0
        self.detail_scroll = 0
        self.detail = []
        self.status = "맵 선택 → 실행 → 결과 확인. LLM 실행에는 key.txt가 필요합니다."
        self.maps, self.runs = [], []
        self.refresh()

    def refresh(self):
        self.maps = sorted((ROOT / "map_datas").glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        self.runs = sorted((p for p in (ROOT / "benchmark_runs").glob("*.jsonl")
                            if not p.name.endswith(('.code_checks.jsonl', '.debug.jsonl'))),
                           key=lambda p: p.stat().st_mtime, reverse=True)

    def path(self, name):
        p = Path(self.fields[name].strip())
        return p if p.is_absolute() else ROOT / p

    def number(self, name, minimum=1):
        value = int(self.fields[name])
        if value < minimum:
            raise ValueError(f"{name}: {minimum} 이상을 입력하세요.")
        return str(value)

    def key_ready(self):
        key = ROOT / "key.txt"
        try:
            return key.is_file() and bool(key.read_text(encoding="utf-8-sig").strip())
        except (OSError, UnicodeError):
            return False

    def start(self, args, kind, path=None):
        if self.proc is not None:
            raise ValueError("현재 작업이 끝나거나 중단된 후 다시 실행하세요.")
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        self.proc = subprocess.Popen([sys.executable, "-u", *args], cwd=ROOT, env=env,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     encoding="utf-8", errors="replace", creationflags=flags)
        self.kind, self.pending_path, self.stopping = kind, path, False
        self.logs = [f"> {subprocess.list2cmdline([sys.executable, *args])}"]
        self._log_revision += 1
        self.log_scroll = 0
        self.status = f"{kind} 진행 중"
        process = self.proc

        def read_output():
            for line in process.stdout:
                self.mail.put(("line", line.rstrip()))
            process.stdout.close()
            self.mail.put(("done", process.wait()))

        threading.Thread(target=read_output, daemon=True).start()

    def stop(self):
        if self.proc is not None:
            self.stopping = True
            self.status = "중단 요청됨. 부분 로그는 결과 폴더에 남습니다."
            process = self.proc

            def terminate():
                try:
                    if os.name == "nt":
                        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                       creationflags=subprocess.CREATE_NO_WINDOW, timeout=3)
                    if process.poll() is None:
                        process.kill()
                except (OSError, subprocess.TimeoutExpired):
                    if process.poll() is None:
                        process.kill()

            threading.Thread(target=terminate, daemon=False).start()

    def poll(self):
        while not self.mail.empty():
            kind, value = self.mail.get_nowait()
            if kind == "line":
                if self.log_scroll and self.tab != '디버그':
                    self.log_scroll += 1
                self.logs.append(value)
                self.logs = self.logs[-3000:]
                self._log_revision += 1
            else:
                self.status = "작업 중단됨" if self.stopping else (
                    f"{self.kind} 완료" if value == 0 else f"{self.kind} 실패 (종료 코드 {value}). 아래 로그를 확인하세요.")
                self.proc = None
                self.refresh()
                if self.pending_path and self.pending_path.is_file():
                    if self.kind in ("맵 생성", "맵 편집"):
                        self.fields["map"] = str(self.pending_path.relative_to(ROOT))
                    elif self.kind == "에피소드 실행":
                        self.fields["manifest"] = str(self.pending_path.relative_to(ROOT))
                        self.load_result()
                        if self.tab != '디버그':
                            self.tab = "결과"
                if self.kind == "LLM 채점" and self.pending_path:
                    self.pending_path.with_suffix(".judge.log.txt").write_text("\n".join(self.logs), encoding="utf-8")
                self.pending_path = None

    def act(self, action):
        try:
            action()
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            self.status = str(exc)

    def generate(self):
        seed = self.number("seed", 0)
        (ROOT / "map_datas").mkdir(exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        output = ROOT / "map_datas" / f"map_{seed}_{stamp}.json"
        args = ["-m", "mapgen", "--seed", seed, "--agents", self.number("agents"),
                "--puzzles", self.number("puzzles"), "--portals", self.number("portals", 0), "--out", str(output)]
        if self.reveal:
            args.append("--reveal-positions")
        self.start(args, "맵 생성", output)

    def editor(self, blank=False):
        (ROOT / "map_datas").mkdir(exist_ok=True)
        output = ROOT / "map_datas" / ("custom_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ".json")
        args = ["-m", "mapgen.editor", "--out", str(output)]
        if not blank and self.fields["map"].strip():
            source = self.path("map")
            if not source.is_file():
                raise ValueError("선택한 맵 파일이 없습니다.")
            args += ["--load", str(source)]
        self.start(args, "맵 편집", output)

    def run_episode(self):
        if self.policy == "code" and not self.key_ready():
            raise ValueError("프로젝트의 key.txt에 API 키를 입력하세요.")
        output_dir = ROOT / "benchmark_runs"
        output_dir.mkdir(exist_ok=True)
        output = output_dir / (datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ".jsonl")
        args = ["benchmark.py", "--policy", self.policy, "--steps", self.number("steps"), "--out", str(output)]
        if self.debug:
            args.append('--debug')
        if self.policy == "code":
            if not self.fields["model"].strip() or not self.fields["url"].strip():
                raise ValueError("모델과 API 주소를 입력하세요.")
            args += ["--model", self.fields["model"].strip(), "--base-url", self.fields["url"].strip()]
        if self.environment == "sequence_rooms":
            pads, presses = self.number("pads"), self.number("presses")
            if not 1 <= int(presses) <= int(pads) <= 5:
                raise ValueError("각 방의 입력 수 ≤ 번호판 수 ≤ 5여야 합니다.")
            args += ["--environment", "sequence_rooms", "--sequence-seed", self.number("seed", 0),
                     "--pads-per-room", pads, "--presses-per-room", presses]
            if self.fields["resets"].strip():
                args += ["--max-resets", self.number("resets", 0)]
        elif self.fields["map"].strip():
            source = self.path("map")
            if not source.is_file():
                raise ValueError("선택한 맵 파일이 없습니다.")
            args += ["--map-file", str(source)]
        self.start(args, "에피소드 실행", output)
        if self.debug:
            self.switch('디버그')
        if self.auto_view:
            self.open_viewer(output, live=True)

    def open_viewer(self, path=None, live=False):
        source = Path(path) if path is not None else self.path("manifest")
        if not live and (not self.fields["manifest"].strip() or not source.is_file()):
            raise ValueError("결과 JSONL을 먼저 선택하세요.")
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        args = [sys.executable, str(ROOT / "viewer.py"), str(source)]
        if live:
            args.append("--live")
        self.viewers = [p for p in self.viewers if p.poll() is None]
        self.viewers.append(subprocess.Popen(args, cwd=ROOT, creationflags=flags))

    def judge(self, baseline=False):
        source = self.path("manifest")
        if not self.fields["manifest"].strip() or not source.is_file():
            raise ValueError("채점할 결과 JSONL을 선택하세요.")
        if not self.key_ready():
            raise ValueError("프로젝트의 key.txt에 API 키를 입력하세요.")
        args = ["maci_judge.py", str(source), "--judge-model", self.fields["judge"].strip(),
                "--base-url", self.fields["url"].strip()]
        if self.fields["turns"].strip():
            args += ["--max-turns", self.number("turns")]
        if self.fields["agent"].strip():
            args += ["--agent", self.fields["agent"].strip()]
        if baseline:
            args.append("--set-baseline")
        self.start(args, "LLM 채점", source)

    def load_result(self):
        source = self.path("manifest")
        self.detail_scroll = 0
        score_path = source.with_suffix(".score.json")
        lines = []
        if score_path.is_file():
            score = json.loads(score_path.read_text(encoding="utf-8"))
            team = score["team"]
            lines += [f"총점: {score['total']}   단체: {team['score']}",
                      f"클리어: {team['cleared']}   클리어 step: {team['clear_step']}   헛된 시도: {team['failed_attempts']}"]
            for agent, data in score["agents"].items():
                lines.append(f"에이전트 {agent}: {data['score']}점")
                checks = score.get('code_checks', {}).get(agent)
                if checks:
                    lines.append(f"  컴파일 검사 {checks['compile_attempts']}회 (실패 {checks['compile_failures']}) / 실행 {checks['execution_attempts']}회 (실패 {checks['execution_failures']})")
                lines += [f"  step {item['step']}: {item['reason']} / {item['target']} / {item['points']}점" for item in data["items"]]
        else:
            lines.append("완료 점수 파일이 없습니다. 중단되었거나 실행 중인 결과일 수 있습니다.")
        lines.append("── 행동 / 메시지 / 이벤트 (자세한 생성 코드는 JSONL 파일에 기록) ──")
        with source.open(encoding="utf-8") as file:
            for line in file:
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    lines.append("불완전한 로그 행")
                    continue
                lines.append(f"step {record['step']}  cleared={record.get('cleared')}")
                for agent in record.get("agents", []):
                    lines.append(f"  {agent['agent']} @ {agent['position']}: " + json.dumps(agent['decision'].get('final_action'), ensure_ascii=False))
                    if agent['decision'].get('policy_error'):
                        lines.append("  정책 오류: " + agent['decision']['policy_error'])
                    if agent['decision'].get('recovery'):
                        lines.append("  코드 복구: " + json.dumps(agent['decision']['recovery'], ensure_ascii=False))
                for name in ("messages", "events"):
                    lines += [f"  {name}: " + json.dumps(item, ensure_ascii=False) for item in record.get(name, [])]
        self.detail = lines

    def text(self, value, x, y, font=None, color=TEXT, width=None):
        font = font or self.font
        value = str(value).replace("\n", " ")
        if width:
            while value and font.size(value)[0] > width:
                value = value[:-1]
        self.screen.blit(font.render(value, True, color), (x, y))

    def button(self, label, rect, action, selected=False):
        rect = pygame.Rect(rect)
        pygame.draw.rect(self.screen, ACCENT if selected else PANEL, rect, border_radius=7)
        self.text(label, rect.x + 12, rect.y + 9, width=rect.width - 20)
        self.widgets.append((rect, lambda: self.act(action)))

    def field(self, name, label, x, y, width=260):
        self.text(label, x, y, self.small, DIM)
        rect = pygame.Rect(x, y + 24, width, 36)
        pygame.draw.rect(self.screen, PANEL, rect, border_radius=5)
        if self.focus == name:
            pygame.draw.rect(self.screen, ACCENT, rect, 2, border_radius=5)
        value = self.fields[name]
        while value and self.font.size(value)[0] > width - 20:
            value = value[1:]
        self.text(value + ("|" if self.focus == name else ""), x + 8, y + 31, width=width - 12)
        self.widgets.append((rect, lambda: setattr(self, "focus", name)))

    def select_map(self, path):
        self.fields["map"] = str(path.relative_to(ROOT)) if path else ""
        self.status = "기본 압력판 맵 선택" if path is None else f"맵 선택: {path.name}"

    def select_run(self, path):
        self.fields["manifest"] = str(path.relative_to(ROOT))
        self.load_result()

    def draw(self):
        self.screen.fill(BG)
        self.widgets = []
        self.text("MACI 실험 실행 도구", 24, 18, self.title)
        self.text("키 파일: " + ("준비됨" if self.key_ready() else "key.txt 확인 필요"), 880, 28, self.small, DIM)
        for i, tab in enumerate(("맵", "실행", "결과", "LLM 채점", "디버그")):
            self.button(tab, (24 + i * 154, 66, 142, 40), lambda t=tab: self.switch(t), self.tab == tab)
        self.button("목록 새로고침", (820, 66, 165, 40), self.refresh)
        self.button("작업 중단", (997, 66, 155, 40), self.stop)
        if self.tab == "맵":
            for name, label, x in (("seed", "시드", 24), ("agents", "에이전트 수", 165), ("puzzles", "퍼즐 수", 306), ("portals", "포탈 쌍", 447)):
                self.field(name, label, x, 122, 125)
            self.button("위치 힌트: " + ("켜짐" if self.reveal else "꺼짐"), (595, 146, 190, 36), lambda: setattr(self, "reveal", not self.reveal))
            self.button("무작위 맵 생성·저장", (806, 146, 345, 36), self.generate)
            self.field("map", "맵 파일 경로 (비우면 기본 맵 / 외부 파일의 전체 경로도 가능)", 24, 195, 760)
            self.button("기본 맵 선택", (806, 219, 345, 36), lambda: self.select_map(None))
            self.button("빈 맵 에디터", (24, 269, 240, 40), lambda: self.editor(True))
            self.button("선택 맵 편집·테스트", (280, 269, 290, 40), self.editor)
            self.text("에디터: A 배치 / L 연결 / G 목표 / P 테스트 / Ctrl+S 저장. 창을 닫으면 돌아옵니다.", 24, 322, self.small, DIM)
            self.text("저장된 맵 (목록 위에서 휠로 스크롤)", 24, 350, self.small)
            for i, path in enumerate(self.maps[self.list_scroll:self.list_scroll + 5]):
                self.button(path.name, (24, 378 + i * 35, 1128, 30), lambda p=path: self.select_map(p), self.fields['map'] == str(path.relative_to(ROOT)))
        elif self.tab == "실행":
            self.button("일반 맵 / 압력판", (24, 122, 360, 36), lambda: setattr(self, 'environment', 'map'), self.environment == 'map')
            self.button("두 방 순서 퍼즐", (400, 122, 360, 36), lambda: setattr(self, 'environment', 'sequence_rooms'), self.environment == 'sequence_rooms')
            self.text("선택 환경: " + ("두 방 순서 퍼즐" if self.environment == 'sequence_rooms' else (self.fields['map'] or "기본 맵 (압력판 2개)")), 24, 174, width=1110)
            for i, (policy, label) in enumerate((("tooluse", "규칙 기반 (무료)"), ("code", "LLM 코드 정책"), ("random", "무작위 이동"), ("noop", "행동 없음"))):
                self.button(label, (24 + i * 280, 208, 265, 40), lambda p=policy: setattr(self, 'policy', p), self.policy == policy)
            self.field("steps", "최대 step / 두 방 퍼즐 턴 제한", 24, 268, 265)
            self.field("model", "에이전트 모델", 310, 268, 842)
            if self.environment == 'sequence_rooms':
                self.field('seed', '퍼즐 시드', 24, 350, 220)
                self.field('pads', '방마다 번호판 (1~5)', 265, 350, 240)
                self.field('presses', '방마다 정답 입력 수', 526, 350, 260)
                self.field('resets', '허용 리셋 (빈칸: 무제한)', 807, 350, 345)
            else:
                self.text('맵은 맵 탭에서 선택합니다. 실행 중 별도 창에서 에이전트 이동을 볼 수 있습니다.', 24, 371, self.small, DIM)
            self.field("url", "OpenAI 호환 API 주소", 24, 430, 736)
            self.button("에피소드 실행", (790, 454, 362, 40), self.run_episode)
            self.button('이동 창 자동 열기: ' + ('켜짐' if self.auto_view else '꺼짐'), (790, 506, 362, 36), lambda: setattr(self, 'auto_view', not self.auto_view))
            self.button('디버깅: ' + ('켜짐' if self.debug else '꺼짐'), (24, 506, 240, 36), lambda: setattr(self, 'debug', not self.debug))
            self.text("결과 자동 저장 · 이동 창에서 재생 속도 / 일시정지 / 이전·다음 step 조절", 24, 566, self.small, DIM)
        elif self.tab == "결과":
            self.field("manifest", "결과 JSONL 경로", 24, 122, 736)
            self.button("결과 불러오기", (780, 146, 177, 36), self.load_result)
            self.button("이동 다시 보기", (972, 146, 180, 36), self.open_viewer)
            for i, path in enumerate(self.runs[self.list_scroll:self.list_scroll + 8]):
                self.button(path.name, (24, 205 + i * 39, 340, 34), lambda p=path: self.select_run(p))
            pygame.draw.rect(self.screen, PANEL, (382, 201, 770, 353), border_radius=7)
            for i, line in enumerate(self.detail[self.detail_scroll:self.detail_scroll + 15]):
                self.text(line, 395, 210 + i * 22, self.small, width=745)
            self.text("휠: 목록 / 결과 내용 스크롤. 긴 코드와 전체 내용은 저장된 JSONL에서 확인하세요.", 24, 566, self.small, DIM)
        elif self.tab == '디버그':
            self.text('실시간 로그 · 최신 내용을 자동으로 따라갑니다. 휠로 이전 내용을 확인하세요.', 24, 128, self.small, DIM)
            self.button('최신 로그로 이동', (930, 120, 222, 36), lambda: setattr(self, 'log_scroll', 0))
            self.text(self.status, 24, 163, self.small, ACCENT, 1128)
            pygame.draw.rect(self.screen, (10, 15, 23), (24, 196, 1128, 628), border_radius=8)
            if self._debug_cache_revision != self._log_revision:
                wrapped = []
                for line in self.logs:
                    rest = line or ' '
                    while rest:
                        n = min(len(rest), 150)
                        while n > 1 and self.small.size(rest[:n])[0] > 1100:
                            n -= 1
                        wrapped.append(rest[:n])
                        rest = rest[n:]
                if self.log_scroll:
                    self.log_scroll = max(0, self.log_scroll + len(wrapped)-len(self._debug_lines))
                self._debug_lines = wrapped
                self._debug_cache_revision = self._log_revision
            end = max(0, len(self._debug_lines)-self.log_scroll)
            for i, line in enumerate(self._debug_lines[max(0, end-28):end]):
                self.text(line, 36, 208+i*22, self.small, width=1100)
            pygame.display.flip()
            return
        else:
            self.field("manifest", "채점할 JSONL (결과 탭에서 선택 가능)", 24, 122, 1128)
            self.field("judge", "판정 모델", 24, 210, 550)
            self.field("turns", "최대 턴 (비우면 전체)", 605, 210, 260)
            self.field("agent", "에이전트 (비우면 전체)", 888, 210, 264)
            self.field("url", "API 주소", 24, 298, 1128)
            self.button("LLM 채점", (24, 390, 350, 44), self.judge)
            self.button("100점 기준 등록 + 채점", (394, 390, 400, 44), lambda: self.judge(True))
            self.text("기준 등록: solar-pro4로 실행한 결과를 선택하세요. 같은 턴 범위로 비교하세요.", 24, 456, self.small, DIM)
            self.text("채점 출력은 결과 파일 옆 .judge.log.txt에 저장됩니다. API 키는 key.txt를 사용합니다.", 24, 486, self.small, DIM)
        self.text(self.status, 24, 600, self.small, ACCENT, 1128)
        pygame.draw.rect(self.screen, (10, 15, 23), (24, 631, 1128, 193), border_radius=8)
        end = max(0, len(self.logs) - self.log_scroll)
        for i, line in enumerate(self.logs[max(0, end - 8):end]):
            self.text(line, 36, 642 + i * 22, self.small, width=1100)
        pygame.display.flip()

    def switch(self, tab):
        self.tab, self.focus, self.list_scroll = tab, None, 0

    def loop(self):
        clock = pygame.time.Clock()
        running = True
        pygame.key.start_text_input()
        while running:
            self.poll()
            self.draw()
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.stop()
                    for process in self.viewers:
                        if process.poll() is None:
                            process.terminate()
                    running = False
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self.focus = None
                    for rect, action in self.widgets:
                        if rect.collidepoint(event.pos):
                            action()
                            break
                elif event.type == pygame.TEXTINPUT and self.focus:
                    self.fields[self.focus] += event.text
                elif event.type == pygame.KEYDOWN and self.focus:
                    if event.key == pygame.K_BACKSPACE:
                        self.fields[self.focus] = self.fields[self.focus][:-1]
                    elif event.key == pygame.K_a and event.mod & pygame.KMOD_CTRL:
                        self.fields[self.focus] = ""
                    elif event.key in (pygame.K_RETURN, pygame.K_ESCAPE):
                        self.focus = None
                    elif event.key == pygame.K_v and event.mod & pygame.KMOD_CTRL:
                        try:
                            pygame.scrap.init()
                            content = pygame.scrap.get(pygame.SCRAP_TEXT)
                            if content:
                                self.fields[self.focus] += content.decode('utf-8', errors='replace').rstrip('\x00').replace('\r', '').replace('\n', '')
                        except pygame.error:
                            self.status = "붙여넣기에 실패했습니다. 직접 입력하세요."
                elif event.type == pygame.MOUSEWHEEL:
                    x, y = pygame.mouse.get_pos()
                    if self.tab == '디버그':
                        self.log_scroll = min(max(0, len(self._debug_lines)-28), max(0, self.log_scroll-event.y*3))
                    elif y >= 631:
                        self.log_scroll = min(max(0, len(self.logs) - 8), max(0, self.log_scroll - event.y * 3))
                    elif self.tab == "결과" and x >= 382:
                        self.detail_scroll = min(max(0, len(self.detail) - 15), max(0, self.detail_scroll - event.y * 3))
                    else:
                        count = len(self.runs) if self.tab == "결과" else len(self.maps)
                        visible = 8 if self.tab == "결과" else 5
                        self.list_scroll = min(max(0, count - visible), max(0, self.list_scroll - event.y))
            clock.tick(30)
        pygame.quit()


if __name__ == "__main__":
    Launcher().loop()
