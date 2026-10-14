"""벤치마크 실행을 보는 웹 페이지 (표준 라이브러리만 사용): 실시간 로그 + 로그 평가.

    python pi_status_site.py benchmark_runs/haiku_all_v2 --host 100.105.194.90 --port 8765
    python pi_status_site.py benchmark_runs --host 100.105.194.90 --allow-judge   # 판정기 실행 버튼까지

- / : 폴더 안(하위 폴더 포함) 각 실행의 <맵>.log 마지막 줄들과 진행 step, 끝났으면 score.json의 결과 몇 개 (5초마다 갱신)
- /eval : 로그 평가. 실행을 고르면 판단 시점(바깥 맥락이 바뀐 때, judge_context.py)마다 묶음 내용,
  판정기 점수(judges.json의 '<모델>@anchor'), 사람 점수와 일치도를 보여 주고, 사람이 0~10점과 메모로 채점함
  (<manifest>.anchor_ratings.<채점자>.json). --allow-judge면 '판정기 실행' 버튼으로 판정 모델이 채점 (key.txt, API 비용)
- 안전: 폴더 밖 경로는 거부하고 실행 기록(manifest .jsonl)만 고를 수 있음. 쓰는 파일은 사람 채점 파일과
  판단 시점 묶음 캐시(<manifest>.judge_bundles.json), 판정기 결과(--allow-judge)뿐.
  API 키처럼 보이는 문자열은 가림. Tailscale IP에 붙이면 tailnet 밖에서는 접근할 수 없음
"""
import argparse
import html
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

TAIL_LINES = 40
TAIL_BYTES = 64_000
STEP_RE = re.compile(r"step (\d+)/(\d+): cleared=(\w+)")
SECRET_RE = re.compile(r"(sk-[A-Za-z0-9_\-]{8,}|hf_[A-Za-z0-9]{8,}|Bearer\s+\S+)")
# 실행 기록(manifest)이 아닌 .jsonl
SIDE_SUFFIXES = (".debug.jsonl", ".code_checks.jsonl", ".context_archive.jsonl", ".context_compressions.jsonl",
                 ".observations.jsonl", ".agent_reasoning.jsonl")


def redact(text: str) -> str:
    return SECRET_RE.sub("[redacted]", text)


def tail(path: Path, lines: int = TAIL_LINES) -> list[str]:
    with open(path, "rb") as f:
        f.seek(0, 2)
        f.seek(max(0, f.tell() - TAIL_BYTES))
        text = f.read().decode("utf-8", errors="replace")
    return [redact(line) for line in text.splitlines()[-lines:]]


