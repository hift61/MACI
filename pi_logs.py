"""실행 로그를 보는 별도 앱 - 라즈베리파이(원격)와 이 컴퓨터(로컬) 모두.

    python pi_logs.py                      # 원격(라즈베리파이)
    python pi_logs.py --local              # 로컬 benchmark_runs
    python pi_logs.py --local D:/runs      # 다른 로컬 폴더
    python pi_logs.py --host jikun@100.105.194.90 --remote-dir ~/MACI/benchmark_runs

창 위쪽의 '원본' 버튼으로 원격/로컬을 바꿀 수 있습니다. 로컬 모드에서는 내려받기 없이 파일을 바로 열고,
진행 중인 실행도 그 파일을 viewer.py --live로 바로 따라봅니다.

SSH(키 로그인)로 원격 benchmark_runs 아래의 실행(manifest .jsonl)을 모두 찾아 보여 줍니다(하위 폴더 포함).
- 목록: 진행 중 / 클리어 / 실패 / 중단, 마지막 step, 모델, 총점
- 선택한 실행: 요약과 콘솔 로그(.log) 끝부분
- 가져오기: 그 실행의 파일을 benchmark_runs/pi/<원격 경로>로 내려받음 (대화 이력 파일은 크기 때문에 선택)
- 이동 다시 보기: 내려받은 뒤 viewer.py로 열기
- 실시간 따라보기: 진행 중인 실행의 새 step만 계속 이어 받아 viewer.py --live로 보기
- LLM 출력 평가: 대화 이력의 LLM 응답 하나하나를 사람이 0~10점과 메모로 평가 (llm_outputs.py,
  <manifest>.llm_ratings.<평가자>.json에 저장). 원격 실행은 대화 이력까지 내려받아 로컬 사본 옆에 저장
원격 작업은 모두 원격의 python3에 아래 REMOTE_HELPER 스크립트를 보내 처리합니다(원격에 따로 설치할 것 없음).
"""
from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tarfile
import threading
import time

import llm_outputs

ROOT = Path(__file__).resolve().parent
LOCAL_DIR = ROOT / "benchmark_runs" / "pi"
DEFAULT_HOST = "jikun@100.105.194.90"
DEFAULT_REMOTE_DIR = "~/MACI/benchmark_runs"
LIVE_SECONDS = 120     # 마지막 수정이 이 시간 안이면 '진행 중'으로 봄
FOLLOW_SECONDS = 3.0   # 실시간 따라보기에서 새 step을 받아 오는 간격
REFRESH_SECONDS = 20.0  # 자동 새로고침 간격

