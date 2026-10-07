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

## GUI 실행

VS Code PowerShell 터미널에서 프로젝트 폴더로 이동한 뒤 처음 한 번 패키지를 설치합니다.

```powershell
python -m pip install -r requirements.txt
python launcher.py
```

또는 `./Start-MACI.ps1`을 실행하면 필요한 패키지를 확인한 뒤 GUI를 엽니다. 이 작업 공간에서는 준비된 Python 환경을 사용해 `.\.venv-gui\Scripts\python.exe launcher.py`로도 실행할 수 있습니다.

GUI에서 다음 순서로 실험할 수 있습니다.

1. **맵**: 기본 맵을 선택하거나 시드·에이전트 수·퍼즐 수·포탈 수를 지정해 생성합니다. 저장된 맵을 목록에서 선택하거나 경로를 입력할 수도 있습니다. 에디터에서 `P`로 테스트하고 `Ctrl+S`로 저장한 뒤 창을 닫으면 선택 맵에 반영됩니다.
2. **실행**: **일반 맵 / 압력판** 또는 **두 방 순서 퍼즐**을 선택합니다. 두 방 퍼즐은 시드·방마다 번호판 수·정답 입력 수·허용 리셋 횟수를 설정합니다. 최대 step은 퍼즐의 턴 제한이 됩니다. 일반 맵은 규칙 기반(`tooluse`)으로 먼저 동작을 확인할 수 있지만 이 정책은 번호판 퍼즐을 풀지 못합니다. 퍼즐의 LLM 실행은 **LLM 코드 정책**을 선택하고 모델·API 주소를 설정합니다. 프로젝트 루트의 `key.txt`에 API 키만 입력하세요. 환경변수는 사용하지 않습니다.
3. **결과**: 완료된 실행의 총점·단체 점수·에이전트별 내역·행동·메시지·이벤트를 확인합니다. 예전 결과도 목록에서 선택할 수 있습니다. **이동 다시 보기**로 시각적으로 재생합니다. 전체 생성 코드는 `benchmark_runs/*.jsonl`에 있습니다.
4. **LLM 채점**: 결과를 선택하고 판정 모델·최대 턴·에이전트 필터를 설정합니다. 최대 턴과 에이전트를 비우면 전체를 채점합니다. 기준 모델(`upstage/solar-pro4`)의 결과로 100점 기준을 등록할 수 있습니다. 채점 출력은 결과 파일 옆 `*.judge.log.txt`에도 저장됩니다.

진행 로그는 창 아래에 표시됩니다. 목록·결과·로그 위에서 마우스 휠로 스크롤할 수 있습니다. 입력칸에서 `Ctrl+A`로 내용을 지우고 새 값을 입력하세요. **작업 중단** 또는 창 닫기는 진행 중인 작업도 중단합니다. 부분 로그에는 완료 점수가 없을 수 있습니다. LLM 실행과 채점은 API 사용 비용이 발생할 수 있습니다.

**실행 → 디버깅: 켜짐**으로 설정하고 실행하면 **디버그** 탭에서 상세 로그를 실시간으로 봅니다. LLM 요청 시작·생성 코드·컴파일/실행 결과·복구 대기·행동·메시지·퍼즐 이벤트를 표시하며, step 완료 전의 오류 검사도 바로 나타납니다. 최신 내용을 자동으로 따라가고 휠로 과거 내용을 살펴보거나 **최신 로그로 이동**으로 돌아올 수 있습니다. GUI에는 최근 3,000개 원본 로그 행을 보관하며 전체 상세 로그는 `<실행 이름>.debug.jsonl`에 즉시 저장합니다. 터미널 실행은 `python benchmark.py --debug ...`를 사용합니다. 디버깅을 끄면 상세 로그 파일은 생성하지 않으며 기존 실행·검사 로그는 유지합니다.

LLM context는 에이전트별로 누적합니다. 이전 요청·모델 응답·코드 제출 검사 결과와 각 step의 자기 관찰·실제 행동·다음 관찰을 다음 LLM 요청에 함께 보냅니다. 다른 에이전트의 비공개 관찰이나 관찰자용 전체 맵은 포함하지 않습니다. 코드 정책은 기존처럼 코드를 재사용하되 다음 코드 생성/복구 요청 때 누적 이력을 전달합니다. 에피소드마다 새 이력으로 시작하고 `CodePolicy.reset()`도 이력을 비웁니다. 완료 후 `<실행 이름>.context.json`에 에이전트별 이력을 저장하며 step 로그의 `decision.context_messages` 및 디버그 로그에서 메시지 수를 확인할 수 있습니다.

