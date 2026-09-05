"""aitrap CLI - a dumb HTTP client plus the `run` launcher. No logic lives here."""
import argparse
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

PORTFILE = pathlib.Path(tempfile.gettempdir()) / "aitrap.port"


def _port(explicit=None):
    if explicit:
        return explicit
    if os.environ.get("AITRAP_PORT"):
        return int(os.environ["AITRAP_PORT"])
    if PORTFILE.exists():
        return int(PORTFILE.read_text().strip())
    sys.exit("no target port: pass --port, or launch with `aitrap run`")


def call(port, method, path, body=None):
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        return json.load(exc)
    except OSError as exc:
        sys.exit(f"cannot reach target on 127.0.0.1:{port}: {exc}")


def cmd_run(args):
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        sys.exit("usage: aitrap run -- <command...>")
    pkg = pathlib.Path(__file__).resolve().parent
    env = dict(os.environ)
    # pkg.parent keeps aitrap importable when running from a checkout, not just an install.
    env["PYTHONPATH"] = os.pathsep.join(
        [str(pkg / "_shim"), str(pkg.parent), *filter(None, [env.get("PYTHONPATH")])]
    )
    env["AITRAP_PORT"] = str(args.port)
    env["AITRAP_PORTFILE"] = str(PORTFILE)
    PORTFILE.unlink(missing_ok=True)
    return subprocess.call(command, env=env)


def cmd_trap(args):
    body = {"events": args.events.split(","), "when": args.when}
    if args.capture:
        body["capture"] = args.capture.split(",")
    if args.trapset:
        body["trapset"], body["hook"] = args.trapset, args.hook
    else:
        body["symbol"] = args.symbol
    return call(_port(args.port), "POST", "/trap", body)


def cmd_poll(args):
    port, cursor = _port(args.port), args.cursor
    while True:
        out = call(port, "GET", f"/poll?cursor={cursor}&limit={args.limit}")
        if out.get("events") or not args.follow:
            print(json.dumps(out, indent=2))
        if not args.follow:
            return out
        cursor = out.get("nextCursor", cursor)
        time.sleep(args.interval)


COMMANDS = {
    "inspect": lambda a: call(_port(a.port), "GET", f"/inspect?objectId={a.object_id}"),
    "traps": lambda a: call(_port(a.port), "GET", "/traps"),
    "untrap": lambda a: call(_port(a.port), "DELETE", f"/trap/{a.trap_id}"),
    "clear": lambda a: call(_port(a.port), "DELETE", "/events"),
    "trapsets": lambda a: call(_port(a.port), "GET", "/trapsets"),
    "probe": lambda a: call(_port(a.port), "GET", f"/probe?name={a.name or ''}"),
}


def main(argv=None):
    p = argparse.ArgumentParser(prog="aitrap", description=__doc__)
    p.add_argument("--port", type=int, help="target control port")
    sub = p.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="launch a process with aitrap installed")
    run.add_argument("--port", type=int, default=0)
    run.add_argument("command", nargs=argparse.REMAINDER)

    trap = sub.add_parser("trap", help="arm a trap")
    trap.add_argument("symbol", nargs="?", help="dotted symbol, e.g. pkg.mod.Class.method")
    trap.add_argument("--trapset", help="framework adapter, e.g. livekit")
    trap.add_argument("--hook", help="one hook from the trapset, e.g. on-tool-call")
    trap.add_argument("--when", help="predicate over locals, e.g. 'total > 600'")
    trap.add_argument("--capture", help="comma-separated locals to keep")
    trap.add_argument("--events", default="call,return", help="call,return,raise")

    poll = sub.add_parser("poll", help="drain captured events (non-blocking)")
    poll.add_argument("cursor", nargs="?", type=int, default=0)
    poll.add_argument("--limit", type=int, default=100)
    poll.add_argument("--follow", action="store_true")
    poll.add_argument("--interval", type=float, default=2.0)

    sub.add_parser("traps", help="list armed traps")
    sub.add_parser("clear", help="drop buffered events")
    sub.add_parser("trapsets", help="list adapters")
    sub.add_parser("inspect", help="expand an objectId").add_argument("object_id", type=int)
    sub.add_parser("untrap", help="disarm a trap").add_argument("trap_id", type=int)
    sub.add_parser("probe", help="check adapter symbols resolve").add_argument("name", nargs="?")

    args = p.parse_args(argv)
    if args.cmd == "run":
        return cmd_run(args)
    result = cmd_trap(args) if args.cmd == "trap" else (
        cmd_poll(args) if args.cmd == "poll" else COMMANDS[args.cmd](args)
    )
    if args.cmd != "poll":
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