# 원격 python3에 표준입력으로 보내 실행하는 도우미. 인자: <동작> <루트> [실행 경로] [...]
REMOTE_HELPER = r'''
import io, json, os, sys, tarfile, time
SIDE = (".debug.jsonl", ".code_checks.jsonl", ".context_archive.jsonl", ".context_compressions.jsonl",
        ".observations.jsonl")
CONTEXT = (".context_archive.jsonl", ".context.json", ".working_context.json", ".context_compressions.jsonl")
action, root = sys.argv[1], os.path.realpath(os.path.expanduser(sys.argv[2]))

def inside(rel):
    path = os.path.realpath(os.path.join(root, rel))
    if not path.startswith(root + os.sep):
        raise SystemExit("path outside root")
    return path

def last_record(path, size):
    with open(path, "rb") as f:
        for back in (200000, 2000000, size):
            f.seek(max(0, size - back))
            for line in reversed(f.read().split(b"\n")):
                try:
                    return json.loads(line)
                except Exception:
                    continue
    return None

if action == "list":
    runs = []
    for dirpath, _, files in os.walk(root):
        for name in files:
            if not name.endswith(".jsonl") or name.endswith(SIDE):
                continue
            path = os.path.join(dirpath, name)
            st = os.stat(path)
            info = {"path": os.path.relpath(path, root), "size": st.st_size, "mtime": st.st_mtime, "done": False}
            last = last_record(path, st.st_size) if st.st_size else None
            if last:
                agents = last.get("agents") or [{}]
                info.update(step=last.get("step"), steps=last.get("configured_steps"), cleared=last.get("cleared"),
                            model=agents[0].get("model"), environment=last.get("environment"),
                            controller=last.get("controller"))
            score = path[:-len(".jsonl")] + ".score.json"
            if os.path.exists(score):
                try:
                    with open(score, encoding="utf-8") as f:
                        s = json.load(f)
                    info.update(done=True, total=s.get("total"), cleared=s["team"]["cleared"],
                                clear_step=s["team"]["clear_step"], stopped=s.get("stopped"))
                except (ValueError, KeyError, OSError):
                    info["score_error"] = True  # 깨진 점수 파일 하나 때문에 목록 전체가 실패하지 않게
            runs.append(info)
    print(json.dumps({"root": root, "now": time.time(), "runs": runs}))
elif action == "tail":
    path = inside(sys.argv[3])[:-len(".jsonl")] + ".log"
    lines = []
    if os.path.exists(path):
        with open(path, "rb") as f:
            f.seek(max(0, os.path.getsize(path) - 400000))
            lines = f.read().decode("utf-8", "replace").splitlines()[-int(sys.argv[4]):]
    print(json.dumps(lines))
elif action == "tar":
    path = inside(sys.argv[3])
    stem, folder = os.path.basename(path)[:-len(".jsonl")], os.path.dirname(path)
    with_context = sys.argv[4] == "1"
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name in sorted(os.listdir(folder)):
            if name.startswith(stem + ".") and (with_context or not name.endswith(CONTEXT)):
                archive.add(os.path.join(folder, name), arcname=name)
    sys.stdout.buffer.write(buffer.getvalue())
elif action == "read":
    path = inside(sys.argv[3])
    with open(path, "rb") as f:
        f.seek(int(sys.argv[4]))
        sys.stdout.buffer.write(f.read())
'''


def local_runner(args: list[str]) -> bytes:
    """REMOTE_HELPER를 이 컴퓨터의 python으로 실행 (로컬 모드, 테스트)."""
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    result = subprocess.run([sys.executable, "-", *args], input=REMOTE_HELPER.encode("utf-8"), capture_output=True,
                            timeout=180, creationflags=flags)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", "replace").strip()[-300:] or f"exit {result.returncode}")
    return result.stdout


