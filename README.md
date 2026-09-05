# aitrap

**[Run it live in your browser →](https://riyadadlani02.github.io/aitrap/live/)** ·
**[Site →](https://riyadadlani02.github.io/aitrap/)** ·
**[Demo video →](https://riyadadlani02.github.io/aitrap/#video)**

Non-stopping runtime traps for live AI agent processes — so an AI coding agent can read **real
values** out of a running agent without freezing the agent it's debugging.

```bash
aitrap run -- python my_agent.py          # zero code changes to the target
aitrap trap --trapset livekit             # or: aitrap trap pkg.mod.Class.method
aitrap poll 0                             # JSON events, non-blocking
aitrap inspect 160                        # expand an object one level
```

## Install

Python 3.12 or newer — the whole design rests on `sys.monitoring`, which does not exist before
that. No dependencies outside the standard library.

```bash
pip install git+https://github.com/riyadadlani02/aitrap
uv pip install git+https://github.com/riyadadlani02/aitrap          # or with uv
pip install "aitrap[mcp] @ git+https://github.com/riyadadlani02/aitrap"   # with the MCP server
```

Not on PyPI yet. `.github/workflows/publish.yml` publishes on a `v*` tag once the name is claimed
there — PyPI trusted publishing, so there is no token to store.

**Or install nothing:** [run it live in your browser](https://riyadadlani02.github.io/aitrap/live/).
Pyodide is CPython 3.13 compiled to WebAssembly and `sys.monitoring` came with it, so the engine
runs unmodified in a tab — real traps, real captured values, no server anywhere.

## Why not just use a debugger

[mcp-debugger](https://github.com/debugmcp/mcp-debugger), [mcp-debugpy](https://github.com/markomanninen/mcp-debugpy)
and friends already give agents debugpy breakpoints over MCP. They all **stop the world**, and an AI
system can't survive that: pause a voice agent for 30s and the LLM request times out, the session
dies, the SIP leg drops. **Pausing destroys the bug you were chasing.** Three more mismatches:

- **Non-determinism** — the bug is on call #400. Nobody is sitting at a breakpoint at 2am.
- **Async** — the interesting frames are asyncio tasks, not threads. Events carry a `task` field.
- **Vocabulary** — you want "trap every tool call", not `agent.py:412`.

aitrap traps **capture and continue**. Built on `sys.monitoring` (PEP 669), armed per code object:

| | |
|---|---|
| Untrapped code | **0.94x** — noise |
| Trapped function | ~18ns/call — irrelevant at LLM/tool boundaries |
| Target process | never pauses, ever |

Need to actually step? Use mcp-debugger. This does the thing it can't.

## Live console

[Try it without installing anything](https://riyadadlani02.github.io/aitrap/live/) — the real
console, wired to a real aitrap engine running in your browser. Arm a trap on the checkout
pricing code, apply the coupon, and read the values that come back; tick *apply the fix* and
the same trap re-reads the repaired run. Nothing is recorded and nothing is served: it is
CPython 3.13 on WebAssembly, arming `sys.monitoring` traps in your tab.


The trap server serves a console at its own port — open it while the target runs:

```bash
open "http://127.0.0.1:$(cat ${TMPDIR:-/tmp}/aitrap.port)/"
```

A time axis that keeps advancing whether or not events arrive (the target is running the whole
time), the armed traps with hit counts, and the event stream. Click an event for its locals; click
a non-primitive to expand it from the live process.

## Demos

| | |
|---|---|
| [Checkout](https://riyadadlani02.github.io/aitrap/demo-phone/) | A coupon silently rejected because two functions disagree about the subtotal. Before/after the fix. |
| [Voice agent](https://riyadadlani02.github.io/aitrap/demo-voice/) | A LiveKit call filed against the wrong person because a matcher defaulted to `self`. Before/after the fix. |
| [Console](https://riyadadlani02.github.io/aitrap/demo/) | The console replaying ten recorded runs — the three story agents mid-bug ([LangGraph](https://riyadadlani02.github.io/aitrap/demo/?ds=langgraph_order), [OpenAI Agents](https://riyadadlani02.github.io/aitrap/demo/?ds=openai_agents_handoff), [Pydantic AI](https://riyadadlani02.github.io/aitrap/demo/?ds=pydantic_ai_billing)), plus — plain Python, plus every adapter through both doors: LangChain [sync](https://riyadadlani02.github.io/aitrap/demo/?ds=langchain) / [async](https://riyadadlani02.github.io/aitrap/demo/?ds=langchain_async), OpenAI Agents [async](https://riyadadlani02.github.io/aitrap/demo/?ds=openai_agents) / [run_sync](https://riyadadlani02.github.io/aitrap/demo/?ds=openai_agents_sync), Pydantic AI [async](https://riyadadlani02.github.io/aitrap/demo/?ds=pydantic_ai) / [run_sync](https://riyadadlani02.github.io/aitrap/demo/?ds=pydantic_ai_sync). |

Every state in them is a real capture from `examples/`, in both the broken and repaired form.
Each demo agent ships broken on purpose, with one env var that applies the repair, so the before
and after are both recordable from one file:

| example | the bug | repaired by |
|---|---|---|
| `checkout_app/backend.py` | min-spend checked against the post-discount subtotal | `CHECKOUT_FIXED=1` |
| `voice_agent.py` | relationship matcher only accepts a bare word, defaults to `self` | `VOICE_FIXED=1` |
| `langgraph_order_agent.py` | reply node prompts the model without the tool's result | `LANGGRAPH_FIXED=1` |
| `openai_agents_handoff_agent.py` | handoff forwards a summary that drops the customer's £50 cap | `HANDOFF_FIXED=1` |
| `pydantic_ai_billing_agent.py` | pence handed to a tool that takes pounds — £49.99 credited as £4,999 | `BILLING_FIXED=1` |

None of them raise, and every transcript reads like a working agent. The wrong value is only
visible in the frame. Regenerate the framework
recordings (no API keys) with `python scripts/record_timeline.py`.

## Trap sets

Semantic hooks instead of line numbers. Adapters are JSON data, not code.

```bash
aitrap trap --trapset livekit --hook on-tool-call
aitrap probe                 # which symbols resolve against what's installed
```

| Adapter | Hooks | Verified against |
|---|---|---|
| `livekit` | on-tool-call, on-llm-request, on-handoff, on-user-turn | livekit-agents 1.6.6, on a live production voice agent — 7/7 |
| `langchain` | on-agent-run, on-llm-request, on-tool-call, on-state-write | langchain-core 1.6.2 + langgraph — 9/9 across sync + async |
| `openai_agents` | on-agent-run, on-turn, on-llm-request, on-tool-call, on-handoff | openai-agents 0.22.0 — 6/6 async, 5/6 through `Runner.run_sync` |
| `pydantic_ai` | on-agent-run, on-llm-request, on-tool-call | pydantic-ai 2.40.0 — 4/4 both ways |

Every symbol above was observed **firing** against a running agent, not merely resolving — a
symbol can resolve and never be called, which is how a trapset rots silently when a framework
moves a function. Sync and async are recorded separately because they are not the same code path:
LangChain's four `a*` symbols never fire in a synchronous graph, and `Runner.run` never fires when
the OpenAI Agents SDK is entered through `run_sync`. Reproduce it yourself, no API keys needed:

```bash
python scripts/verify_trapset.py            # all four, against examples/
```

Run `aitrap probe <name>` before trusting an unverified adapter, or after a framework upgrade.
PRs fixing symbols welcome.

## Capture safety

- **`__repr__` is never called on unknown types.** A repr can be slow, raise on a half-built object,
  or touch network state on a live session. Primitives inline; everything else gets an `objectId`
  you expand on demand, held by weakref so aitrap never keeps your objects alive.
- **PII redaction is on by default**, applied *at capture time* — dates of birth, names, emails,
  government IDs, tokens and friends never enter the buffer an LLM reads. Widen with `--redact`.
- **Drops are reported.** `poll` returns `dropped`; a tool that silently loses events while implying
  full coverage is worse than no tool.
- **Redaction is key-based, not value-based.** A PII-shaped key is caught; a DOB buried inside a
  free-text value is not. Don't point aitrap at a process and assume the buffer is safe to paste.
- **Objects expire.** `inspect` reaches the last `AITRAP_RECENT_OBJECTS` (default 256) captured
  objects; older ones say so rather than lying. Raising it pins that many live objects in memory.

## Conditional traps

The "only capture on call #400" feature — a predicate over the function's locals:

```bash
aitrap trap myapp.pricing.evaluate_promo --when "base_amount < coupon.min_spend"
```

A predicate that raises 5 times disarms itself rather than spinning in the hot path.

## MCP

```bash
pip install "aitrap[mcp]" && aitrap-mcp
```

Same core as the CLI: `trap`, `poll`, `inspect`, `traps`, `untrap`, `probe`.

## Getting in

1. `aitrap run -- python agent.py` — wrapper, no target changes
2. `PYTHONPATH=.../aitrap/_shim` — for containers you don't launch yourself
3. `import aitrap; aitrap.serve()` — when you own the entrypoint

## Limits

- **Python 3.12+.** No `sys.monitoring` below that.
- **No attach to an already-running PID.** Entry is at process start. The main thing to fix next.
- **One process, one port.** Distributed workers each need their own.

## Tests

```bash
python tests/test_aitrap.py     # or: pytest tests/
```

MIT.
