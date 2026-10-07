"""Base action-function layout supplied to LLMs as source, not imported by generated code."""


def decide(observation):
    # 1. Read only this agent's allowed observation.
    me = observation["self"]
    x, y = me["x"], me["y"]
    step = me["step"]
    memory = dict(observation.get("memory", {}))
    inbox = observation.get("inbox", [])
    walls = observation.get("walls", [])
    objects = dict(observation.get("known_objects", {}))
    for obj in observation.get("visible_objects", []):
        objects[obj["object_id"]] = obj

    # 2. Use these helpers to keep action and memory formatting consistent.
    def finish(action_type="noop", **fields):
        action = dict(fields)
        action["type"] = action_type
        action["memory"] = memory
        return action

    def find_object(object_id):
        return objects.get(object_id)

    def move_toward(tx, ty, stop_radius=0.0, step_size=20.0):
        dx, dy = tx - x, ty - y
        distance = math.hypot(dx, dy)
        if distance <= stop_radius or distance == 0:
            return finish()
        target_facing = math.degrees(math.atan2(dy, dx)) % 360
        angle = (target_facing - me.get("facing", 0) + 180) % 360 - 180
        if abs(angle) > 0.001:
            return finish("turn", angle=angle)
        travel = min(step_size, distance - stop_radius)
        return finish("move_forward", distance=travel)

    def send_message(receiver_id, content):
        return finish("send_message", receiver_id=receiver_id, content=content)

    # 3. DECISION START: replace only this region with task-specific logic.
    # Read new messages, check progress/reset, select a target, and act.
    # Save state in memory. Return through finish/move_toward/send_message.
    return finish()
    # DECISION END
