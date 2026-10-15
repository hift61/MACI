"""Read-only turn context for the web evaluator, without simulator dependencies."""
import json
import math


def read_records(path):
    # Sidecars must stay beside the manifest, including when symlinks are used.
    if path.resolve().parent != path.parent.resolve():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    records = []
    for line in lines:
        try:
            record = json.loads(line)
        except ValueError:
            continue  # A live runner may still be writing the last line.
        if isinstance(record, dict):
            records.append(record)
    return records


class TurnContext:
    def __init__(self, manifest):
        self.frames = {r["step"]: r for r in read_records(manifest) if "step" in r}
        scene_path = manifest.with_suffix(".scene.json")
        if scene_path.resolve().parent == scene_path.parent.resolve():
            try:
                scene = json.loads(scene_path.read_text(encoding="utf-8"))
                if isinstance(scene, dict):
                    self.frames[0] = scene
            except (OSError, ValueError):
                pass
        self.observations = {(r.get("step"), r.get("agent")): r.get("observation")
                             for r in read_records(manifest.with_suffix(".observations.jsonl"))}

    def render(self, step, agent, escape):
        before, after = self.frames.get(step - 1), self.frames.get(step)
        maps = []
        for label, frame in (("직전 턴 종료", before), ("행동 후", after)):
            drawing = render_map(frame, agent, escape) if frame else ""
            maps.append(f'<div><b>{label} · step {step - 1 if label == "직전 턴 종료" else step}</b>'
                        + (drawing or '<p class="meta">이 시점의 지도 기록이 없습니다.</p>') + '</div>')
        frame = after or {}
        actions = [{"agent": a.get("agent"), "action": (a.get("decision") or {}).get("final_action")}
                   for a in frame.get("agents", [])]
        details = {"행동": actions, "메시지": frame.get("messages", []), "이벤트": frame.get("events", [])}
        state = (frame.get("world") or {}).get("level_state")
        if state:
            details["단계 상태"] = state
        observation = self.observations.get((step, agent))
        obs = ('<pre>' + escape(json.dumps(observation, ensure_ascii=False, indent=2)) + '</pre>'
               if observation is not None else '<p class="meta">이 턴의 관찰 기록이 없습니다.</p>')
        return ('<section class="turn-context"><h2>이 턴의 상황</h2>'
                '<p class="meta">지도는 관찰자 시점의 전체 상태입니다. 실제 판단에 사용할 수 있었던 정보는 아래 에이전트 관찰에서 확인하세요. 화살표는 바라보는 방향이며, 흰 테두리는 평가 대상입니다.</p>'
                f'<div class="turn-maps">{"".join(maps)}</div>'
                f'<pre>{escape(json.dumps(details, ensure_ascii=False, indent=2))}</pre>'
                f'<details><summary>{escape(agent)} 에이전트가 받은 관찰 · step {step}</summary>{obs}</details></section>')


def render_map(frame, selected, escape):
    world = frame.get("world") or {}
    if not world or not world.get("width") or not world.get("height"):
        return ""
    width, height = float(world["width"]), float(world["height"])
    scale = 460 / max(width, height)
    def n(value):
        return f"{float(value) * scale:.2f}"
    parts = [f'<svg class="turn-map" viewBox="-16 -16 {width * scale + 32:g} {height * scale + 32:g}" '
             'role="img" aria-label="턴 상황 지도" xmlns="http://www.w3.org/2000/svg">',
             f'<rect width="{n(width)}" height="{n(height)}" fill="#1d2533"/>']
    for x, y, w, h in world.get("walls", []):
        parts.append(f'<rect x="{n(x)}" y="{n(y)}" width="{n(w)}" height="{n(h)}" fill="#8c97a9"/>')
    colors = {"number_pad": "#80beec", "button": "#57c4db", "key": "#f2d75a",
              "portal": "#ac7de7", "pressure_plate": "#71bf7f"}
    for obj in world.get("objects", []):
        if obj.get("x") is None or obj.get("y") is None:
            continue
        x, y = float(obj["x"]) * scale, float(obj["y"]) * scale
        kind = obj.get("type")
        color = colors.get(kind, "#c1c9d6")
        if kind == "door":
            color = "#da705f" if obj.get("locked") else "#60d08a"
        label = obj.get("number", obj.get("object_id", kind))
        title = escape(json.dumps(obj, ensure_ascii=False))
        radius = max(4, float(obj.get("radius", 6)) * scale)
        parts.append(f'<g><title>{title}</title><circle cx="{x:g}" cy="{y:g}" r="{radius:g}" fill="{color}"/>'
                     f'<text x="{x + radius + 3:g}" y="{y:g}" fill="#e3ebf6" font-size="10">{escape(label)}</text></g>')
    for i, agent in enumerate(frame.get("agents", [])):
        pos = agent.get("position")
        if not pos:
            continue
        x, y = (float(p) * scale for p in pos)
        angle = math.radians(float(agent.get("facing", 0)))
        color = ("#ff859b", "#57b8ff", "#74df9e", "#e5b853")[i % 4]
        border = "#fff" if agent.get("agent") == selected else color
        parts.append(f'<g><title>{escape(agent.get("agent"))} · {escape(pos)}</title>'
                     f'<circle cx="{x:g}" cy="{y:g}" r="9" fill="{color}" stroke="{border}" stroke-width="2"/>'
                     f'<path d="M{x:g},{y:g} L{x + 23 * math.cos(angle):g},{y + 23 * math.sin(angle):g}" stroke="{color}" stroke-width="3"/>'
                     f'<text x="{x:g}" y="{y + 4:g}" text-anchor="middle" fill="#121721" font-size="11">{escape(agent.get("agent"))}</text></g>')
    return "".join(parts) + '</svg>'
