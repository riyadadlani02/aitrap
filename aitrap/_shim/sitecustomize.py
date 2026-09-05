"""Dropped on PYTHONPATH by `aitrap run` - installs traps with zero target code change."""
import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
_rest = [p for p in sys.path if os.path.abspath(p or ".") != _here]
sys.path[:] = _rest  # stop shadowing the target's own sitecustomize

# Chain to the real sitecustomize under a different module name: popping our own
# half-imported module from sys.modules breaks the import that is running us.
try:
    from importlib.machinery import PathFinder
    from importlib.util import module_from_spec

    _spec = PathFinder().find_spec("sitecustomize", _rest)
    if _spec is not None:
        _spec.loader.exec_module(module_from_spec(_spec))
except Exception as exc:
    print(f"[aitrap] chained sitecustomize failed: {exc}", file=sys.stderr)

try:
    import aitrap

    aitrap.serve()
except Exception as exc:  # never take the target process down with us
    print(f"[aitrap] failed to install: {exc}", file=sys.stderr)
