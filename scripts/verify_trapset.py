"""Prove a trapset actually FIRES against a running agent, not merely that it resolves.

    python scripts/verify_trapset.py langchain examples/langchain_agent.py

Resolving is not verification: a symbol can resolve and still never be called, which is
exactly how a trapset rots when a framework moves a function. This launches the agent
under aitrap, arms the trapset by name, and reports hits per symbol.
"""
import json, os, pathlib, subprocess, sys, tempfile, time, urllib.error, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORTFILE = pathlib.Path(tempfile.gettempdir()) / "aitrap.port"

DEFAULT_RUNS = [
    ("langchain", "examples/langchain_agent.py"),
    ("langchain", "examples/langchain_async_agent.py"),
    ("openai_agents", "examples/openai_agents_agent.py"),
    ("openai_agents", "examples/openai_agents_sync_agent.py"),
    ("pydantic_ai", "examples/pydantic_ai_agent.py"),
    ("pydantic_ai", "examples/pydantic_ai_sync_agent.py"),
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


def verify(trapset, script, rounds=3):
    PORTFILE.unlink(missing_ok=True)
    env = {**os.environ, "ARM_WAIT": "9", "ROUNDS": str(rounds), "HOLD": "22"}
    proc = subprocess.Popen([sys.executable, "-m", "aitrap.cli", "run", "--",
                             sys.executable, str(ROOT / script)], env=env, cwd=ROOT,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            if PORTFILE.exists():
                break
            time.sleep(0.5)
        else:
            print(f"  {script}: target never announced a port")
            return 0, 0
        port = PORTFILE.read_text().strip()
        time.sleep(1.5)
        armed = api(port, "POST", "/trap", {"trapset": trapset, "events": ["call"]})
        time.sleep(15)
        traps = api(port, "GET", "/traps").get("traps", [])
    finally:
        proc.terminate()

    fired = [t for t in traps if t["hits"]]
    print(f"\n--trapset {trapset}   ({script})")
    print(f"  armed {len(armed.get('armed', []))}  failed {len(armed.get('failed', []))}  "
          f"fired {len(fired)}/{len(traps)}")
    for t in sorted(traps, key=lambda t: -t["hits"]):
        print(f"   {t['hits']:>3}x  {t['symbol']}" if t["hits"] else f"      ·  {t['symbol']}")
    for f in armed.get("failed", []):
        print(f"   FAIL  {f['symbol']}: {f['error'][:70]}")
    return len(fired), len(traps)


if __name__ == "__main__":
    runs = [(sys.argv[1], sys.argv[2])] if len(sys.argv) > 2 else DEFAULT_RUNS
    fired = armed = 0
    for trapset, script in runs:
        f, a = verify(trapset, script)
        fired += f; armed += a
    print(f"\nfired {fired} of {armed} armed symbols")
