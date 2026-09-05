"""The same pydantic-ai agent through the synchronous entry point, Agent.run_sync."""
import os, time

from pydantic_ai_agent import agent

if __name__ == "__main__":
    print("[pas] ready", flush=True)
    time.sleep(int(os.environ.get("ARM_WAIT", 0)))
    for i in range(int(os.environ.get("ROUNDS", 3))):
        r = agent.run_sync("where is my order?")
        print(f"[pas] round {i}: {str(r.output)[:60]}", flush=True)
        time.sleep(0.5)
    print("[pas] done", flush=True)
    time.sleep(int(os.environ.get("HOLD", 0)))
