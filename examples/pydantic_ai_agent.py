"""pydantic-ai agent driven by TestModel. No API key."""
import asyncio, os
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

agent = Agent(TestModel(call_tools=["lookup_order"]), system_prompt="You are support.")


@agent.tool_plain
def lookup_order(order_id: str) -> str:
    """Look up an order by id."""
    return f"order {order_id}: shipped"


async def main():
    print("[pa] ready", flush=True)
    await asyncio.sleep(int(os.environ.get("ARM_WAIT", 0)))
    for i in range(int(os.environ.get("ROUNDS", 3))):
        r = await agent.run("where is my order?")
        print(f"[pa] round {i}: {str(r.output)[:60]}", flush=True)
        await asyncio.sleep(0.5)
    print("[pa] done", flush=True)
    await asyncio.sleep(int(os.environ.get("HOLD", 0)))

asyncio.run(main())
