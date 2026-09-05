"""A LiveKit voice agent you can trap, driven by a scripted model. No API keys, no audio.

    aitrap run -- python examples/voice_agent.py
    aitrap trap --trapset livekit --hook on-tool-call
    aitrap trap examples.voice_agent.normalise_relationship
    aitrap poll 0

The bug is the one voice systems actually get wrong: the caller is ringing about somebody
else, and the intake step quietly decides they mean themselves. Nothing errors, nothing logs,
and the call proceeds against the wrong person's account. You only see it in the arguments
the tool was handed.
"""
import asyncio
import os
import uuid

from livekit.agents import Agent, AgentSession, function_tool, llm
from livekit.agents.testing import fake_job_context

ACCOUNTS = {"self": "AC-1001 (the caller)", "mother": "AC-2277 (Jean Whitfield)"}
KNOWN = ("mother", "father", "son", "daughter", "partner", "self")

# Ships broken on purpose. VOICE_FIXED=1 applies the repair so both states can be recorded.
FIXED = os.environ.get("VOICE_FIXED") == "1"


def normalise_relationship(spoken: str) -> str:
    """Map what the caller said onto a relationship we store."""
    word = spoken.strip().lower()
    if FIXED:
        return next((k for k in KNOWN if k in word), "self")
    # The bug: only an exact single word matches, so "for my mother" falls through to the
    # default. Real callers never answer in one bare word.
    return word if word in KNOWN else "self"


def resolve_account_holder(relationship: str) -> str:
    return ACCOUNTS.get(relationship, ACCOUNTS["self"])


class SupportAgent(Agent):
    def __init__(self):
        super().__init__(instructions="You are a support line. Find out who the call is about.")

    @function_tool
    async def record_caller_relationship(self, spoken_relationship: str) -> str:
        """Record who the caller is calling about."""
        relationship = normalise_relationship(spoken_relationship)
        holder = resolve_account_holder(relationship)
        return f"relationship={relationship} account={holder}"


class _ScriptedStream(llm.LLMStream):
    def __init__(self, parent, *, chat_ctx, tools, conn_options, turn):
        super().__init__(parent, chat_ctx=chat_ctx, tools=tools, conn_options=conn_options)
        self._turn = turn

    async def _run(self) -> None:
        cid = str(uuid.uuid4())
        if self._turn == 1:
            spoken = "for my mother"
            self._event_ch.send_nowait(llm.ChatChunk(id=cid, delta=llm.ChoiceDelta(
                role="assistant", tool_calls=[llm.FunctionToolCall(
                    call_id=cid, name="record_caller_relationship",
                    arguments=f'{{"spoken_relationship": "{spoken}"}}')])))
        else:
            self._event_ch.send_nowait(llm.ChatChunk(id=cid, delta=llm.ChoiceDelta(
                role="assistant", content="Thanks — I have that on the account now.")))


class ScriptedLLM(llm.LLM):
    """Stands in for a real model so the voice path runs with no key and no network."""

    def __init__(self):
        super().__init__()
        self.turn = 0

    def chat(self, *, chat_ctx, tools=None, conn_options=None, **kw) -> llm.LLMStream:
        from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS
        self.turn += 1
        return _ScriptedStream(self, chat_ctx=chat_ctx, tools=tools or [],
                               conn_options=conn_options or DEFAULT_API_CONNECT_OPTIONS,
                               turn=self.turn)


async def _call(model):
    session = AgentSession(llm=model)
    await session.start(SupportAgent())
    model.turn = 0
    result = await session.run(user_input="Hi, I'm calling about my mother's account.")
    for ev in result.events:
        kind = type(ev).__name__
        if kind == "FunctionCallEvent":
            print(f"  [tool] {ev.item.name}({ev.item.arguments})", flush=True)
        elif kind == "FunctionCallOutputEvent":
            print(f"  [out ] {ev.item.output}", flush=True)
        elif kind == "ChatMessageEvent":
            print(f"  [say ] {ev.item.text_content}", flush=True)
    await session.aclose()


async def main():
    with fake_job_context() as ctx:
        ctx.proc.userdata.setdefault("conversation_messages", [])
        print("[voice] ready", flush=True)
        await asyncio.sleep(int(os.environ.get("ARM_WAIT", 0)))
        model = ScriptedLLM()
        for i in range(int(os.environ.get("ROUNDS", 3))):
            print(f"[voice] call {i + 1}", flush=True)
            await _call(model)
            await asyncio.sleep(0.6)
        print("[voice] done", flush=True)
        await asyncio.sleep(int(os.environ.get("HOLD", 0)))


if __name__ == "__main__":
    asyncio.run(main())
