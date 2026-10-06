"""Runs one agent's generated decide() code in a restricted subprocess.

Invoked as a subprocess by policy_sandbox.py with the launcher's -I -S flags
(isolated mode, no site module) - not meant to be imported or run standalone
otherwise. Reads a JSON payload {"code": ..., "observation": ...} from the
path in argv[1] and prints a single JSON result line to stdout:
{"action": dict|None, "error": str|None}.

This restricts the *ordinary* way in - no import statements, no dunder-name
references, no exec/eval/open/__import__/compile/input calls (checked twice:
statically via _check_code_safety, and again at runtime via a builtins
allowlist that simply doesn't include them) - but plain Python has no true
capability sandbox, so a sufficiently adversarial snippet could still try to
escape via object introspection (e.g. chaining through
__class__/__subclasses__, which _check_code_safety's dunder-name check
already blocks at the syntax level). The real safety net here is OS-level:
this runs as a separate, disposable process with a hard wall-clock timeout
enforced by the caller (policy_sandbox.run_decide_code), so a buggy or
adversarial decide() (e.g. an infinite loop) can only hang or crash
*itself*, not the simulation - this is not a hardened boundary against a
truly malicious model.
"""
import ast
import builtins
import json
import math
import sys

_FORBIDDEN_CALL_NAMES = {"exec", "eval", "open", "__import__", "compile", "input"}

_SAFE_BUILTIN_NAMES = (
    "abs", "all", "any", "bool", "dict", "enumerate", "float", "int", "len",
    "list", "max", "min", "range", "reversed", "round", "sorted", "str",
    "sum", "tuple", "zip", "isinstance", "True", "False", "None",
)
SAFE_BUILTINS = {name: getattr(builtins, name) for name in _SAFE_BUILTIN_NAMES}


def _check_code_safety(code: str) -> None:
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise ValueError("generated code may not use import statements")
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            raise ValueError("generated code may not reference dunder names")
        # Blocks attribute-access escapes too (e.g. ({}).__class__.__bases__),
        # not just bare dunder names (e.g. __builtins__) - a bare-name-only
        # check would let object-introspection chains slip through unnoticed.
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise ValueError("generated code may not reference dunder attributes")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in _FORBIDDEN_CALL_NAMES:
                raise ValueError(f"generated code may not call {node.func.id}()")


def main():
    with open(sys.argv[1], "r", encoding="utf-8") as f:
        payload = json.load(f)

    code = payload["code"]
    observation = payload["observation"]
    result = {"action": None, "error": None}

    try:
        _check_code_safety(code)
        # globals/locals를 한 dict로 써야 코드 최상단에 둔 상수/보조 함수(예: ME = "A")가
        # decide() 안에서 보임 - 둘을 나누면 최상단 정의가 locals에만 들어가 NameError가 남
        scope: dict = {"__builtins__": SAFE_BUILTINS, "math": math}
        exec(compile(code, "<policy>", "exec"), scope)
        decide_fn = scope.get("decide")
        if not callable(decide_fn):
            raise ValueError("generated code did not define a decide() function")

        action = decide_fn(observation)
        if not isinstance(action, dict) or "type" not in action:
            raise ValueError(f"decide() returned invalid action: {action!r}")
        result["action"] = action
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"

    print(json.dumps(result))


if __name__ == "__main__":
    main()
