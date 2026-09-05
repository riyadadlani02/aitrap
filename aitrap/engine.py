"""Non-stopping trap engine built on sys.monitoring (PEP 669, Python 3.12+).

Traps capture and continue. Nothing here ever pauses the target process.
"""
import importlib
import itertools
import sys
import threading
import time
from collections import deque

from . import render

if not hasattr(sys, "monitoring"):  # pragma: no cover
    raise RuntimeError("aitrap needs Python 3.12+ (sys.monitoring / PEP 669)")

E = sys.monitoring.events
EVENT_MASKS = {"call": E.PY_START, "return": E.PY_RETURN, "raise": E.RAISE}


class Buffer:
    """Bounded event ring. Reports drops rather than silently losing coverage."""

    def __init__(self, maxlen=10_000):
        self._d = deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self._seq = itertools.count(1)
        self.dropped = 0

    def push(self, event):
        with self._lock:
            event["seq"] = next(self._seq)
            if len(self._d) == self._d.maxlen:
                self.dropped += 1
            self._d.append(event)

    def poll(self, cursor=0, limit=100):
        with self._lock:
            # ponytail: linear scan over <=10k events; index it if polls get hot.
            out = [e for e in self._d if e["seq"] > cursor][:limit]
            next_cursor = out[-1]["seq"] if out else cursor
            has_more = bool(self._d) and self._d[-1]["seq"] > next_cursor
            return {
                "events": out,
                "nextCursor": next_cursor,
                "hasMore": has_more,
                "dropped": self.dropped,
            }

    def clear(self):
        with self._lock:
            self._d.clear()


def resolve(dotted):
    """'pkg.mod.Class.method' -> the underlying function object, from the LIVE module."""
    parts = dotted.split(".")
    for i in range(len(parts), 0, -1):
        modname = ".".join(parts[:i])
        # Prefer an already-imported module: importing afresh builds a second module
        # object whose code we would arm while the running one keeps executing untrapped.
        obj = sys.modules.get(modname)
        if obj is None:
            try:
                obj = importlib.import_module(modname)
            except ImportError:
                continue
        obj = _prefer_main(obj)
        try:
            for attr in parts[i:]:
                obj = getattr(obj, attr)
        except AttributeError as exc:
            raise LookupError(f"{dotted}: {exc}") from None
        return obj
    raise LookupError(f"{dotted}: no importable module prefix{_shorter_name(parts)}")


def _shorter_name(parts):
    """A script run directly puts its own directory on sys.path, not the repo root, so
    `examples.toy_agent.f` is unimportable there while `toy_agent.f` resolves. Say so
    rather than leaving the caller to guess which prefix the target actually has."""
    tail, names = parts[-1], set(parts[:-1])
    for name, module in list(sys.modules.items()):
        if name.split(".")[-1] in names and hasattr(module, tail):
            return f" — the target has it as {name}.{tail}"
    return ""


def _prefer_main(mod):
    """A script launched directly runs as __main__. Importing it by its package name
    yields a different module whose functions never run, so traps on it never fire."""
    main = sys.modules.get("__main__")
    if main is None or main is mod:
        return mod
    path = getattr(mod, "__file__", None)
    if path and path == getattr(main, "__file__", None):
        return main
    return mod


def code_of(fn):
    """Unwrap decorators/descriptors down to a code object."""
    for attr in ("__func__", "__wrapped__"):
        while hasattr(fn, attr):
            fn = getattr(fn, attr)
    code = getattr(fn, "__code__", None)
    if code is None:
        raise LookupError(f"{fn!r} has no code object (builtin, or a class not a function?)")
    return code


