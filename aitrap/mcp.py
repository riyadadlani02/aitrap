"""MCP frontend. Same HTTP core as the CLI - no logic duplicated here."""
from mcp.server.fastmcp import FastMCP

from .cli import _port, call

mcp = FastMCP("aitrap")


@mcp.tool()
def trap(symbol: str = "", trapset: str = "", hook: str = "", when: str = "",
         events: str = "call,return", port: int = 0) -> dict:
    """Arm a non-stopping trap. Give a dotted `symbol`, or a `trapset` (livekit,
    langchain, openai_agents) with an optional `hook` like on-tool-call.
    `when` is a predicate over the function's locals, e.g. 'total > 600'.
    The target process is never paused."""
    body = {"events": events.split(","), "when": when or None}
    if trapset:
        body["trapset"], body["hook"] = trapset, hook or None
    else:
        body["symbol"] = symbol
    return call(_port(port or None), "POST", "/trap", body)


@mcp.tool()
def poll(cursor: int = 0, limit: int = 100, port: int = 0) -> dict:
    """Drain captured events since `cursor`. Non-blocking: returns immediately with
    {events, nextCursor, hasMore, dropped}. Pass nextCursor back on the next call.
    A non-zero `dropped` means the ring buffer overflowed and events were lost."""
    return call(_port(port or None), "GET", f"/poll?cursor={cursor}&limit={limit}")


@mcp.tool()
def inspect(object_id: int, port: int = 0) -> dict:
    """Expand a non-primitive value one level, using an objectId from a poll result."""
    return call(_port(port or None), "GET", f"/inspect?objectId={object_id}")


@mcp.tool()
def traps(port: int = 0) -> dict:
    """List armed traps with hit counts and any self-disarm reason."""
    return call(_port(port or None), "GET", "/traps")


@mcp.tool()
def untrap(trap_id: int, port: int = 0) -> dict:
    """Disarm one trap."""
    return call(_port(port or None), "DELETE", f"/trap/{trap_id}")


@mcp.tool()
def probe(name: str = "", port: int = 0) -> dict:
    """Check which trapset symbols resolve against the frameworks actually installed
    in the target. Run this first when a trapset arms nothing."""
    return call(_port(port or None), "GET", f"/probe?name={name}")


def main():
    mcp.run()


if __name__ == "__main__":
    main()
