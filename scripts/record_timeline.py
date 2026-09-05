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

RUNS = [  # name, trapset, script
    ("langchain", "langchain", "examples/langchain_agent.py"),
    ("openai_agents", "openai_agents", "examples/openai_agents_agent.py"),
    ("pydantic_ai", "pydantic_ai", "examples/pydantic_ai_agent.py"),
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
    out.write_text(json.dumps({"events": events, "objects": objects}))
    print(f"{name:>14}  {len(events):>4} events  {fired}/{len(traps)} symbols fired  "
          f"{len(objects)} objects  -> {out.relative_to(ROOT)}  "
          f"({len(armed.get('failed', []))} failed to arm)")
    for f in armed.get("failed", []):
        print(f"                FAILED {f['symbol']}: {f['error'][:70]}")
    return len(events)


if __name__ == "__main__":
    runs = [(sys.argv[1], sys.argv[1], sys.argv[2])] if len(sys.argv) > 2 else RUNS
    for name, trapset, script in runs:
        record(name, trapset, script)
