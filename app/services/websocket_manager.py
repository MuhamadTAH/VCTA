import asyncio
from typing import Dict


class WebSocketManager:
    def __init__(self, max_queue_size: int = 100):
        self.active_connections: Dict[str, asyncio.Queue] = {}
        self.max_queue_size = max_queue_size

    async def connect(self, session_id: str) -> asyncio.Queue:
        queue = asyncio.Queue(maxsize=self.max_queue_size)
        self.active_connections[session_id] = queue
        return queue

    async def disconnect(self, session_id: str) -> None:
        self.active_connections.pop(session_id, None)

    async def send(self, session_id: str, message: str) -> bool:
        if session_id in self.active_connections:
            await self.active_connections[session_id].put(message)
            return True
        return False

    async def broadcast(self, message: str) -> None:
        for queue in self.active_connections.values():
            await queue.put(message)

    def is_connected(self, session_id: str) -> bool:
        return session_id in self.active_connections

    async def heartbeat(self, session_id: str, websocket, interval: float = 30.0) -> None:
        while session_id in self.active_connections:
            try:
                await asyncio.sleep(interval)
                await websocket.send_text("")
            except Exception:
                await self.disconnect(session_id)
                break

    async def send_direct(self, websocket, message: str) -> bool:
        try:
            await websocket.send_text(message)
            return True
        except Exception:
            return False

    async def get_message(self, session_id: str, timeout: float = 5.0) -> str | None:
        if session_id not in self.active_connections:
            return None
        try:
            return await asyncio.wait_for(
                self.active_connections[session_id].get(),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            return None


ws_manager = WebSocketManager()