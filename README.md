# MACI
(This repository is for the 2026 R&E project at CBSH 1st students.)


MACI is a project designed to analyze and evaluate collaboration between multiple AI agents in a shared environment.

---

## Project Overview

Most existing multi-agent evaluation methods focus mainly on whether the agents successfully complete a task or how much reward they receive.

However, a final success or failure score alone cannot explain what actually happened during the collaboration process.

For example, a failure may occur because:

* One agent provided incorrect information
* Another agent misunderstood a message
* The agents failed to coordinate their roles
* An agent made an incorrect plan
* An agent failed to detect or recover from an earlier mistake

MACI aims to identify these differences by analyzing the full interaction process between agents.

---

## Core Objective

The main research question of MACI is:

> Which agent caused the failure, at what point did the failure become decisive, and which message or action had the greatest influence?

MACI records the complete interaction trace of each episode, including:

* Agent observations
* Messages exchanged between agents
* Selected actions
* Changes in the environment
* Task progress
* Rewards and milestones

This allows the system to analyze not only the final result, but also the process that led to it.

---

## Failure Analysis

When a collaboration failure occurs, MACI attempts to identify:

* The agent responsible for the failure
* The decisive interaction step
* The message or action that influenced the outcome
* Whether the failure could have been detected or recovered from

Failures may be classified into categories such as:

* Perception
* Belief Tracking
* Communication
* Planning
* Coordination
* Execution
* Verification
* Evaluation

---

## Counterfactual Replay

MACI uses counterfactual replay to verify whether a specific message or action actually caused a failure.

The system can replay the same situation after changing one part of the original interaction, such as:

* Removing a message
* Correcting incorrect information
* Replacing an agent's action
* Changing the order of messages
* Delaying or blocking communication
* Swapping agent roles

The results of the original execution and the modified execution are then compared.

This makes it possible to explain failures using reproducible evidence rather than relying only on assumptions or generated explanations.

---

## Project Goal

The final goal of MACI is to build an evaluation framework that can measure and explain multi-agent collaboration.

Rather than asking only:

> Did the agents succeed?

MACI focuses on a more detailed question:

> How did the agents collaborate, where did the collaboration fail, and why did that failure occur?

---

## Continuous movement

Agent positions and headings use floating-point world coordinates. Screen pixels
are only a rendering detail; fractional distances and angles do not get rounded
by the simulation. To move 2.5 units in the current facing direction, return:

```python
{"type": "move_forward", "distance": 2.5}
```

Use `{"type": "turn", "angle": 37.5}` to rotate the body 37.5 degrees clockwise
in place, then move forward on the next step. Negative angles rotate
counterclockwise. Facing is in degrees: 0 points right, 90 down, 180 left, and
270 up. Forward motion preserves facing; rotation changes both heading and the
view cone without changing position. `turn(facing=...)` remains available for
absolute orientation; provide exactly one of `angle` or `facing`.

`move(dx, dy)` is removed and rejected as an invalid action, including commands
from another agent. Agents cannot strafe or walk backward. To move toward a
target, first rotate by `(target_facing - facing + 180) % 360 - 180`, then advance.

The observation's `self` includes `x`, `y`, `facing`, a unit `heading` vector,
`max_move` (default 20; `None` means unlimited), and `last_move`:

```python
{
    "step": 1,
    "requested_distance": 2.5,
    "distance": 2.5,
    "dx": 2.5,
    "dy": 0.0,
    "blocked": False,
    "limited": False,
}
```

`last_move` is initially `None` and persists until the next movement action.
Its distance and displacement exclude portal teleportation. `blocked` means
collision, a map boundary, or missing cooperative helpers shortened the capped
move; `limited` means the request exceeded `max_move`. Walls and locked doors
stop movement just before contact, including obstacles crossed mid-move.
The same spatial state is saved under each agent's `spatial_state` in the run log.
Movement still advances once per simulation step; distances are not velocities
and this interface does not introduce elapsed-time physics or rendering animation.

The pygame map editor has no visible grid or placement snapping. Dragging and
placing entities keeps fractional world coordinates. In test play, hold W/Up
to advance 2.5 units per action; A/Left/Q and D/Right/E rotate the body by 15
degrees per action. Hold Shift for 0.25-unit forward steps and 1.5-degree turns.
S/Down does not move backward. The mouse wheel rotates agents in edit mode with
the same angular increments. The sidebar shows position, facing, and heading.

Run the movement regression checks without external API calls:

```sh
python3 -m unittest discover -s tests -v
```

---

## Repository Access

The following members are authorized to access and modify this repository:

* Jihoon Park
* Yeomyeong Lee
* Henry Kim
* Hanwook Choi
