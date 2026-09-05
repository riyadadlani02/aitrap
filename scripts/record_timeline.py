"""Record a real run of an example agent into a replayable timeline for the site.

    python scripts/record_timeline.py langchain examples/langchain_agent.py langchain

Launches the example under aitrap, arms the trapset by name, drains the event buffer and
expands every objectId the events reference, so the hosted console can replay clicks into
objects exactly as the live one does. Nothing here is hand-written: the JSON is whatever
the running agent produced.
"""
import json, os, pathlib, subprocess, sys, tempfile, time, urllib.error, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "demo"
PORTFILE = pathlib.Path(tempfile.gettempdir()) / "aitrap.port"
DEPTH = 2  # levels of object expansion kept for the replay

RUNS = [  # name, trapset, script — every adapter through both doors, sync and async
    ("langchain", "langchain", "examples/langchain_agent.py"),
    ("langchain_async", "langchain", "examples/langchain_async_agent.py"),
    ("openai_agents", "openai_agents", "examples/openai_agents_agent.py"),
    ("openai_agents_sync", "openai_agents", "examples/openai_agents_sync_agent.py"),
    ("pydantic_ai", "pydantic_ai", "examples/pydantic_ai_agent.py"),
    ("pydantic_ai_sync", "pydantic_ai", "examples/pydantic_ai_sync_agent.py"),
]


STORIES = [  # name, trapset, script, the env var that repairs it, extra symbols to arm
    ("langgraph_order", "langchain", "examples/langgraph_order_agent.py", "LANGGRAPH_FIXED",
     ["examples.langgraph_order_agent.reply_node"]),
    ("openai_agents_handoff", "openai_agents", "examples/openai_agents_handoff_agent.py",
     "HANDOFF_FIXED", ["examples.openai_agents_handoff_agent.decide_replacement"]),
    ("pydantic_ai_billing", "pydantic_ai", "examples/pydantic_ai_billing_agent.py",
     "BILLING_FIXED", ["examples.pydantic_ai_billing_agent.credit_for",
                       "examples.pydantic_ai_billing_agent.issue_credit"]),
]


def api(port, method, path, body=None):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method=method,
        data=json.dumps(body).encode() if body else None,
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return json.load(e)


