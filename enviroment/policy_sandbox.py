"""Sandboxed execution of LLM-generated policy code (Code as Policies) for
MACI agents.

CodePolicy/LiveCodePolicy/HybridPolicy (see policy.py) used to exec()
generated decide() code directly in the main simulation process. Every call
here instead runs in a separate, disposable `python -I -S` subprocess (see
_policy_harness.py) with a hard wall-clock timeout, so a runaway (e.g.
infinite-looping) or crashing decide() can only hang or crash *itself* -
never the simulation loop or the other agents in it. The static import/
dunder/exec-eval-open check still runs first inside the harness; this
subprocess boundary is a second, OS-level layer on top of that, not a
replacement for it - see _policy_harness.py's docstring for the real
(limited) security model this provides.

The trade-off is a subprocess spawn per decide() call (tens of
milliseconds), paid every step for CodePolicy/HybridPolicy's cached code
too - deliberate, since decide() must stay a fast, side-effect-free
function of `observation` anyway (see policy.py's CodePolicy docstring), so
nothing is lost by not keeping it "warm" as an in-process callable between
steps.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

HARNESS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_policy_harness.py")

DEFAULT_TIMEOUT_SEC = 5.0


def run_decide_code(code: str, observation: dict, timeout: float = DEFAULT_TIMEOUT_SEC) -> dict:
    """Executes `code`'s decide(observation) in a locked-down subprocess.
    Returns {"action": dict|None, "error": str|None} - error is set if the
    code failed the safety check, raised, returned something that isn't a
    valid action dict, or timed out."""
    payload_path = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump({"code": code, "observation": observation}, f)
            payload_path = f.name

        try:
            proc = subprocess.run(
                [sys.executable, "-I", "-S", HARNESS_PATH, payload_path],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return {"action": None, "error": f"timed out after {timeout}s (likely an infinite loop)"}

        if proc.returncode != 0:
            return {"action": None, "error": f"harness crashed (exit {proc.returncode}): {proc.stderr.strip()[-500:]}"}

        try:
            last_line = proc.stdout.strip().splitlines()[-1]
            return json.loads(last_line)
        except Exception as e:
            return {"action": None, "error": f"could not parse harness output ({e}): {proc.stdout[:500]!r}"}
    finally:
        if payload_path:
            try:
                os.unlink(payload_path)
            except OSError:
                pass
