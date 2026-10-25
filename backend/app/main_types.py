from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class GameSession:
    session_id: str
    total_pitches: int
    difficulty: str
    starting_capital: int
    pitch_queue: list[str]
    pitch_index: int = 0
    round_number: int = 1
    phase: str = "investigate"
    balance: int = 0
    pitch: dict = field(default_factory=dict)
    messages: list[dict] = field(default_factory=list)
    disclosures: list[str] = field(default_factory=list)
    offers: list[dict] = field(default_factory=list)
    completed: list[dict] = field(default_factory=list)
    human_out: bool = False
    question_asked: bool = False
    pending_result: dict | None = None
    result: dict | None = None
    scorecard: dict | None = None
    persistence_version: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
