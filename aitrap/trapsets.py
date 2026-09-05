"""Framework adapters: semantic hook names -> concrete symbols. Data, not code."""
import json
import pathlib

from .engine import code_of, resolve

DIR = pathlib.Path(__file__).parent / "trapsets"


def available():
    return sorted(p.stem for p in DIR.glob("*.json"))


def load(name):
    path = DIR / f"{name}.json"
    if not path.exists():
        raise LookupError(f"unknown trapset {name!r}; have: {', '.join(available())}")
    return json.loads(path.read_text())


def symbols_for(name, hook=None):
    """-> [(symbol, capture_list_or_None)] for one hook, or every hook in the set."""
    spec = load(name)
    hooks = spec["hooks"]
    if hook:
        if hook not in hooks:
            raise LookupError(f"{name} has no hook {hook!r}; have: {', '.join(hooks)}")
        hooks = {hook: hooks[hook]}
    out = []
    for entry in (e for h in hooks.values() for e in h):
        out.append((entry["symbol"], entry.get("capture")))
    return out


def probe(name=None):
    """Resolve every symbol against what's installed. Blind adapters must self-check."""
    results = {}
    for set_name in [name] if name else available():
        spec = load(set_name)
        hooks = {}
        for hook, entries in spec["hooks"].items():
            checked = []
            for entry in entries:
                try:
                    code_of(resolve(entry["symbol"]))
                    checked.append({"symbol": entry["symbol"], "ok": True})
                except Exception as exc:
                    checked.append({"symbol": entry["symbol"], "ok": False, "error": str(exc)})
            hooks[hook] = checked
        ok = sum(c["ok"] for h in hooks.values() for c in h)
        total = sum(len(h) for h in hooks.values())
        results[set_name] = {"package": spec.get("package"), "resolved": f"{ok}/{total}", "hooks": hooks}
    return results
