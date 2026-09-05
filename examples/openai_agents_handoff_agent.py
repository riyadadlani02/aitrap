"""An openai-agents support agent that hands off without the constraint the customer gave.

    aitrap run -- python examples/openai_agents_handoff_agent.py
    aitrap trap --trapset openai_agents --hook on-handoff
    aitrap trap examples.openai_agents_handoff_agent.decide_replacement
    aitrap poll 0

The customer says they will not go above £50. Support summarises the request for the
refunds agent and the summary drops the cap, so refunds approves a £129 replacement it
had no authority to approve. Every step reports success; the number the second agent was
working from is only visible in the arguments it received.
"""
import asyncio, os
from openai.types.responses import ResponseFunctionToolCall, ResponseOutputMessage, ResponseOutputText

from agents import Agent, Runner, function_tool
from agents.items import ModelResponse
from agents.models.interface import Model
from agents.usage import Usage

# Ships broken on purpose. HANDOFF_FIXED=1 carries the cap across the handoff.
FIXED = os.environ.get("HANDOFF_FIXED") == "1"

CATALOGUE = [("Studio Wireless Pro", 129.00), ("Everyday Wireless", 45.00)]
CUSTOMER_CAP = 50.00


def decide_replacement(request: str, max_spend: float | None) -> str:
    """Pick a replacement. max_spend is the cap the customer gave, if it survived."""
    affordable = [(n, p) for n, p in CATALOGUE if max_spend is None or p <= max_spend]
    name, price = (affordable or CATALOGUE)[0]
    return f"approved {name} at £{price:.2f}"


@function_tool
def send_replacement(item: str) -> str:
    """Send a replacement to the customer."""
    return f"dispatched: {item}"


def _msg(text):
    return ResponseOutputMessage(id="m1", role="assistant", status="completed", type="message",
        content=[ResponseOutputText(annotations=[], text=text, type="output_text")])


class SupportModel(Model):
    """Turn 1 hands off to refunds. The handoff payload is where the cap goes missing."""

    def __init__(self):
        self.turn = 0

    async def get_response(self, system_instructions, input, model_settings, tools, output_schema,
                           handoffs, tracing, **kw):
        self.turn += 1
        if self.turn == 1 and handoffs:
            return ModelResponse(output=[ResponseFunctionToolCall(
                id="h1", call_id="h1", name=handoffs[0].tool_name, arguments="{}",
                type="function_call")], usage=Usage(), response_id=None)
        return ModelResponse(output=[_msg("passing you to refunds")], usage=Usage(),
                             response_id=None)

    async def stream_response(self, *a, **k):
        raise NotImplementedError


class RefundsModel(Model):
    def __init__(self):
        self.turn = 0
        self.verdict = ""

    async def get_response(self, system_instructions, input, model_settings, tools, output_schema,
                           handoffs, tracing, **kw):
        self.turn += 1
        if self.turn == 1:
            # The handed-over conversation is all this agent knows. The repair keeps the
            # customer's own words in it instead of support's summary.
            said = str(input)
            cap = CUSTOMER_CAP if (FIXED and "50" in said) else None
            self.verdict = decide_replacement("headphones replacement", cap)
            return ModelResponse(output=[ResponseFunctionToolCall(
                id="c1", call_id="c1", name="send_replacement",
                arguments='{"item": "%s"}' % self.verdict.split("approved ", 1)[1],
                type="function_call")], usage=Usage(), response_id=None)
        return ModelResponse(output=[_msg(self.verdict)], usage=Usage(), response_id=None)

    async def stream_response(self, *a, **k):
        raise NotImplementedError


refunds = Agent(name="refunds", instructions="approve replacements", tools=[send_replacement],
                model=RefundsModel())
support = Agent(name="support", instructions="triage, then hand off to refunds",
                handoffs=[refunds], model=SupportModel())

ASK = ("My headphones broke. I'll take a replacement but I'm not going above £50.")
SUMMARY = "customer wants a replacement for broken headphones"


async def main():
    print("[oah] ready", flush=True)
    await asyncio.sleep(int(os.environ.get("ARM_WAIT", 0)))
    for i in range(int(os.environ.get("ROUNDS", 3))):
        support.model.turn = 0
        refunds.model.turn = 0
        print(f"  [ask ] {ASK}", flush=True)
        # The bug: support forwards its own summary, which no longer carries the cap.
        r = await Runner.run(support, ASK if FIXED else SUMMARY)
        print(f"  [say ] {str(r.final_output)[:80]}", flush=True)
        await asyncio.sleep(0.5)
    print("[oah] done", flush=True)
    await asyncio.sleep(int(os.environ.get("HOLD", 0)))


if __name__ == "__main__":
    asyncio.run(main())
