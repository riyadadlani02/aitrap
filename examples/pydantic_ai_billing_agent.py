"""A pydantic-ai billing agent that credits an account a hundred times over.

    aitrap run -- python examples/pydantic_ai_billing_agent.py
    aitrap trap --trapset pydantic_ai --hook on-tool-call
    aitrap trap examples.pydantic_ai_billing_agent.credit_for
    aitrap poll 0

The invoice store keeps money in pence, the credit tool takes pounds, and the helper
between them hands the pence figure straight over. £49.99 becomes £4,999.00. Both are
valid floats, so nothing raises, the tool reports success and the agent tells the
customer it is done. The unit only exists in the value.
"""
import asyncio, os
from pydantic_ai import Agent
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel

# Ships broken on purpose. BILLING_FIXED=1 converts pence to pounds.
FIXED = os.environ.get("BILLING_FIXED") == "1"

INVOICES = {"INV-4417": {"account": "AC-8802", "amount_pence": 4999}}


def credit_for(invoice_id: str) -> float:
    """How much to credit, in pounds — which is the part that is wrong."""
    pence = INVOICES[invoice_id]["amount_pence"]
    return pence / 100 if FIXED else float(pence)


def model_fn(messages, info):
    if len(messages) == 1:
        return ModelResponse(parts=[ToolCallPart("issue_credit", {"invoice_id": "INV-4417"})])
    return ModelResponse(parts=[TextPart("Done — that credit is on the account.")])


agent = Agent(FunctionModel(model_fn), system_prompt="You are billing support.")


@agent.tool_plain
def issue_credit(invoice_id: str) -> str:
    """Credit the invoice back to the customer's account, in pounds."""
    amount = credit_for(invoice_id)
    account = INVOICES[invoice_id]["account"]
    return f"credited GBP {amount:,.2f} to {account}"


async def main():
    print("[pab] ready", flush=True)
    await asyncio.sleep(int(os.environ.get("ARM_WAIT", 0)))
    for i in range(int(os.environ.get("ROUNDS", 3))):
        print("  [ask ] Please refund invoice INV-4417.", flush=True)
        r = await agent.run("Please refund invoice INV-4417.")
        for m in r.all_messages():
            for part in getattr(m, "parts", []):
                if type(part).__name__ == "ToolReturnPart":
                    print(f"  [tool] {part.content}", flush=True)
        print(f"  [say ] {r.output}", flush=True)
        await asyncio.sleep(0.5)
    print("[pab] done", flush=True)
    await asyncio.sleep(int(os.environ.get("HOLD", 0)))


if __name__ == "__main__":
    asyncio.run(main())
