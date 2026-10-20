"""Runs one agent's generated decide() code in a restricted subprocess.

Invoked as a subprocess by policy_sandbox.py with the launcher's -I -S flags
(isolated mode, no site module) - not meant to be imported or run standalone
otherwise. Reads a JSON payload {"code": ..., "observation": ...} from the
path in argv[1] and prints a single JSON result line to stdout:
{"action": dict|None, "error": str|None}.

This restricts the *ordinary* way in - imports only of SAFE_MODULES, no
dunder-name references, no exec/eval/open/__import__/compile/input calls (checked twice:
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
import collections
import functools
import heapq
import itertools
import json
import math
import sys

_FORBIDDEN_CALL_NAMES = {"exec", "eval", "open", "__import__", "compile", "input"}

# 프레임/코드 객체 속성: dunder 없이도 제너레이터의 gi_frame.f_back.f_globals처럼 하네스
# 자신의 전역(sys, builtins)까지 거슬러 올라가 샌드박스를 벗어날 수 있으므로 막음
_FORBIDDEN_ATTR_PREFIXES = ("gi_", "cr_", "ag_", "f_", "tb_", "co_")

# 생성 코드가 쓸 수 있는 내장 이름. getattr/setattr/type/vars/dir/globals처럼 문자열로 dunder 속성에
# 닿거나 객체 내부를 들여다볼 수 있는 것은 넣지 않음. 이 목록은 프롬프트에도 그대로 안내됨
_SAFE_BUILTIN_NAMES = (
    "abs", "all", "any", "bool", "callable", "chr", "dict", "divmod", "enumerate", "filter", "float",
    "format", "frozenset", "hash", "int", "isinstance", "iter", "len", "list", "map", "max", "min",
    "next", "ord", "pow", "print", "range", "repr", "reversed", "round", "set", "slice", "sorted", "str",
    "sum", "tuple", "zip", "True", "False", "None",
    "Exception", "ArithmeticError", "AttributeError", "IndexError", "KeyError", "LookupError",
    "StopIteration", "TypeError", "ValueError", "ZeroDivisionError",
)
# import해도 되는 표준 모듈 (부작용/외부 접근이 없는 계산용). math는 import 없이도 쓸 수 있음.
# random은 실행마다 결과가 달라져 재현성을 해치므로 넣지 않음
SAFE_MODULES = {"math": math, "itertools": itertools, "collections": collections, "heapq": heapq,
                "functools": functools}


def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    if level == 0 and name in SAFE_MODULES:
        return SAFE_MODULES[name]
    raise ImportError(f"only these modules can be imported: {', '.join(sorted(SAFE_MODULES))}")


SAFE_BUILTINS = {name: getattr(builtins, name) for name in _SAFE_BUILTIN_NAMES}
SAFE_BUILTINS["__import__"] = _safe_import


def _check_code_safety(code: str) -> None:
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name not in SAFE_MODULES:
                    raise ValueError(f"generated code may only import {', '.join(sorted(SAFE_MODULES))}")
        if isinstance(node, ast.ImportFrom) and (node.level or node.module not in SAFE_MODULES):
            raise ValueError(f"generated code may only import {', '.join(sorted(SAFE_MODULES))}")
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            raise ValueError("generated code may not reference dunder names")
        # Blocks attribute-access escapes too (e.g. ({}).__class__.__bases__),
        # not just bare dunder names (e.g. __builtins__) - a bare-name-only
        # check would let object-introspection chains slip through unnoticed.
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise ValueError("generated code may not reference dunder attributes")
        if isinstance(node, ast.Attribute) and node.attr.startswith(_FORBIDDEN_ATTR_PREFIXES):
            raise ValueError(f"generated code may not access frame/code attribute .{node.attr}")
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
        try:
            json.dumps(action)
        except (TypeError, ValueError) as e:
            raise ValueError(f"decide() returned an action that is not JSON-serializable ({e}); action and memory "
                             "may hold only dict/list/str/int/float/bool/None (e.g. convert sets to sorted lists)")
        result["action"] = action
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"

    print(json.dumps(result))


if __name__ == "__main__":
    main()