class Trap:
    def __init__(self, trap_id, symbol, code, events, when=None, capture=None):
        self.id = trap_id
        self.symbol = symbol
        self.code = code
        self.events = events
        self.capture = capture
        self.hits = 0
        self.when_src = when
        self._when = compile(when, f"<trap {trap_id}>", "eval") if when else None
        self._when_errors = 0
        self.disarmed_reason = None

    def matches(self, frame_locals):
        if self._when is None:
            return True
        try:
            return bool(eval(self._when, {"__builtins__": {}}, dict(frame_locals)))
        except Exception as exc:
            self._when_errors += 1
            if self._when_errors >= 5:
                self.disarmed_reason = f"predicate failed 5x: {type(exc).__name__}: {exc}"
            return False

    def info(self):
        return {
            "trapId": self.id,
            "symbol": self.symbol,
            "events": sorted(self.events),
            "when": self.when_src,
            "capture": self.capture,
            "hits": self.hits,
            "disarmed": self.disarmed_reason,
        }


class Engine:
    def __init__(self, buffer=None, tool_id=None):
        self.buffer = buffer or Buffer()
        self.traps = {}
        self._by_code = {}
        self._ids = itertools.count(1)
        self._guard = threading.local()
        self.tool_id = self._claim_tool_id(tool_id)
        sys.monitoring.register_callback(self.tool_id, E.PY_START, self._on_call)
        sys.monitoring.register_callback(self.tool_id, E.PY_RETURN, self._on_return)
        sys.monitoring.register_callback(self.tool_id, E.RAISE, self._on_raise)

    @staticmethod
    def _claim_tool_id(tool_id):
        candidates = [tool_id] if tool_id is not None else [3, 4]
        for tid in candidates:
            try:
                sys.monitoring.use_tool_id(tid, "aitrap")
                return tid
            except ValueError:
                continue
        raise RuntimeError("no free sys.monitoring tool id")

    def arm(self, symbol, events=("call", "return"), when=None, capture=None):
        code = code_of(resolve(symbol))
        trap = Trap(next(self._ids), symbol, code, set(events), when, capture)
        self.traps[trap.id] = trap
        self._by_code.setdefault(code, []).append(trap)
        self._sync(code)
        return trap

    def disarm(self, trap_id):
        trap = self.traps.pop(trap_id, None)
        if trap is None:
            return False
        peers = self._by_code.get(trap.code, [])
        if trap in peers:
            peers.remove(trap)
        self._sync(trap.code)
        return True

    def close(self):
        """Release the sys.monitoring tool id and disarm everything."""
        for trap_id in list(self.traps):
            self.disarm(trap_id)
        sys.monitoring.free_tool_id(self.tool_id)

    def _sync(self, code):
        """Union the masks of every live trap on this code object."""
        mask = 0
        for trap in self._by_code.get(code, []):
            for name in trap.events:
                mask |= EVENT_MASKS[name]
        sys.monitoring.set_local_events(self.tool_id, code, mask)
        if not mask:
            self._by_code.pop(code, None)

    def _emit(self, code, kind, extra):
        if getattr(self._guard, "busy", False):
            return  # a predicate re-entered a trapped function; drop, don't recurse
        traps = self._by_code.get(code)
        if not traps:
            return
        self._guard.busy = True
        try:
            frame = sys._getframe(2)
            frame_locals = frame.f_locals
            for trap in list(traps):
                if kind not in trap.events or trap.disarmed_reason:
                    continue
                if not trap.matches(frame_locals):
                    continue
                trap.hits += 1
                event = {
                    "trapId": trap.id,
                    "kind": kind,
                    "symbol": trap.symbol,
                    "where": f"{code.co_filename}:{frame.f_lineno}",
                    "thread": threading.current_thread().name,
                    "task": _task_name(),
                    "ts": time.time(),
                    **extra(trap, frame),
                }
                self.buffer.push(event)
        finally:
            self._guard.busy = False

    def _on_call(self, code, offset):
        self._emit(code, "call", lambda t, f: {"locals": render.render_locals(f.f_locals, t.capture)})

    def _on_return(self, code, offset, retval):
        self._emit(code, "return", lambda t, f: {"returned": render.render(retval)})

    def _on_raise(self, code, offset, exc):
        self._emit(code, "raise", lambda t, f: {"exception": f"{type(exc).__name__}: {exc}"})


def _task_name():
    """asyncio task name if we're on a loop - AI agents are task-shaped, not thread-shaped."""
    try:
        import asyncio

        return asyncio.current_task().get_name()
    except Exception:
        return None
