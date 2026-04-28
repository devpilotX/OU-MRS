"""Phase 9.6: in-memory asyncio pub/sub for live ticks.

Publishers are non-asyncio threads (e.g. SmartWebSocketV2 callback);
subscribers are FastAPI SSE endpoint coroutines. Bridge via
loop.call_soon_threadsafe.
"""
import asyncio
import logging
from typing import Set, Dict, Optional

log = logging.getLogger("tick_broker")


class TickBroker:
    def __init__(self) -> None:
        self._subs: Set[asyncio.Queue] = set()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._latest: Dict[str, dict] = {}

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._subs.add(q)
        for tick in self._latest.values():
            try:
                q.put_nowait(tick)
            except asyncio.QueueFull:
                pass
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.discard(q)

    def publish_threadsafe(self, tick: dict) -> None:
        if self._loop is None:
            return
        sym = tick.get("symbol")
        if sym:
            self._latest[sym] = tick
        try:
            self._loop.call_soon_threadsafe(self._fanout, tick)
        except RuntimeError:
            pass

    def _fanout(self, tick: dict) -> None:
        for q in list(self._subs):
            try:
                q.put_nowait(tick)
            except asyncio.QueueFull:
                try:
                    q.get_nowait()
                    q.put_nowait(tick)
                except Exception:
                    pass

    def stats(self) -> dict:
        return {
            "subscribers": len(self._subs),
            "symbols": list(self._latest.keys()),
            "latest": self._latest,
        }


broker = TickBroker()
