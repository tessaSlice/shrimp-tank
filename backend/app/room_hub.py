"""In-process WebSocket fanout for shared LAN game sessions."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Callable

from fastapi import WebSocket


@dataclass(eq=False)
class RoomClient:
    websocket: WebSocket
    client_id: str


class RoomHub:
    """Tracks connected browser tabs and broadcasts public session snapshots."""

    def __init__(self) -> None:
        self._rooms: dict[str, set[RoomClient]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, session_id: str, websocket: WebSocket, client_id: str) -> RoomClient:
        await websocket.accept()
        client = RoomClient(websocket=websocket, client_id=client_id)
        async with self._lock:
            clients = self._rooms.setdefault(session_id, set())
            clients.add(client)
            count = len(clients)
        await self._send_presence(session_id, count)
        return client

    async def disconnect(self, session_id: str, client: RoomClient) -> None:
        async with self._lock:
            clients = self._rooms.get(session_id)
            if not clients:
                return
            clients.discard(client)
            count = len(clients)
            if not clients:
                self._rooms.pop(session_id, None)
        await self._send_presence(session_id, count)

    async def send_state(self, websocket: WebSocket, state: dict) -> None:
        await asyncio.wait_for(websocket.send_json({"type": "state", "state": state}), timeout=2)

    async def broadcast_event(
        self,
        session_id: str,
        event: dict,
        exclude_client_id: str | None = None,
    ) -> None:
        async with self._lock:
            recipients = [
                client for client in self._rooms.get(session_id, set())
                if client.client_id != exclude_client_id
            ]
        stale: list[RoomClient] = []
        for client in recipients:
            try:
                await asyncio.wait_for(client.websocket.send_json(event), timeout=2)
            except Exception:
                stale.append(client)
        for client in stale:
            await self.disconnect(session_id, client)

    async def broadcast_state(
        self,
        session_id: str,
        state: dict,
        exclude_client_id: str | None = None,
        state_for_client: Callable[[str], dict] | None = None,
    ) -> None:
        async with self._lock:
            recipients = [
                client for client in self._rooms.get(session_id, set())
                if client.client_id != exclude_client_id
            ]
        stale: list[RoomClient] = []
        for client in recipients:
            try:
                client_state = state_for_client(client.client_id) if state_for_client else state
                await self.send_state(client.websocket, client_state)
            except Exception:
                stale.append(client)
        for client in stale:
            await self.disconnect(session_id, client)

    async def _send_presence(self, session_id: str, count: int) -> None:
        async with self._lock:
            recipients = list(self._rooms.get(session_id, set()))
        stale: list[RoomClient] = []
        for client in recipients:
            try:
                await asyncio.wait_for(client.websocket.send_json({"type": "presence", "count": count}), timeout=2)
            except Exception:
                stale.append(client)
        for client in stale:
            async with self._lock:
                clients = self._rooms.get(session_id)
                if clients:
                    clients.discard(client)
                    if not clients:
                        self._rooms.pop(session_id, None)


ROOM_HUB = RoomHub()