class PiClient:
    """원격 도우미 호출. runner는 테스트에서 바꿔 끼울 수 있게 분리 (기본: ssh)."""

    def __init__(self, host: str, remote_dir: str, runner=None) -> None:
        self.host, self.remote_dir = host, remote_dir
        self.runner = runner or self._ssh

    def _ssh(self, args: list[str]) -> bytes:
        command = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", self.host, "python3", "-", *args]
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        result = subprocess.run(command, input=REMOTE_HELPER.encode("utf-8"), capture_output=True,
                                timeout=180, creationflags=flags)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.decode("utf-8", "replace").strip()[-300:] or f"ssh exit {result.returncode}")
        return result.stdout

    def list_runs(self) -> dict:
        data = json.loads(self.runner(["list", self.remote_dir]))
        data["runs"].sort(key=lambda r: r["mtime"], reverse=True)
        return data

    def tail_log(self, rel: str, lines: int = 40) -> list[str]:
        return json.loads(self.runner(["tail", self.remote_dir, rel, str(lines)]))

    def download(self, rel: str, include_context: bool = False) -> Path:
        """그 실행의 파일들을 LOCAL_DIR/<원격 경로>로 받음. 반환: 로컬 manifest 경로."""
        data = self.runner(["tar", self.remote_dir, rel, "1" if include_context else "0"])
        target = local_path(rel).parent
        target.mkdir(parents=True, exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
            for member in archive.getmembers():
                if member.isfile() and "/" not in member.name and ".." not in member.name:
                    (target / member.name).write_bytes(archive.extractfile(member).read())
        return local_path(rel)

    def append_new(self, rel: str) -> int:
        """진행 중인 실행: 로컬 사본 뒤에 원격에서 새로 쌓인 부분만 붙임. 반환: 받은 바이트 수."""
        path = local_path(rel)
        offset = path.stat().st_size if path.exists() else 0
        data = self.runner(["read", self.remote_dir, rel, str(offset)])
        if data:
            with path.open("ab") as file:
                file.write(data)
        return len(data)


class LocalClient(PiClient):
    """로컬 폴더용: 목록/로그는 같은 도우미로 읽고, 파일은 내려받지 않고 그 자리의 파일을 씀."""

    def __init__(self, folder: str, runner=None) -> None:
        super().__init__("local", folder, runner or local_runner)
        self.folder = Path(os.path.expanduser(folder)).resolve()

    def path(self, rel: str) -> Path:
        path = (self.folder / rel).resolve()
        if self.folder not in path.parents:
            raise ValueError("path escapes the local folder")
        return path

    def download(self, rel: str, include_context: bool = False) -> Path:
        return self.path(rel)

    def append_new(self, rel: str) -> int:
        return 0  # 로컬 파일은 viewer --live가 직접 따라 읽음


def local_path(rel: str) -> Path:
    path = (LOCAL_DIR / rel).resolve()
    if LOCAL_DIR.resolve() not in path.parents:
        raise ValueError("remote path escapes the local folder")
    return path


def run_status(run: dict, now: float) -> str:
    if run.get("done"):
        if run.get("stopped"):
            return "중단"
        return "클리어" if run.get("cleared") else "실패"
    return "진행 중" if now - run["mtime"] <= LIVE_SECONDS else "멈춤"


STATUS_COLORS = {"진행 중": (73, 166, 228), "클리어": (96, 208, 138), "실패": (218, 112, 95),
                 "중단": (232, 170, 92), "멈춤": (154, 171, 193)}


def summary_lines(run: dict, now: float) -> list[str]:
    status = run_status(run, now)
    age = max(0, int(now - run["mtime"]))
    age_text = (f"{age // 86400}일 {age % 86400 // 3600}시간" if age >= 86400 else
                f"{age // 3600}시간 {age % 3600 // 60}분" if age >= 3600 else f"{age // 60}분 {age % 60}초")
    lines = [f"{run['path']}",
             f"상태: {status}   마지막 기록: {age_text} 전   크기: {run['size'] / 1e6:.1f}MB",
             f"모델: {run.get('model')}   환경: {run.get('environment')}   조종: {run.get('controller') or 'decentralized'}",
             f"step: {run.get('step')} / {run.get('steps')}"]
    if run.get("done"):
        lines.append(f"클리어: {run.get('cleared')} (step {run.get('clear_step')})   총점: {run.get('total')}")
    if run.get("stopped"):
        lines.append(f"중단 사유: {run['stopped']}")
    return lines


class PiLogsApp:
    def __init__(self, host: str, remote_dir: str, runner=None, local_dir: str | None = None,
                 source: str = "remote") -> None:
        import pygame
        self.pygame = pygame
        pygame.init()
        self.screen = pygame.display.set_mode((1180, 760))
        pygame.display.set_caption("MACI 실행 로그 (원격/로컬)")
        font = pygame.font.match_font("malgungothic,nanumgothic,applegothic")
        self.font, self.small, self.title = (pygame.font.Font(font, 18), pygame.font.Font(font, 14),
                                             pygame.font.Font(font, 26))
        self.fields = {"host": host, "remote": remote_dir, "local": local_dir or str(ROOT / "benchmark_runs"),
                       "rater": "", "comment": ""}
        # LLM 출력 평가 화면 상태: {"path", "outputs", "index", "ratings", "filter", "lines", "scroll"}
        self.review: dict | None = None
        self.runner = runner
        self.source = source  # "remote" 또는 "local"
        self.focus = None
        self.runs: list[dict] = []
        self.now = time.time()
        self.selected: str | None = None
        self.log_lines: list[str] = []
        self.list_scroll = 0
        self.log_scroll = 0
        self.include_context = False
        self.auto_refresh = True
        self.following: str | None = None
        self.status = "새로고침을 누르면 원격 실행 목록을 불러옵니다."
        self.jobs: queue.Queue = queue.Queue()
        self.busy = 0
        self.last_refresh = 0.0
        self.last_follow = 0.0
        self.viewers: list[subprocess.Popen] = []
        self.widgets = []

    @property
    def client(self) -> PiClient:
        if self.source == "local":
            return LocalClient(self.fields["local"].strip(), self.runner)
        return PiClient(self.fields["host"].strip(), self.fields["remote"].strip(), self.runner)

    def toggle_source(self) -> None:
        self.source = "local" if self.source == "remote" else "remote"
        self.runs, self.selected, self.log_lines, self.following = [], None, [], None
        self.refresh()

    # ---- 원격 작업은 GUI가 멈추지 않게 백그라운드 스레드에서
    def background(self, label: str, work, done=None) -> None:
        self.busy += 1
        self.status = label + "…"

        def run():
            try:
                result, error = work(), None
            except Exception as exc:  # 연결 실패 등은 상태 줄에 보여 줌
                result, error = None, f"{type(exc).__name__}: {exc}"
            self.jobs.put((label, result, error, done))
        threading.Thread(target=run, daemon=True).start()

    def poll(self) -> None:
        while True:
            try:
                label, result, error, done = self.jobs.get_nowait()
            except queue.Empty:
                break
            self.busy -= 1
            if error:
                self.status = f"{label} 실패: {error}"
            else:
                self.status = f"{label} 완료"
                if done:
                    done(result)
        now = time.time()
        if self.auto_refresh and not self.busy and now - self.last_refresh >= REFRESH_SECONDS and self.last_refresh:
            self.refresh()
        if self.following and not self.busy and now - self.last_follow >= FOLLOW_SECONDS:
            self.last_follow = now
            rel = self.following
            self.background("새 step 받기", lambda: self.client.append_new(rel))

    def refresh(self) -> None:
        self.last_refresh = time.time()

        def done(data):
            self.runs, self.now = data["runs"], data["now"]
            self.status = f"{'로컬' if self.source == 'local' else '원격'} 실행 {len(self.runs)}개 ({data['root']})"
            followed = next((r for r in self.runs if r["path"] == self.following), None)
            if followed is not None and followed.get("done"):
                # 끝난 실행은 점수 파일까지 한 번 더 받아 오고 따라보기를 멈춤
                rel, self.following = self.following, None
                self.background("완료된 실행 마무리 받기", lambda: self.client.download(rel, False))
            if self.selected:
                self.load_log()
        self.background("목록 새로고침", self.client.list_runs, done)

    def select(self, rel: str) -> None:
        self.selected, self.log_lines, self.log_scroll = rel, [], 0
        self.load_log()

    def load_log(self) -> None:
        rel = self.selected
        self.background("로그 불러오기", lambda: self.client.tail_log(rel, 200),
                        lambda lines: setattr(self, "log_lines", lines))

    def download(self, open_viewer: bool = False) -> None:
        if not self.selected:
            self.status = "실행을 먼저 고르세요."
            return
        if self.source == "local":
            path = self.client.download(self.selected)
            if open_viewer:
                self.open_viewer(path)
            self.status = f"로컬 파일: {path}"
            return
        rel, context = self.selected, self.include_context

        def done(path):
            self.status = f"가져오기 완료: {path}"
            if open_viewer:
                self.open_viewer(path)
        self.background("가져오기", lambda: self.client.download(rel, context), done)

    def follow(self) -> None:
        if self.following:
            self.following = None
            self.status = "실시간 따라보기를 멈췄습니다."
            return
        if not self.selected:
            self.status = "실행을 먼저 고르세요."
            return
        rel = self.selected
        if self.source == "local":  # 로컬 파일은 viewer --live가 직접 따라 읽음
            self.open_viewer(self.client.download(rel), live=True)
            self.status = "로컬 실행을 이동 창에서 실시간으로 따라봅니다."
            return

        def done(path):
            self.following, self.last_follow = rel, time.time()
            self.open_viewer(path, live=True)
        self.background("실시간 따라보기 준비", lambda: self.client.download(rel, False), done)

    # ---- LLM 출력 평가
    def open_review(self) -> None:
        if not self.selected:
            self.status = "실행을 먼저 고르세요."
            return
        if not self.fields["rater"].strip():
            self.status = "평가자 이름을 먼저 입력하세요 (아래 칸)."
            self.focus = "rater"
            return
        rel = self.selected

        def load(path):
            outputs = llm_outputs.extract_outputs(path)
            if not outputs:
                raise ValueError("이 실행에는 LLM 출력이 없습니다 (규칙 기반 정책 등).")
            return path, outputs

        def done(result):
            path, outputs = result
            self.review = {"path": path, "outputs": outputs, "index": 0, "filter": None, "scroll": 0,
                           "ratings": llm_outputs.load_ratings(path, self.fields["rater"])}
            self.next_unrated(start=-1)
            self.status = f"LLM 출력 {len(outputs)}개를 불러왔습니다. 숫자 키 0~9로 평가, ←/→ 이동."
        if self.source == "local":
            self.background("LLM 출력 불러오기", lambda: load(self.client.download(rel)), done)
        else:
            self.background("대화 이력 포함 가져오기", lambda: load(self.client.download(rel, True)), done)

    def review_items(self) -> list[dict]:
        outputs = self.review["outputs"]
        agent = self.review["filter"]
        return [o for o in outputs if agent is None or o["agent"] == agent]

    def current_output(self) -> dict | None:
        items = self.review_items() if self.review else []
        return items[min(self.review["index"], len(items) - 1)] if items else None

    def move_review(self, delta: int) -> None:
        items = self.review_items()
        if items:
            self.review["index"] = min(len(items) - 1, max(0, self.review["index"] + delta))
            self._show_output()

    def next_unrated(self, start: int | None = None) -> None:
        items = self.review_items()
        begin = self.review["index"] if start is None else start
        for offset in range(1, len(items) + 1):
            index = (begin + offset) % len(items)
            if items[index]["id"] not in self.review["ratings"]:
                self.review["index"] = index
                self._show_output()
                return
        self._show_output()
        self.status = "모든 출력을 평가했습니다."

    def set_filter(self, agent: str | None) -> None:
        self.review["filter"], self.review["index"] = agent, 0
        self._show_output()

    def _show_output(self) -> None:
        output = self.current_output()
        if output is None:
            self.review["lines"] = ["(이 에이전트의 출력이 없습니다)"]
            return
        rating = self.review["ratings"].get(output["id"])
        self.fields["comment"] = rating.get("comment", "") if rating else ""
        text = (llm_outputs.RUBRIC + "\n\n=== LLM 출력 ===\n" + output["output"]
                + ("\n\n=== 하네스 응답 ===\n" + "\n".join(output["result"]) if output["result"] else "")
                + "\n\n=== 이 출력 직전에 받은 입력 (앞부분) ===\n" + output["input"][:4000])
        self.review["lines"] = self.wrap(text, 676)
        self.review["scroll"] = 0

    def rate(self, score) -> None:
        output = self.current_output()
        if output is None:
            return
        llm_outputs.save_rating(self.review["path"], self.fields["rater"], output, score, self.fields["comment"])
        self.review["ratings"] = llm_outputs.load_ratings(self.review["path"], self.fields["rater"])
        if score is not None:
            self.next_unrated()

    def wrap(self, value, width) -> list[str]:
        lines = []
        for paragraph in str(value).split("\n"):
            rest = paragraph or " "
            while rest:
                n = min(len(rest), 220)
                while n > 1 and self.small.size(rest[:n])[0] > width:
                    n -= 1
                lines.append(rest[:n])
                rest = rest[n:]
        return lines

    def _draw_review(self, x: int) -> None:
        pygame = self.pygame
        review = self.review
        output = self.current_output()
        items = self.review_items()
        self.button("평가 닫기", (x, 126, 120, 32), lambda: setattr(self, "review", None))
        for i, (label, agent) in enumerate((("전체", None), ("A", "A"), ("B", "B"))):
            self.button(label, (x + 132 + i * 66, 126, 60, 32), lambda a=agent: self.set_filter(a), review["filter"] == agent)
        self.text(llm_outputs.summary(review["outputs"], review["ratings"]), x + 340, 134, width=356)
        if output is not None:
            rating = review["ratings"].get(output["id"])
            self.text(f"{review['index'] + 1}/{len(items)}   에이전트 {output['agent']}   #{output['index']}   "
                      f"step 약 {output['step']}   도구: {', '.join(t for t in output['tools'] if t) or '없음'}   "
                      f"내 점수: {'-' if rating is None else rating['score']}", x, 166, self.font, width=696)
        pygame.draw.rect(self.screen, (10, 15, 23), (x, 192, 696, 400), border_radius=8)
        for i, line in enumerate(review["lines"][review["scroll"]:review["scroll"] + 19]):
            self.text(line, x + 10, 198 + i * 20, width=676)
        mine = review["ratings"].get(output["id"], {}).get("score") if output else None
        for score in range(11):
            self.button(str(score), (x + score * 56, 600, 50, 32), lambda v=score: self.rate(v), mine == score)
        self.button("지우기", (x + 616, 600, 80, 32), lambda: self.rate(None))
        self.button("◀ 이전", (x, 640, 100, 32), lambda: self.move_review(-1))
        self.button("다음 ▶", (x + 108, 640, 100, 32), lambda: self.move_review(1))
        self.button("다음 미평가", (x + 216, 640, 130, 32), self.next_unrated)
        self.field("comment", "메모 (점수를 누르면 함께 저장)", x + 356, 632, 340)

    def open_viewer(self, path: Path, live: bool = False) -> None:
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        args = [sys.executable, str(ROOT / "viewer.py"), str(path)] + (["--live"] if live else [])
        self.viewers = [p for p in self.viewers if p.poll() is None]
        self.viewers.append(subprocess.Popen(args, cwd=ROOT, creationflags=flags))

    # ---- 그리기
    def text(self, value, x, y, font=None, color=(227, 235, 246), width=None) -> None:
        font = font or self.small
        value = str(value).replace("\n", " ")
        if width:
            while value and font.size(value)[0] > width:
                value = value[:-1]
        self.screen.blit(font.render(value, True, color), (x, y))

    def button(self, label, rect, action, selected=False) -> None:
        rect = self.pygame.Rect(rect)
        self.pygame.draw.rect(self.screen, (73, 166, 228) if selected else (29, 37, 51), rect, border_radius=7)
        self.text(label, rect.x + 10, rect.y + 8, self.font, width=rect.width - 16)
        self.widgets.append((rect, action))

    def field(self, name, label, x, y, width) -> None:
        self.text(label, x, y, color=(154, 171, 193))
        rect = self.pygame.Rect(x, y + 20, width, 34)
        self.pygame.draw.rect(self.screen, (29, 37, 51), rect, border_radius=5)
        if self.focus == name:
            self.pygame.draw.rect(self.screen, (73, 166, 228), rect, 2, border_radius=5)
        self.text(self.fields[name] + ("|" if self.focus == name else ""), x + 8, y + 27, self.font, width=width - 14)
        self.widgets.append((rect, lambda: setattr(self, "focus", name)))

    def draw(self) -> None:
        pygame = self.pygame
        self.screen.fill((18, 23, 33))
        self.widgets = []
        self.text("실행 로그", 24, 14, self.title)
        self.button("원본: " + ("로컬" if self.source == "local" else "원격"), (160, 14, 150, 34), self.toggle_source,
                    self.source == "local")
        if self.source == "local":
            self.field("local", "로컬 로그 폴더", 24, 56, 646)
        else:
            self.field("host", "SSH 주소", 24, 56, 300)
            self.field("remote", "원격 로그 폴더", 340, 56, 330)
        self.button("새로고침", (690, 76, 120, 36), self.refresh)
        self.button("자동 새로고침: " + ("켬" if self.auto_refresh else "끔"), (822, 76, 200, 36),
                    lambda: setattr(self, "auto_refresh", not self.auto_refresh), self.auto_refresh)
        self.text("작업 중" if self.busy else "", 1040, 86, color=(232, 170, 92))
        # 목록
        pygame.draw.rect(self.screen, (29, 37, 51), (24, 126, 420, 590), border_radius=8)
        visible = self.runs[self.list_scroll:self.list_scroll + 21]
        for i, run in enumerate(visible):
            status = run_status(run, self.now)
            rect = (30, 132 + i * 28, 408, 26)
            if run["path"] == self.selected:
                pygame.draw.rect(self.screen, (44, 58, 80), rect, border_radius=5)
            self.text(status, 36, 136 + i * 28, color=STATUS_COLORS[status])
            self.text(run["path"], 100, 136 + i * 28, width=270)
            self.text(f"{run.get('step')}/{run.get('steps')}", 378, 136 + i * 28, color=(154, 171, 193), width=60)
            self.widgets.append((pygame.Rect(rect), lambda p=run["path"]: self.select(p)))
        if not self.runs:
            self.text("목록이 비어 있습니다.", 40, 140, color=(154, 171, 193))
        # 선택한 실행 (또는 LLM 출력 평가 화면)
        x = 460
        if self.review is not None:
            self._draw_review(x)
            self.text(self.status, 24, 728, color=(73, 166, 228), width=1130)
            pygame.display.flip()
            return
        run = next((r for r in self.runs if r["path"] == self.selected), None)
        if run:
            for i, line in enumerate(summary_lines(run, self.now)):
                self.text(line, x, 130 + i * 20, width=700)
        self.button("로그 새로고침", (x, 252, 150, 34), self.load_log)
        if self.source == "remote":
            self.button("가져오기", (x + 160, 252, 120, 34), lambda: self.download(False))
        self.button("이동 다시 보기", (x + 290, 252, 160, 34), lambda: self.download(True))
        self.button("실시간 따라보기" + (" 끄기" if self.following else ""), (x + 460, 252, 200, 34), self.follow,
                    bool(self.following))
        if self.source == "remote":
            self.button("대화 이력 포함: " + ("예" if self.include_context else "아니오"), (x, 292, 250, 30),
                        lambda: setattr(self, "include_context", not self.include_context), self.include_context)
        self.button("LLM 출력 평가", (x + 260, 292, 170, 30), self.open_review)
        self.field("rater", "평가자", x + 440, 274, 256)
        pygame.draw.rect(self.screen, (10, 15, 23), (x, 330, 696, 386), border_radius=8)
        end = max(0, len(self.log_lines) - self.log_scroll)
        for i, line in enumerate(self.log_lines[max(0, end - 18):end]):
            self.text(line, x + 10, 338 + i * 21, width=676)
        self.text(self.status, 24, 728, color=(73, 166, 228), width=1130)
        pygame.display.flip()

    def handle_click(self, pos) -> None:
        self.focus = None
        for rect, action in self.widgets:
            if rect.collidepoint(pos):
                action()
                return

    def run(self) -> None:
        pygame = self.pygame
        clock = pygame.time.Clock()
        pygame.key.start_text_input()
        self.refresh()
        running = True
        while running:
            self.poll()
            self.draw()
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self.handle_click(event.pos)
                elif event.type == pygame.MOUSEWHEEL:
                    if self.review is not None and pygame.mouse.get_pos()[0] >= 450:
                        self.review["scroll"] = min(max(0, len(self.review["lines"]) - 19),
                                                    max(0, self.review["scroll"] - event.y * 3))
                    elif pygame.mouse.get_pos()[0] < 450:
                        self.list_scroll = min(max(0, len(self.runs) - 21), max(0, self.list_scroll - event.y))
                    else:
                        self.log_scroll = min(max(0, len(self.log_lines) - 18), max(0, self.log_scroll - event.y * 3))
                elif event.type == pygame.TEXTINPUT and self.focus:
                    self.fields[self.focus] += event.text
                elif event.type == pygame.KEYDOWN and not self.focus and self.review is not None:
                    if event.key == pygame.K_LEFT:
                        self.move_review(-1)
                    elif event.key == pygame.K_RIGHT:
                        self.move_review(1)
                    elif pygame.K_0 <= event.key <= pygame.K_9:
                        self.rate(event.key - pygame.K_0)
                elif event.type == pygame.KEYDOWN and self.focus:
                    if event.key == pygame.K_BACKSPACE:
                        self.fields[self.focus] = self.fields[self.focus][:-1]
                    elif event.key in (pygame.K_RETURN, pygame.K_ESCAPE):
                        self.focus = None
            clock.tick(30)
        pygame.quit()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--remote-dir", default=DEFAULT_REMOTE_DIR)
    parser.add_argument("--local", nargs="?", const=str(ROOT / "benchmark_runs"), default=None,
                        help="로컬 폴더를 봄 (폴더를 생략하면 이 프로젝트의 benchmark_runs)")
    args = parser.parse_args()
    PiLogsApp(args.host, args.remote_dir, local_dir=args.local,
              source="local" if args.local else "remote").run()


if __name__ == "__main__":
    main()
