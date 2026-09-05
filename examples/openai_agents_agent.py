"""openai-agents SDK driven by a hand-written fake model. No API key, no network."""
import asyncio, os
from openai.types.responses import ResponseFunctionToolCall, ResponseOutputMessage, ResponseOutputText

from agents import Agent, Runner, function_tool
from agents.items import ModelResponse
from agents.models.interface import Model
from agents.usage import Usage


@function_tool
def lookup_order(order_id: str) -> str:
    """Look up an order by id."""
    return f"order {order_id}: shipped"


def _msg(text):
    return ResponseOutputMessage(id="m1", role="assistant", status="completed", type="message",
        content=[ResponseOutputText(annotations=[], text=text, type="output_text")])


class FakeModel(Model):
    """Turn 1 asks for the tool, turn 2 hands off, turn 3 answers."""
    def __init__(self):
        self.turn = 0

    async def get_response(self, system_instructions, input, model_settings, tools,
                           output_schema, handoffs, tracing, *, previous_response_id=None,
                           conversation_id=None, prompt=None, **kw):
        self.turn += 1
        if self.turn == 1:
            out = [ResponseFunctionToolCall(id="c1", call_id="c1", name="lookup_order",
                                            arguments='{"order_id": "A-1"}', type="function_call")]
        elif self.turn == 2 and handoffs:
            out = [ResponseFunctionToolCall(id="c2", call_id="c2", name=handoffs[0].tool_name,
                                            arguments="{}", type="function_call")]
        else:
            out = [_msg("your order shipped yesterday")]
        return ModelResponse(output=out, usage=Usage(), response_id=None)

    async def stream_response(self, *a, **k):
        raise NotImplementedError


escalation = Agent(name="escalation", instructions="handle escalations", model=FakeModel())
support = Agent(name="support", instructions="you are support", tools=[lookup_order],
                handoffs=[escalation], model=FakeModel())


async def main():
    print("[oa] ready", flush=True)
    await asyncio.sleep(int(os.environ.get("ARM_WAIT", 0)))
    for i in range(int(os.environ.get("ROUNDS", 3))):
        support.model.turn = 0
        escalation.model.turn = 5
        r = await Runner.run(support, "where is my order?")
        print(f"[oa] round {i}: {str(r.final_output)[:60]}", flush=True)
        await asyncio.sleep(0.5)
    print("[oa] done", flush=True)
    await asyncio.sleep(int(os.environ.get("HOLD", 0)))

asyncio.run(main())
