"""Value rendering for captured frames: safe, bounded, redacted."""
import collections
import os
import re
import weakref

PRIMITIVES = (bool, int, float, str, bytes, type(None))
CONTAINERS = (dict, list, tuple, set, frozenset)

MAX_DEPTH = 2
MAX_STR = 200
MAX_ITEMS = 25

# Redaction is ON by default: agent state routinely holds end-user PII.
DEFAULT_REDACT = re.compile(
    r"nhs|dob|birth|passw|token|secret|api_?key|ssn|phone|mobile|postcode|"
    r"first_?name|last_?name|full_?name|surname|patient|email|address|credential|auth",
    re.I,
)
REDACTED = "«redacted»"

# WeakValueDictionary alone loses the object before an agent gets round to inspecting it:
# in a live async agent the frame's objects are collected the moment the turn ends. The
# deque pins the most recent RECENT_OBJECTS so deferred inspect works, with bounded memory.
# ponytail: fixed-size pin; make it configurable if someone traps very large objects.
# Deliberately small: these are STRONG references into a live process, and an agent's
# frames hold chat contexts. Raise it when you need to inspect further back, and accept
# that you are keeping that many objects alive.
RECENT_OBJECTS = int(os.environ.get("AITRAP_RECENT_OBJECTS", 256))
_registry: "weakref.WeakValueDictionary[int, object]" = weakref.WeakValueDictionary()
_recent = collections.deque(maxlen=RECENT_OBJECTS)
_next_id = [1]


def register(obj):
    try:
        oid = _next_id[0]
        _registry[oid] = obj
    except TypeError:
        return None  # not weakref-able
    _recent.append(obj)
    _next_id[0] += 1
    return oid


def lookup(object_id):
    return _registry.get(object_id)


def _truncate(s):
    return s if len(s) <= MAX_STR else s[:MAX_STR] + f"…(+{len(s) - MAX_STR})"


def render(value, depth=0, redact=DEFAULT_REDACT):
    """Render one value. Never calls __repr__ on unknown types."""
    if isinstance(value, PRIMITIVES):
        v = value
        if isinstance(v, (str, bytes)):
            v = _truncate(v.decode("utf-8", "replace") if isinstance(v, bytes) else v)
        return {"type": type(value).__name__, "value": v, "isPrimitive": True}

    if isinstance(value, CONTAINERS) and depth < MAX_DEPTH:
        if isinstance(value, dict):
            items, extra = list(value.items())[:MAX_ITEMS], max(0, len(value) - MAX_ITEMS)
            out = {
                str(k): (
                    {"type": type(v).__name__, "value": REDACTED, "isPrimitive": True}
                    if redact and redact.search(str(k))
                    else render(v, depth + 1, redact)
                )
                for k, v in items
            }
            return {"type": "dict", "value": out, "truncated": extra, "isPrimitive": False}
        seq = list(value)[:MAX_ITEMS]
        return {
            "type": type(value).__name__,
            "value": [render(v, depth + 1, redact) for v in seq],
            "truncated": max(0, len(value) - MAX_ITEMS),
            "isPrimitive": False,
        }

    cls = type(value)
    return {
        "type": f"{cls.__module__}.{cls.__qualname__}",
        "objectId": register(value),
        "isPrimitive": False,
    }


def render_locals(frame_locals, capture=None, redact=DEFAULT_REDACT):
    """Render a frame's locals, dropping `self`/`cls` noise and applying redaction."""
    out = {}
    for name, value in frame_locals.items():
        if capture and name not in capture:
            continue
        if name in ("self", "cls") and not capture:
            continue
        if redact and redact.search(name):
            out[name] = {"type": type(value).__name__, "value": REDACTED, "isPrimitive": True}
        else:
            out[name] = render(value, 0, redact)
    return out


def expand(object_id, redact=DEFAULT_REDACT):
    """Expand one registered object, one level deep."""
    obj = lookup(object_id)
    if obj is None:
        return {
            "error": f"objectId {object_id} is gone: collected, or older than the last "
                     f"{RECENT_OBJECTS} captured objects"
        }
    fields = getattr(obj, "__dict__", None)
    if fields is None:
        fields = {s: getattr(obj, s, None) for s in getattr(type(obj), "__slots__", ())}
    cls = type(obj)
    return {
        "objectId": object_id,
        "type": f"{cls.__module__}.{cls.__qualname__}",
        "fields": render_locals(dict(fields), None, redact),
    }
