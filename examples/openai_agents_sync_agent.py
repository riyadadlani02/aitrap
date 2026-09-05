"""The same openai-agents run through the synchronous entry point, Runner.run_sync.

Same trapset, different door in: run_sync drives its own event loop, so the frames come
back on a different task than the async example's.
"""
import os, time

from agents import Runner
from openai_agents_agent import escalation, support

if __name__ == "__main__":
    print("[oas] ready", flush=True)
    time.sleep(int(os.environ.get("ARM_WAIT", 0)))
    for i in range(int(os.environ.get("ROUNDS", 3))):
        support.model.turn = 0
        escalation.model.turn = 5
        r = Runner.run_sync(support, "where is my order?")
        print(f"[oas] round {i}: {str(r.final_output)[:60]}", flush=True)
        time.sleep(0.5)
    print("[oas] done", flush=True)
    time.sleep(int(os.environ.get("HOLD", 0)))
