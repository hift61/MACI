from .spec import MapSpec

# 에디터로 직접 만든 맵처럼 퍼즐 템플릿 없이 만들어진 맵의 과제 설명(hints)을 오브젝트 연결
# 관계와 objectives로부터 자동으로 만듦. 순수 데이터만 다루므로 pygame/Environment 의존 없음.


def _where(obj: dict, reveal_positions: bool) -> str:
    return f" (around ({obj['x']:.0f}, {obj['y']:.0f}))" if reveal_positions else ""


# door_id를 여는 장치 목록 (열쇠/버튼/레버/압력판)
def mechanisms_for(spec: MapSpec, door_id: str) -> list[dict]:
    result = []
    for obj in spec.objects:
        params = obj["params"]
        if obj["kind"] == "key" and params.get("unlocks") == door_id:
            result.append(obj)
        elif obj["kind"] in ("button", "pressure_plate") and params.get("linked_door_id") == door_id:
            result.append(obj)
        elif obj["kind"] == "lever" and door_id in params.get("linked_door_ids", []):
            result.append(obj)
    return result


def auto_hints(spec: MapSpec, reveal_positions: bool = False) -> list[str]:
    objects = {o["id"]: o for o in spec.objects}
    hints = []
    for objective in spec.objectives:
        if objective["type"] == "door_unlocked":
            door_id = objective["door_id"]
            door = objects.get(door_id)
            if door is None:
                continue
            ways = []
            mechs = mechanisms_for(spec, door_id)
            for key in [m for m in mechs if m["kind"] == "key"]:
                ways.append(f"use key '{key['id']}'{_where(key, reveal_positions)} next to it")
            for lever in [m for m in mechs if m["kind"] == "lever"]:
                ways.append(f"pull lever '{lever['id']}'{_where(lever, reveal_positions)}")
            for button in [m for m in mechs if m["kind"] == "button"]:
                ways.append(f"press button '{button['id']}'{_where(button, reveal_positions)} (it toggles the door)")
            plates = [m for m in mechs if m["kind"] == "pressure_plate"]
            if len(plates) == 1:
                ways.append(f"keep an agent standing on pressure plate '{plates[0]['id']}'{_where(plates[0], reveal_positions)}")
            elif plates:
                names = ", ".join(f"'{p['id']}'{_where(p, reveal_positions)}" for p in plates)
                ways.append(f"have agents stand on ALL of the pressure plates {names} AT THE SAME TIME")
            how = ": " + "; or ".join(ways) if ways else ""
            hints.append(f"Unlock '{door_id}'{_where(door, reveal_positions)}{how}.")
        elif objective["type"] == "item_picked_up":
            item = objects.get(objective["object_id"])
            if item is None:
                continue
            if item["params"].get("category") == "coop":
                need = item["params"].get("required_agents", 2)
                hints.append(f"Pick up the heavy item '{item['id']}'{_where(item, reveal_positions)}: it needs {need} agents "
                             f"standing next to it together, and the carrier cannot move unless a helper stays close.")
            else:
                hints.append(f"Pick up '{item['id']}'{_where(item, reveal_positions)}.")

    if any(o["kind"] == "item" and o["params"].get("category") == "trap" for o in spec.objects):
        clues = [o for o in spec.objects if o["kind"] == "clue"]
        tail = f" Hidden notes ({', '.join(repr(c['id']) for c in clues)}) may tell which ones are safe." if clues else ""
        hints.append("Some items that look normal are traps: picking one up seals every door forever." + tail)
    if any(o["kind"] == "portal" for o in spec.objects):
        hints.append("Portals (type 'portal') teleport you to their destination when you step onto them.")
    return hints
