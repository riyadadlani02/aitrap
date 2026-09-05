"""aitrap - non-stopping runtime traps for live AI agent processes."""
import os

__version__ = "0.1.0"
_engine = None


def serve(port=None, buffer_size=10_000, announce=True):
    """Install traps + control plane in this process. Idempotent."""
    global _engine
    if _engine is not None:
        return _engine
    from .engine import Buffer, Engine
    from .server import serve as _serve

    _engine = Engine(Buffer(buffer_size))
    port = _serve(_engine, int(port if port is not None else os.environ.get("AITRAP_PORT", 0)))
    _engine.port = port
    path = os.environ.get("AITRAP_PORTFILE")
    if path:
        with open(path, "w") as fh:
            fh.write(str(port))
    if announce:
        print(f"[aitrap] listening on 127.0.0.1:{port}", flush=True)
    return _engine
