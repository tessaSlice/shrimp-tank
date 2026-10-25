from __future__ import annotations

import asyncio
import json
import os
import subprocess
from dataclasses import fields
from datetime import datetime, timezone
from threading import Lock
from typing import Any
from urllib.parse import quote

import httpx

from .main_types import GameSession


class SpacetimeStoreError(RuntimeError):
    """Raised when the persistent session database cannot complete an operation."""


def _cli_token() -> str | None:
    """Developer-only convenience; deployed services must use SPACETIMEDB_TOKEN."""
    try:
        result = subprocess.run(
            ["spacetime", "login", "show", "--token"],
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    marker = "Your auth token (don't share this!) is "
    for line in result.stdout.splitlines():
        if line.startswith(marker):
            return line.removeprefix(marker).strip() or None
    return None


class SpacetimeSessionStore:
    """Persists complete game sessions in a private SpacetimeDB table.

    Game rules intentionally stay in FastAPI. Each completed route transition is
    stored through a transactional SpacetimeDB reducer, while the table remains
    private because it contains hidden fictional borrower profiles.
    """

    def __init__(self, database: str, uri: str, token: str | None = None):
        self.database = database
        self.uri = uri.rstrip("/")
        self.token = token or _cli_token()
        if not self.token:
            raise SpacetimeStoreError(
                "SPACETIMEDB_TOKEN is required for the persistent session store. "
                "For local development, run `spacetime login` or set the environment variable."
            )
        self._locks: dict[str, asyncio.Lock] = {}
        self._locks_guard = Lock()

    @classmethod
    def from_environment(cls) -> SpacetimeSessionStore | None:
        if os.getenv("SESSION_STORE", "spacetime").lower() == "memory":
            return None
        database = os.getenv("SPACETIMEDB_DATABASE", "credit-tank-state").strip()
        return cls(
            database=database,
            uri=os.getenv("SPACETIMEDB_URI", "https://maincloud.spacetimedb.com"),
            token=os.getenv("SPACETIMEDB_TOKEN"),
        )

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def _url(self, suffix: str) -> str:
        return f"{self.uri}/v1/database/{quote(self.database, safe='')}{suffix}"

    def _post(self, suffix: str, *, content: str, content_type: str) -> httpx.Response:
        try:
            response = httpx.post(
                self._url(suffix),
                content=content.encode("utf-8"),
                headers={**self._headers, "Content-Type": content_type},
                timeout=httpx.Timeout(6.0, connect=2.0),
            )
            response.raise_for_status()
            return response
        except httpx.HTTPError as exc:
            raise SpacetimeStoreError(f"SpacetimeDB request failed: {exc}") from exc

    @staticmethod
    def _session_payload(session: GameSession) -> str:
        data = {
            field.name: getattr(session, field.name)
            for field in fields(GameSession)
            if field.name != "lock"
        }
        return json.dumps(data, separators=(",", ":"), ensure_ascii=False)

    @staticmethod
    def _row_payload(response: httpx.Response) -> tuple[str, str] | None:
        try:
            statements = response.json()
            rows = statements[0].get("rows", [])
            if not rows:
                return None
            row = rows[0]
            if isinstance(row, dict):
                payload = row.get("state_json") or row.get("stateJson")
                version = row.get("updated_at") or row.get("updatedAt")
                return (payload, version) if payload is not None and version is not None else None
            # SATS JSON can represent product values positionally.
            return (row[0], row[1]) if isinstance(row, list) and len(row) > 1 else None
        except (IndexError, TypeError, ValueError) as exc:
            raise SpacetimeStoreError("SpacetimeDB returned an unreadable session row.") from exc

    def get(self, session_id: str) -> GameSession | None:
        escaped_id = session_id.replace("'", "''")
        response = self._post(
            "/sql",
            content=f"SELECT state_json, updated_at FROM game_session WHERE session_id = '{escaped_id}'",
            content_type="text/plain",
        )
        row = self._row_payload(response)
        if row is None:
            return None
        try:
            payload, version = row
            session = GameSession(**json.loads(payload))
            session.persistence_version = version
            return session
        except (TypeError, ValueError) as exc:
            raise SpacetimeStoreError("Stored session data is invalid.") from exc

    def put(self, session: GameSession) -> None:
        updated_at = datetime.now(timezone.utc).isoformat()
        expected_version = session.persistence_version
        session.persistence_version = updated_at
        conversation_messages = [
            {
                "message_id": message["id"],
                "session_id": session.session_id,
                "pitch_id": session.pitch["id"],
                "pitch_index": session.pitch_index + 1,
                "sequence": sequence,
                "round_number": int(message.get("round", session.round_number)),
                "speaker": str(message.get("speaker", "Unknown")),
                "kind": str(message.get("kind", "dialogue")),
                "text": str(message.get("text", "")),
                "source": str(message.get("source", "system")),
            }
            for sequence, message in enumerate(session.messages)
        ]
        arguments = json.dumps([
            session.session_id,
            self._session_payload(session),
            updated_at,
            expected_version,
            conversation_messages,
        ], separators=(",", ":"), ensure_ascii=False)
        try:
            self._post(
                "/call/upsert_session_with_messages?confirmed=true",
                content=arguments,
                content_type="application/json",
            )
        except Exception:
            session.persistence_version = expected_version
            raise

    def delete(self, session_id: str) -> None:
        self._post(
            "/call/delete_session?confirmed=true",
            content=json.dumps([session_id]),
            content_type="application/json",
        )

    def lock_for(self, session_id: str) -> asyncio.Lock:
        with self._locks_guard:
            return self._locks.setdefault(session_id, asyncio.Lock())
