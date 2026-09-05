"""A LangGraph order agent that answers with filler because the tool result never
reaches the model.

    aitrap run -- python examples/langgraph_order_agent.py
    aitrap trap --trapset langchain
    aitrap poll 0

The tool works. The graph is valid. The reply node just prompts the model with the
question alone, so the delivery date the tool fetched is dropped on the floor and the
model's polite filler overwrites it in state. Nothing raises and the transcript reads
like a working agent — the only place it shows is the input the model was handed.
"""
import os, time
from langchain_core.language_models.chat_models import SimpleChatModel
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

# Ships broken on purpose. LANGGRAPH_FIXED=1 applies the repair.
FIXED = os.environ.get("LANGGRAPH_FIXED") == "1"

ORDERS = {"A-1": "arriving Friday 12 Sep, signed for"}


@tool
def lookup_order(order_id: str) -> str:
    """Look up an order by id."""
    return f"order {order_id}: {ORDERS.get(order_id, 'not found')}"


class ScriptedModel(SimpleChatModel):
    """Stands in for a real model: it answers from what the prompt gives it, and has
    nothing to go on when the prompt carries no order."""

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def _call(self, messages, stop=None, run_manager=None, **kw) -> str:
        prompt = messages[-1].content
        if "context:" in prompt:
            return f"Your order is {prompt.split('context:', 1)[1].split(':', 1)[-1].strip()}."
        return "Let me check that for you."


class State(TypedDict):
    question: str
    lookup: str
    answer: str


llm = ScriptedModel()


def tool_node(state: State):
    return {"lookup": lookup_order.run({"order_id": "A-1"})}


def reply_node(state: State):
    # The repair is one argument: give the model what the tool just found.
    prompt = f"{state['question']}\n\ncontext: {state['lookup']}" if FIXED else state["question"]
    return {"answer": llm.invoke(prompt).content}


g = StateGraph(State)
g.add_node("tools", tool_node)
g.add_node("reply", reply_node)
g.add_edge(START, "tools")
g.add_edge("tools", "reply")
g.add_edge("reply", END)
app = g.compile()

if __name__ == "__main__":
    print("[lg] ready", flush=True)
    time.sleep(int(os.environ.get("ARM_WAIT", 0)))
    for i in range(int(os.environ.get("ROUNDS", 3))):
        print("  [ask ] Where is my order?", flush=True)
        out = app.invoke({"question": "Where is my order?", "lookup": "", "answer": ""})
        print(f"  [tool] {out['lookup']}", flush=True)
        print(f"  [say ] {out['answer']}", flush=True)
        time.sleep(0.5)
    print("[lg] done", flush=True)
    time.sleep(int(os.environ.get("HOLD", 0)))
