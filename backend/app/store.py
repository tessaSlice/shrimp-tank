from __future__ import annotations

import asyncio
from typing import Protocol

from .main_types import GameSession


class SessionStore(Protocol):
    """Persistent-session storage boundary."""

    def get(self, session_id: str) -> GameSession | None: ...
    def put(self, session: GameSession) -> None: ...
    def delete(self, session_id: str) -> None: ...
    def lock_for(self, session_id: str) -> asyncio.Lock: ...


class InMemorySessionStore:
    """Single-process demo store. State disappears when the backend restarts."""

    def __init__(self) -> None:
        self._sessions: dict[str, GameSession] = {}

    def get(self, session_id: str) -> GameSession | None:
        return self._sessions.get(session_id)

    def put(self, session: GameSession) -> None:
        self._sessions[session.session_id] = session

    def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def lock_for(self, session_id: str) -> asyncio.Lock:
        session = self._sessions.get(session_id)
        return session.lock if session else asyncio.Lock()
