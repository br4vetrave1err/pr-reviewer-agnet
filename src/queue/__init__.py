# Implements: MOD-004, MOD-005, ARCH-003
"""Queue Manager package (MOD-004, MOD-005).

The canonical spec places the queue modules at ``src/queue/manager.py`` and
``src/queue/worker.py``, which shadows the standard library ``queue`` module
on the import path. To keep third-party imports like ``from queue import
Queue`` (anyio / asyncio) working, the stdlib module is loaded explicitly and
re-exported here.
"""

from __future__ import annotations

import importlib.util
import os
import sys

_STDLIB_DIR = os.path.dirname(os.__file__)
_QUEUE_PATH = os.path.join(_STDLIB_DIR, "queue.py")

if os.path.exists(_QUEUE_PATH):
    _spec = importlib.util.spec_from_file_location("queue._stdlib_queue", _QUEUE_PATH)
    _stdlib_queue = importlib.util.module_from_spec(_spec)
    assert _spec.loader is not None
    _spec.loader.exec_module(_stdlib_queue)
    sys.modules["queue._stdlib_queue"] = _stdlib_queue

    Queue = _stdlib_queue.Queue
    SimpleQueue = _stdlib_queue.SimpleQueue
    LifoQueue = _stdlib_queue.LifoQueue
    PriorityQueue = _stdlib_queue.PriorityQueue
    Empty = _stdlib_queue.Empty
    Full = _stdlib_queue.Full
else:  # pragma: no cover - stdlib layout fallback
    from queue import Empty, Full, LifoQueue, PriorityQueue, Queue, SimpleQueue

__all__ = ["Queue", "SimpleQueue", "LifoQueue", "PriorityQueue", "Empty", "Full"]