def score_result(score: Path) -> dict | None:
    if not score.is_file():
        return None
    try:
        data = json.loads(score.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    team = data.get("team", {})
    result = {"cleared": bool(team.get("cleared")), "total": data.get("total"), "clear_step": team.get("clear_step"),
              "failed_attempts": team.get("failed_attempts"), "stopped": data.get("stopped")}
    return {k: v for k, v in result.items() if v is not None}


def map_status(run_dir: Path, log: Path) -> dict:
    name = log.relative_to(run_dir).with_suffix("").as_posix()
    lines = tail(log)
    status = {"map": name, "lines": lines, "step": None, "steps": None, "cleared": False, "done": False}
    for line in reversed(lines):
        m = STEP_RE.search(line)
        if m:
            status.update(step=int(m.group(1)), steps=int(m.group(2)), cleared=m.group(3) == "True")
            break
    result = score_result(log.with_suffix(".score.json"))
    if result is not None:
        cleared = result.pop("cleared", status["cleared"])
        status.update(done=True, cleared=cleared, result=result)
    return status


def all_status(run_dir: Path) -> list[dict]:
    return [map_status(run_dir, p) for p in sorted(run_dir.rglob("*.log"))]


def list_manifests(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.jsonl") if not p.name.endswith(SIDE_SUFFIXES))


def resolve_manifest(root: Path, rel: str) -> Path | None:
    """폴더 안의 실행 기록만. 그 밖의 경로, 부속 파일, 없는 파일은 None"""
    try:
        path = (root / rel).resolve()
        path.relative_to(root)
    except (ValueError, OSError):
        return None
    if path.suffix != ".jsonl" or path.name.endswith(SIDE_SUFFIXES) or not path.is_file():
        return None
    return path


PAGE = """<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>MACI 실행 상태</title>
<style>
:root{--bg:#f7f7f5;--fg:#1d1d1b;--muted:#6b6b66;--card:#fff;--line:#e3e3de;--ok:#1f7a3a;--run:#2d5fb0;--fail:#a33}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--fg:#e8e8e3;--muted:#9a9a93;--card:#20201e;--line:#33332f}}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,sans-serif}
main{max-width:1100px;margin:0 auto;padding:16px}a{color:var(--run)}
h1{font-size:18px;margin:0 0 4px}.sub{color:var(--muted);margin-bottom:16px}
details{background:var(--card);border:1px solid var(--line);border-radius:8px;margin-bottom:8px}
summary{cursor:pointer;padding:10px 12px;display:flex;gap:12px;flex-wrap:wrap;align-items:center}
.name{font-weight:600;min-width:200px}.tag{font-size:12px;padding:1px 8px;border-radius:10px;border:1px solid}
.run{color:var(--run)}.ok{color:var(--ok)}.fail{color:var(--fail)}.meta{color:var(--muted)}
.bar{flex:1;min-width:120px;height:6px;background:var(--line);border-radius:3px;overflow:hidden}
.bar i{display:block;height:100%;background:var(--run)}
pre{margin:0;padding:10px 12px;border-top:1px solid var(--line);overflow-x:auto;font-size:12px;max-height:420px}
</style></head><body><main><h1>MACI 실행 상태</h1>
<div class="sub"><span id="sub"></span> · <a href="eval">로그 평가</a></div><div id="list"></div></main>
<script>
const open = new Set();
function esc(s){return s.replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
async function load(){
  let data; try{data = await (await fetch('status.json',{cache:'no-store'})).json()}catch(e){return}
  document.getElementById('sub').textContent = data.run + ' · ' + data.maps.length + '개 맵 · '
    + new Date().toLocaleTimeString() + ' 갱신 (5초마다)';
  document.querySelectorAll('details[open]').forEach(d=>open.add(d.dataset.map));
  document.querySelectorAll('details:not([open])').forEach(d=>open.delete(d.dataset.map));
  document.getElementById('list').innerHTML = data.maps.map(m=>{
    const tag = m.done ? (m.cleared ? '<span class="tag ok">클리어</span>' : '<span class="tag fail">종료</span>')
                       : '<span class="tag run">진행 중</span>';
    const pct = m.steps ? Math.min(100, 100*m.step/m.steps) : 0;
    const res = m.result ? Object.entries(m.result).map(([k,v])=>k+'='+(typeof v==='number'?+v.toFixed(2):v)).join(' ') : '';
    return `<details data-map="${esc(m.map)}" ${open.has(m.map)?'open':''}><summary><span class="name">${esc(m.map)}</span>${tag}
      <span class="meta">step ${m.step??'-'}/${m.steps??'-'}</span><span class="bar"><i style="width:${pct}%"></i></span>
      <span class="meta">${esc(res)}</span></summary><pre>${esc(m.lines.join('\\n'))}</pre></details>`}).join('');
}
load(); setInterval(load, 5000);
</script></body></html>"""

EVAL_STYLE = """<style>
:root{--bg:#f7f7f5;--fg:#1d1d1b;--muted:#6b6b66;--card:#fff;--line:#e3e3de;--ok:#1f7a3a;--run:#2d5fb0;--fail:#a33}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--fg:#e8e8e3;--muted:#9a9a93;--card:#20201e;--line:#33332f}}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,sans-serif}
main{max-width:1100px;margin:0 auto;padding:16px}a{color:var(--run)}h1{font-size:18px;margin:0 0 4px}
.sub,.meta{color:var(--muted)}.ok{color:var(--ok)}.fail{color:var(--fail)}.run{color:var(--run)}
table{width:100%;border-collapse:collapse;background:var(--card)}td,th{padding:6px 8px;border-bottom:1px solid var(--line);text-align:left}
details{background:var(--card);border:1px solid var(--line);border-radius:8px;margin-bottom:8px}
summary{cursor:pointer;padding:10px 12px;display:flex;gap:12px;flex-wrap:wrap;align-items:baseline}
pre{margin:0;padding:10px 12px;border-top:1px solid var(--line);overflow-x:auto;font-size:12px;max-height:520px;white-space:pre-wrap}
form{padding:10px 12px;border-top:1px solid var(--line);display:flex;gap:8px;flex-wrap:wrap;align-items:center}
input,select,button{font:inherit;padding:4px 8px;background:var(--bg);color:var(--fg);border:1px solid var(--line);border-radius:6px}
input[name=comment]{flex:1;min-width:200px}.box{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 12px;margin:12px 0}
@media (max-width:640px){td:nth-child(n+4),th:nth-child(n+4){display:none}}
</style>"""


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def eval_page(title: str, body: str, refresh: bool = False) -> bytes:
    meta = '<meta http-equiv="refresh" content="5">' if refresh else ""
    return (f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" '
            f'content="width=device-width, initial-scale=1">{meta}<title>{esc(title)}</title>{EVAL_STYLE}</head>'
            f'<body><main>{body}</main></body></html>').encode("utf-8")


class Evaluator:
    """로그 평가 페이지의 상태: 판단 시점 묶음 캐시와 판정기 실행 작업"""

    def __init__(self, root: Path, allow_judge: bool = False, embed: bool = False):
        self.root, self.allow_judge, self.embed = root, allow_judge, embed
        self.jobs: dict[str, str] = {}  # manifest 상대 경로 -> 판정기 실행 상태 글
        self.lock = threading.Lock()

    def client(self):
        from openai import OpenAI
        from maci_judge import read_secret
        return OpenAI(base_url="https://openrouter.ai/api/v1", api_key=read_secret("key.txt"))

    def bundles(self, manifest: Path) -> list[dict]:
        import judge_context
        client = None
        if self.embed:
            try:
                client = self.client()
            except Exception:
                client = None
        return judge_context.load_or_build_bundles(manifest, client, log=lambda message: None)

    def index(self) -> bytes:
        rows = []
        for manifest in list_manifests(self.root):
            rel = manifest.relative_to(self.root).as_posix()
            result = score_result(manifest.with_suffix(".score.json"))
            if result is None:
                state = '<span class="run">진행 중</span>'
            else:
                state = '<span class="ok">클리어</span>' if result.get("cleared") else '<span class="fail">실패</span>'
            rated = len(list(manifest.parent.glob(manifest.stem + ".anchor_ratings.*.json")))
            judged = manifest.with_name(manifest.stem + ".judges.json").is_file()
            total = result.get("total", "-") if result else "-"
            rows.append(f'<tr><td><a href="/eval/run?path={quote(rel)}">{esc(rel)}</a></td><td>{state}</td>'
                        f'<td>{esc(total)}</td><td>{"있음" if judged else "-"}</td><td>{rated or "-"}</td></tr>')
        body = (f'<h1>로그 평가</h1><div class="sub">{esc(self.root.name)} · 실행 {len(rows)}개 · '
                f'<a href="/">실시간 로그</a></div><table><tr><th>실행</th><th>상태</th><th>총점</th><th>판정기</th>'
                f'<th>사람 채점자</th></tr>{"".join(rows) or "<tr><td>실행 기록이 없습니다</td></tr>"}</table>')
        return eval_page("로그 평가", body)

    def run(self, rel: str, manifest: Path, rater: str) -> bytes:
        import judge_agreement
        import judge_context
        bundles = self.bundles(manifest)
        judges = judge_context.judge_scores(manifest)
        humans = judge_context.load_all_anchor_ratings(manifest)
        job = self.jobs.get(rel, "")
        report = judge_agreement.report(manifest, "anchor", humans)
        agreement = "<br>".join(esc(line) for line in judge_agreement.format_report(report))
        judge_button = (f'<form method="post" action="judge"><input type="hidden" name="path" value="{esc(rel)}">'
                        f'<button {"disabled" if job.startswith("실행 중") else ""}>판정기 실행 '
                        f'({len(bundles)}개 시점, API 비용)</button><span class="meta">{esc(job)}</span></form>'
                        if self.allow_judge else '<div class="meta">판정기 실행은 꺼져 있습니다 (--allow-judge).</div>')
        points = []
        for bundle in bundles:
            key = judge_agreement.turn_key(bundle["step"], bundle["agent"])
            judge_text = "  ".join(f"{name.split('/')[-1]} {s[key]:g}" for name, s in judges.items() if key in s)
            human_text = "  ".join(f"{name} {s[key]:g}" for name, s in humans.items() if key in s)
            anchor = f"p-{bundle['agent']}-{bundle['step']}"
            points.append(
                f'<details id="{anchor}"><summary><b>{esc(bundle["agent"])} · step {bundle["step"]}</b>'
                f'<span>{esc(redact(" | ".join(bundle["trigger"]))[:160])}</span>'
                f'<span class="meta">판정기: {esc(judge_text or "-")} · 사람: {esc(human_text or "-")}</span></summary>'
                f'<pre>{esc(redact(judge_context.render(bundle)))}</pre>'
                f'<form method="post" action="rate"><input type="hidden" name="path" value="{esc(rel)}">'
                f'<input type="hidden" name="agent" value="{esc(bundle["agent"])}">'
                f'<input type="hidden" name="step" value="{bundle["step"]}">'
                f'<input name="rater" placeholder="채점자" value="{esc(rater)}" required size="10">'
                f'<select name="score">{"".join(f"<option>{i}</option>" for i in range(11))}</select>'
                f'<input name="comment" placeholder="메모"><button>저장</button></form></details>')
        body = (f'<h1>{esc(rel)}</h1><div class="sub"><a href="/eval">실행 목록</a> · '
                f'{esc(judge_context.summary(manifest, bundles, rater) if rater else f"판단 시점 {len(bundles)}개")}</div>'
                f'<div class="box">{esc(judge_context.ANCHOR_RUBRIC)}</div>{judge_button}'
                f'<div class="box">{agreement}</div>{"".join(points) or "<p>판단 시점이 없습니다.</p>"}')
        return eval_page(rel, body, refresh=job.startswith("실행 중"))

    def rate(self, manifest: Path, form: dict) -> None:
        import judge_context
        bundles = {(b["agent"], b["step"]): b for b in self.bundles(manifest)}
        bundle = bundles.get((form.get("agent", ""), int(form.get("step", "-1"))))
        if bundle is None:
            raise ValueError("없는 판단 시점입니다.")
        score = int(form.get("score", ""))
        judge_context.save_anchor_rating(manifest, form.get("rater", ""), bundle, score, form.get("comment", "")[:1000])

    def start_judge(self, rel: str, manifest: Path) -> None:
        import judge_agreement
        import maci_judge
        with self.lock:
            if self.jobs.get(rel, "").startswith("실행 중"):
                return
            self.jobs[rel] = "실행 중 0개 완료"
        bundles = self.bundles(manifest)
        model = maci_judge.DEFAULT_JUDGE_MODEL
        done = {"n": 0}

        def log(message):
            if "anchor step=" in message:
                done["n"] += 1
                self.jobs[rel] = f"실행 중 {done['n']}/{len(bundles)}개 완료"

        def work():
            try:
                result = maci_judge.score_run_anchors(manifest, self.client(), model, bundles=bundles, log=log)
                judge_agreement.save_judge_result(manifest, model + judge_agreement.ANCHOR_SUFFIX, result)
                self.jobs[rel] = f"완료: {model} 평균 {result['raw_avg']:.2f} ({result['n_scored']}/{result['n_total']})"
            except Exception as exc:
                self.jobs[rel] = f"실패: {type(exc).__name__}: {redact(str(exc))[:200]}"
        threading.Thread(target=work, daemon=True).start()


def make_handler(run_dir: Path, evaluator: Evaluator | None = None):
    evaluator = evaluator or Evaluator(run_dir)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            url = urlparse(self.path)
            query = {k: v[0] for k, v in parse_qs(url.query).items()}
            if url.path in ("/", "/index.html"):
                self._send(PAGE.encode("utf-8"), "text/html; charset=utf-8")
            elif url.path == "/status.json":
                body = json.dumps({"run": run_dir.name, "maps": all_status(run_dir)}, ensure_ascii=False)
                self._send(body.encode("utf-8"), "application/json; charset=utf-8")
            elif url.path in ("/eval", "/eval/"):
                self._send(evaluator.index(), "text/html; charset=utf-8")
            elif url.path == "/eval/run":
                manifest = resolve_manifest(run_dir, query.get("path", ""))
                if manifest is None:
                    self.send_error(404)
                    return
                try:
                    page = evaluator.run(query["path"], manifest, query.get("rater", ""))
                except Exception as exc:  # 대화 이력 파일이 없는 실행 등
                    page = eval_page("오류", f'<p>이 실행을 평가할 수 없습니다: {esc(type(exc).__name__)}: '
                                            f'{esc(redact(str(exc)))}</p><a href="/eval">실행 목록</a>')
                self._send(page, "text/html; charset=utf-8")
            else:
                self.send_error(404)

        def do_POST(self):
            url = urlparse(self.path)
            length = min(int(self.headers.get("Content-Length") or 0), 20_000)
            form = {k: v[0] for k, v in parse_qs(self.rfile.read(length).decode("utf-8", "replace")).items()}
            manifest = resolve_manifest(run_dir, form.get("path", ""))
            if manifest is None or url.path not in ("/eval/rate", "/eval/judge"):
                self.send_error(404)
                return
            back = f"run?path={quote(form['path'])}"
            if url.path == "/eval/rate":
                try:
                    evaluator.rate(manifest, form)
                except (ValueError, KeyError) as exc:
                    self.send_error(400, "invalid rating")  # 상태 줄은 latin-1이라 한글 메시지를 못 담음
                    return
                back += f"&rater={quote(form.get('rater', ''))}#p-{quote(form.get('agent', ''))}-{form.get('step', '')}"
            else:
                if not evaluator.allow_judge:
                    self.send_error(403, "judge disabled (--allow-judge)")
                    return
                evaluator.start_judge(form["path"], manifest)
            self.send_response(303)
            self.send_header("Location", back)
            self.end_headers()

        def _send(self, body: bytes, content_type: str):
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    return Handler


def main():
    parser = argparse.ArgumentParser(description="Live status and log evaluation pages for benchmark run folders.")
    parser.add_argument("run_dir")
    parser.add_argument("--host", default="127.0.0.1", help="Pi의 Tailscale IP에 붙이면 tailnet 안에서만 열림")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--allow-judge", action="store_true", help="로그 평가에서 판정기 실행 버튼을 켬 (key.txt, API 비용)")
    parser.add_argument("--embed", action="store_true", help="판단 시점의 이전 맥락을 임베딩으로 고름 (기본: 단어 기반)")
    args = parser.parse_args()
    run_dir = Path(args.run_dir).resolve()
    if not run_dir.is_dir():
        parser.error(f"not a folder: {run_dir}")
    evaluator = Evaluator(run_dir, allow_judge=args.allow_judge, embed=args.embed)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(run_dir, evaluator))
    print(f"Serving {run_dir} at http://{args.host}:{args.port}/ (log evaluation: /eval)", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
