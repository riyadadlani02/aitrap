"""Runnable with `pytest tests/` or plain `python tests/test_aitrap.py`."""
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aitrap import render
from aitrap.engine import Buffer, Engine


# --- the video's bug, reproduced from live values with no pause -------------
def calculate_order(gross_subtotal, member_discount):
    net_subtotal = gross_subtotal - member_discount
    return evaluate_promo(net_subtotal)  # the bug: net passed where gross was owed


def evaluate_promo(base_amount, min_spend=600.0):
    return 0.0 if base_amount < min_spend else base_amount * 0.15


def untrapped_sibling(x):
    return x * 2


def test_captures_locals_and_return_without_pausing():
    e = Engine(Buffer())
    try:
        e.arm(f"{__name__}.evaluate_promo", events=("call", "return"))
        t0 = time.perf_counter()
        calculate_order(628.49, 62.85)
        untrapped_sibling(3)
        elapsed = time.perf_counter() - t0

        events = e.buffer.poll(0)["events"]
        call, ret = events[0], events[1]
        assert call["locals"]["base_amount"]["value"] == 565.64, call
        assert call["locals"]["min_spend"]["value"] == 600.0
        assert ret["returned"]["value"] == 0.0  # promo silently lost
        assert not any("untrapped_sibling" in ev["symbol"] for ev in events)
        assert elapsed < 0.5, "traps must not block the caller"
    finally:
        e.close()


def test_untrapped_code_pays_nothing():
    def hot(x):
        return x + 1

    def bench():
        t0 = time.perf_counter()
        for i in range(100_000):
            hot(i)
        return time.perf_counter() - t0

    baseline = min(bench() for _ in range(3))
    e = Engine(Buffer())
    try:
        e.arm(f"{__name__}.evaluate_promo")
        armed = min(bench() for _ in range(3))
    finally:
        e.close()
    ratio = armed / baseline
    assert ratio < 1.25, f"untrapped code slowed to {ratio:.2f}x - the core claim is broken"


def test_overflow_is_reported_not_hidden():
    b = Buffer(maxlen=10)
    for i in range(25):
        b.push({"kind": "call"})
    out = b.poll(0)
    assert out["dropped"] == 15, out
    assert len(out["events"]) == 10


def test_pii_is_redacted_at_capture_time():
    rendered = render.render_locals(
        {"userdata": {"ssn": "078-05-1120", "dob": "1984-03-02", "reason": "order not delivered"}}
    )
    blob = json.dumps(rendered)
    assert "078-05-1120" not in blob and "1984-03-02" not in blob, blob
    assert "order not delivered" in blob, "redaction must not eat non-PII"


def test_predicate_gates_capture_and_auto_disarms():
    e = Engine(Buffer())
    try:
        e.arm(f"{__name__}.evaluate_promo", events=("call",), when="base_amount > 600")
        evaluate_promo(100.0)
        evaluate_promo(700.0)
        events = e.buffer.poll(0)["events"]
        assert len(events) == 1 and events[0]["locals"]["base_amount"]["value"] == 700.0

        bad = e.arm(f"{__name__}.untrapped_sibling", events=("call",), when="nope_undefined")
        for i in range(6):
            untrapped_sibling(i)
        assert bad.disarmed_reason, "a broken predicate must disarm itself"
    finally:
        e.close()


def test_http_control_plane_end_to_end():
    from aitrap.server import serve

    e = Engine(Buffer())
    try:
        port = serve(e, 0)
        get = lambda p: json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}{p}", timeout=5))

        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/trap",
            data=json.dumps({"symbol": f"{__name__}.evaluate_promo"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        assert len(json.load(urllib.request.urlopen(req, timeout=5))["armed"]) == 1

        evaluate_promo(565.64)
        first = get("/poll?cursor=0&limit=1")
        assert first["events"] and first["hasMore"] is True
        rest = get(f"/poll?cursor={first['nextCursor']}")
        assert rest["events"] and rest["hasMore"] is False
        assert get("/traps")["traps"][0]["hits"] == 2
    finally:
        e.close()


def test_recent_objects_survive_collection():
    """The failure a real agent run exposed: the frame's object is collected before
    the agent polls, so a weakref-only registry always answers 'not found'."""

    class Coupon:
        def __init__(self):
            self.code, self.min_spend = "TECH15", 600.0

    def make_and_drop():
        return render.render(Coupon())["objectId"]

    oid = make_and_drop()  # the Coupon has no live reference left
    import gc

    gc.collect()
    assert render.expand(oid)["fields"]["code"]["value"] == "TECH15", render.expand(oid)


def test_symbol_in_the_running_script_resolves_to_the_live_module():
    """Arming `pkg.script.fn` while that script runs as __main__ must hit the live code,
    not a second copy created by importing it — that silently captures nothing."""
    import types

    main = sys.modules["__main__"]
    fake = types.ModuleType("fake_pkg_module")
    fake.__file__ = getattr(main, "__file__", __file__)
    sys.modules["fake_pkg_module"] = fake
    try:
        from aitrap.engine import resolve

        assert resolve("fake_pkg_module.evaluate_promo") is evaluate_promo
    finally:
        del sys.modules["fake_pkg_module"]


def test_livekit_trapset_resolves():
    from aitrap import trapsets

    result = trapsets.probe("livekit")["livekit"]
    ok, total = result["resolved"].split("/")
    assert ok == total, result


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
    print("\nall checks passed")