def record(name, trapset, script, rounds=4, watch=18, max_objects=1200):
    PORTFILE.unlink(missing_ok=True)
    # Pin generously: the site replays clicks into objects captured minutes earlier, which the
    # live default (256) would have let go.
    env = {**os.environ, "ARM_WAIT": "9", "ROUNDS": str(rounds), "HOLD": str(watch + 6),
           "AITRAP_RECENT_OBJECTS": "6000"}
    py = sys.executable
    proc = subprocess.Popen([py, "-m", "aitrap.cli", "run", "--", py,
                             str(ROOT / script)], env=env, cwd=ROOT,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            if PORTFILE.exists():
                break
            time.sleep(0.5)
        else:
            sys.exit(f"{script}: target never announced a port")
        port = PORTFILE.read_text().strip()
        time.sleep(1.5)

        armed = api(port, "POST", "/trap", {"trapset": trapset, "events": ["call"]})
        time.sleep(watch)

        events, cursor = [], 0
        while True:
            page = api(port, "GET", f"/poll?cursor={cursor}&limit=200")
            batch = page.get("events", [])
            events += batch
            cursor = page.get("nextCursor", cursor)
            if not batch or not page.get("hasMore"):
                break

        # Expand breadth-first to DEPTH levels so a visitor can click down into an object,
        # not just open the first one. Unbounded, this walks the whole agent heap.
        queue = [(v["objectId"], 0) for e in events for v in e.get("locals", {}).values()
                 if v.get("objectId")]
        objects = {}
        while queue and len(objects) < max_objects:
            oid, depth = queue.pop(0)
            if str(oid) in objects:
                continue
            got = api(port, "GET", f"/inspect?objectId={oid}")
            objects[str(oid)] = got
            if depth < DEPTH:
                queue += [(f["objectId"], depth + 1)
                          for f in (got.get("fields") or {}).values()
                          if isinstance(f, dict) and f.get("objectId")]
        traps = api(port, "GET", "/traps").get("traps", [])
    finally:
        proc.terminate()

    fired = sum(1 for t in traps if t["hits"])
    out = OUT / f"{name}.json"
    out.write_text(json.dumps({"events": events, "objects": objects,
                               "meta": {"script": script, "trapset": trapset,
                                        "armed": len(traps), "fired": fired}}))
    print(f"{name:>14}  {len(events):>4} events  {fired}/{len(traps)} symbols fired  "
          f"{len(objects)} objects  -> {out.relative_to(ROOT)}  "
          f"({len(armed.get('failed', []))} failed to arm)")
    for f in armed.get("failed", []):
        print(f"                FAILED {f['symbol']}: {f['error'][:70]}")
    return len(events)


def record_story(name, trapset, script, fixed_env=None, symbols=(), rounds=3, watch=14):
    """One pass over a story agent: arm the trapset plus the example's own functions, keep
    call and return, and keep the printed transcript alongside the frames."""
    PORTFILE.unlink(missing_ok=True)
    py = sys.executable
    env = {**os.environ, "ARM_WAIT": "9", "ROUNDS": str(rounds), "HOLD": str(watch + 6),
           "AITRAP_RECENT_OBJECTS": "6000"}
    if fixed_env:
        env[fixed_env] = "1"
    proc = subprocess.Popen([py, "-m", "aitrap.cli", "run", "--", py, str(ROOT / script)],
                            env=env, cwd=ROOT, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, text=True)
    try:
        for _ in range(60):
            if PORTFILE.exists():
                break
            time.sleep(0.5)
        else:
            sys.exit(f"{script}: target never announced a port")
        port = PORTFILE.read_text().strip()
        time.sleep(1.5)
        api(port, "POST", "/trap", {"trapset": trapset, "events": ["call", "return"]})
        for sym in symbols:
            api(port, "POST", "/trap", {"symbol": sym, "events": ["call", "return"]})
        time.sleep(watch)
        events, cursor = [], 0
        while True:
            page = api(port, "GET", f"/poll?cursor={cursor}&limit=300")
            batch = page.get("events", [])
            events += batch
            cursor = page.get("nextCursor", cursor)
            if not batch or not page.get("hasMore"):
                break
    finally:
        proc.terminate()
        out = proc.stdout.read() if proc.stdout else ""
    transcript = [l.strip() for l in out.splitlines() if l.startswith("  [")]
    return events, transcript[:4]


def record_stories(path=ROOT / "scripts" / "video" / "stories.json"):
    """Both states of each story agent, trimmed to what the video scenes show."""
    stories = []
    for name, trapset, script, fixed_env, symbols in STORIES:
        state = {}
        for label, env in (("broken", None), ("fixed", fixed_env)):
            events, transcript = record_story(name, trapset, script, env, symbols)
            state[label] = {"frames": [{"kind": e["kind"], "symbol": e["symbol"],
                                        "locals": {k: v for k, v in (e.get("locals") or {}).items()
                                                   if v.get("isPrimitive")},
                                        "returned": e.get("returned")}
                                       for e in events],
                            "transcript": transcript}
            print(f"{name + '/' + label:>30}  {len(events)} events  {len(transcript)} spoken lines")
        stories.append({"name": name, "trapset": trapset, "script": script, **state})
    path.write_text(json.dumps({"stories": stories}))
    print(f"{'stories':>18}  {len(stories)} -> {path.relative_to(ROOT)}")


# Panel copy for the video's adapter scene. The counts and frames under it are read back
# out of the recordings, never typed here.
VIDEO_PANELS = [
    ("langchain", "langchain", "sync"),
    ("langchain_async", "langchain", "async"),
    ("openai_agents", "openai_agents", "async"),
    ("openai_agents_sync", "openai_agents", "run_sync"),
    ("pydantic_ai", "pydantic_ai", "async"),
    ("pydantic_ai_sync", "pydantic_ai", "run_sync"),
]


def build_video_data(path=ROOT / "scripts" / "video" / "frameworks.json", per_panel=5):
    """Trim the recordings down to what the video scene shows: a few frames each, plus the
    symbols that stayed silent on that door — read from the adapter, not typed by hand."""
    panels = []
    for name, adapter, door in VIDEO_PANELS:
        d = json.loads((OUT / f"{name}.json").read_text())
        armed = [h["symbol"] for hooks in
                 json.loads((ROOT / "aitrap" / "trapsets" / f"{adapter}.json").read_text())
                 ["hooks"].values() for h in hooks]
        rang = {e["symbol"] for e in d["events"]}
        seen, frames = set(), []
        for e in d["events"]:
            if e["symbol"] in seen or len(frames) >= per_panel:
                continue
            seen.add(e["symbol"])
            frames.append({"kind": e["kind"], "symbol": e["symbol"], "task": e.get("task"),
                           "locals": {k: v for k, v in (e.get("locals") or {}).items()
                                      if v.get("isPrimitive")}})
        panels.append({"name": name, "adapter": adapter, "door": door, "frames": frames,
                       "silent": [a for a in armed if a not in rang], **d["meta"]})
    path.write_text(json.dumps({"panels": panels}))
    print(f"{'video':>18}  {len(panels)} panels -> {path.relative_to(ROOT)}")


if __name__ == "__main__":
    runs = [(sys.argv[1], sys.argv[1], sys.argv[2])] if len(sys.argv) > 2 else RUNS
    for name, trapset, script in runs:
        record(name, trapset, script)
    if len(runs) == len(RUNS):
        build_video_data()
        record_stories()
