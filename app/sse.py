from __future__ import annotations
import asyncio, time
from typing import AsyncIterator, Dict, Deque
from collections import defaultdict, deque

class StreamHub:
    def __init__(self):
        self._queues: Dict[str, Deque[str]] = defaultdict(deque)
        self._conds: Dict[str, asyncio.Condition] = defaultdict(asyncio.Condition)

    async def publish(self, task_id: str, message: str):
        async with self._conds[task_id]:
            self._queues[task_id].append(message)
            self._conds[task_id].notify_all()

    

    
    def close(self, task_id: str) -> None:
        """Cleanup per-task state to avoid unbounded growth."""
        try:
            self._queues.pop(task_id, None)
        except Exception:
            pass
        try:
            self._conds.pop(task_id, None)
        except Exception:
            pass

    async def stream(self, task_id: str, heartbeat_seconds: int = 10) -> AsyncIterator[str]:
        last = time.time()
        while True:
            async with self._conds[task_id]:
                if self._queues[task_id]:
                    msg = self._queues[task_id].popleft()
                    yield f"data: {msg}\n\n"
                    last = time.time()
                else:
                    try:
                        await asyncio.wait_for(self._conds[task_id].wait(), timeout=1.0)
                    except asyncio.TimeoutError:
                        pass
            if time.time() - last >= heartbeat_seconds:
                yield "event: heartbeat\ndata: ping\n\n"
                last = time.time()
