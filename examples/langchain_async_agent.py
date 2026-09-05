"""Async LangChain + LangGraph, to exercise the ainvoke/arun paths."""
import asyncio, os
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict


@tool
async def lookup_order(order_id: str) -> str:
    """Look up an order by id."""
    return f"order {order_id}: shipped"


class State(TypedDict):
    question: str
    answer: str


llm = FakeListChatModel(responses=["checking", "shipped", "anything else?"])


async def model_node(state: State):
    return {"answer": (await llm.ainvoke(state["question"])).content}


async def tool_node(state: State):
    return {"answer": await lookup_order.arun({"order_id": "A-1"})}


g = StateGraph(State)
g.add_node("model", model_node); g.add_node("tools", tool_node)
g.add_edge(START, "model"); g.add_edge("model", "tools"); g.add_edge("tools", END)
app = g.compile()


async def main():
    print("[lca] ready", flush=True)
    await asyncio.sleep(int(os.environ.get("ARM_WAIT", 0)))
    for i in range(int(os.environ.get("ROUNDS", 3))):
        out = await app.ainvoke({"question": "where is my order?", "answer": ""})
        print(f"[lca] round {i}: {out['answer']}", flush=True)
    print("[lca] done", flush=True)
    await asyncio.sleep(int(os.environ.get("HOLD", 0)))

asyncio.run(main())