행동 함수의 기본 레이아웃은 `enviroment/policy_template.py`입니다. 코드 생성 프롬프트는 관찰/메모리/물체 목록을 준비하는 부분과 `finish`, `find_object`, `move_toward`, `send_message` 헬퍼를 제공하고 LLM에게 `DECISION START/END` 영역의 판단 로직을 채우도록 안내합니다. LLM은 완성된 `decide(observation)` 전체를 제출하며 기존 컴파일·안전성·실행 검사를 통과해야 합니다. `finish`를 통해 모든 행동에 메모리를 포함하고 현재 시야 밖의 기억한 물체도 조회할 수 있습니다. `move_toward`는 직선 이동 헬퍼이므로 벽 우회나 미끼 번호판 회피를 위한 경유점은 판단 로직에서 선택해야 합니다. 초기 코드 생성과 오류 복구, LiveCodePolicy 및 HybridPolicy의 코드 모드에 같은 틀을 제공합니다.

**에이전트 이동 창**은 실행 시 자동으로 열립니다 (실행 탭에서 끌 수 있음). 맵·벽·번호판·문·이동 경로와 에이전트 위치를 표시하며 오른쪽에서 해당 step의 행동·메시지·이벤트를 볼 수 있습니다. 일시정지, 처음, 이전/다음, 최신 step, 재생 속도 버튼을 제공합니다. `Space`는 재생/정지, 좌우 방향키는 step 이동입니다. 움직임은 기록된 step 사이를 보간해 표시합니다. 관찰자용 전체 상태는 에이전트 관찰에 포함되지 않습니다. 이동 창을 닫아도 실행은 계속됩니다.

두 방 퍼즐의 번호판 번호와 전체 입력 순서는 시드 기반 난수로 부여됩니다. 같은 시드는 같은 퍼즐을 재현하며 실행 도중이나 오입력 리셋 후에도 번호·순서는 바뀌지 않습니다. 각 방의 안내판에는 자기 차례만 표시되므로 메시지로 공유 순서를 맞춰야 합니다. 번호판의 반경 10 범위에 닿으면 자동 입력되며 `press_button`은 필요하지 않습니다. 머무르면 반복 입력되지 않고 나갔다 다시 들어와야 재입력됩니다. 이동 중 다른 번호판을 스쳐도 입력되므로 번호판 줄 아래로 우회한 뒤 목표에 접근해야 합니다. 이동 창의 번호판 주변 원은 접촉 범위입니다.

새 실행에는 초기 상태를 담은 `*.scene.json`과 매 step의 `world`·`facing`·`failure`가 저장됩니다. 이전 형식 JSONL은 에이전트 위치만 재생할 수 있습니다. 터미널에서도 실행 가능합니다.

LLM 코드 정책의 실행 오류가 발생하면 새 코드가 실행에 성공할 때까지 현재 step에서 기다립니다. 기다리는 동안 이동·회전하거나 추가 step을 소비하지 않습니다. 코드 재생성 또는 재실행이 실패하면 잠시 대기 후 재시도하며, 성공한 행동으로 현재 step을 이어갑니다. 복구 대기는 일반 정체 재계획 횟수 제한과 별개로 진행됩니다. GUI 로그에 `[CODE RECOVERY]`가 표시되며 **작업 중단**으로 대기를 끝낼 수 있습니다. 복구 결과는 `decision.recovery`에 기록됩니다.

에이전트가 제출한 코드는 `py_compile`로 검사하며 실행 직전에도 다시 검사합니다. 컴파일 성공은 문법 검사 통과를 뜻하고, 실제 실행 성공 여부는 샌드박스에서 별도로 확인합니다. 에이전트마다 `compile_attempts/successes/failures`와 `execution_attempts/successes/failures`를 누적합니다. 제출 단계와 실행 직전의 검사는 각각 1회로 세며 동일 코드의 재검사도 포함합니다. 컴파일 실패 시 실행 횟수는 증가하지 않습니다. 각 검사 결과·에이전트·코드 SHA-256·누적 횟수는 `*.code_checks.jsonl`에 즉시 저장되므로 복구 대기 중 중단해도 남습니다. step 로그의 `decision.code_checks`와 완료 점수 파일의 `code_checks`에도 누적 횟수가 기록되며 결과·이동 화면에서 볼 수 있습니다.

```powershell
python benchmark.py --environment sequence_rooms --sequence-seed 42 --steps 80
python viewer.py benchmark_runs\실행결과.jsonl
```

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
