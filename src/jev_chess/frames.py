"""Frame history: append-only list with a view cursor for back/forward."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Frame:
    ply: int
    fen: str
    parent_fen: str | None
    move_uci: str
    move_san: str
    side: str  # "white" (jev) | "black" (engine)
    is_check: bool = False
    result: str | None = None
    # Jev stats (white plies)
    jev_choice: str | None = None
    jev_probs: dict[str, float] = field(default_factory=dict)
    jev_confidence: float | None = None
    jev_temperature: float = 0.0
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: float | None = None
    # Full Jev query/response for the expandable detail view (white plies)
    jev_state: dict = field(default_factory=dict)
    jev_questions: dict = field(default_factory=dict)
    jev_response: dict = field(default_factory=dict)
    # Engine detail (black plies)
    engine_time_s: float | None = None
    engine_info: dict = field(default_factory=dict)


class History:
    """Push-only frames; cursor views history. Next locked unless at tip."""

    def __init__(self, initial_fen: str) -> None:
        self.initial_fen = initial_fen
        self.frames: list[Frame] = []
        self.cursor: int = -1  # -1 = initial position, else index into frames

    @property
    def tip(self) -> int:
        return len(self.frames) - 1

    @property
    def at_tip(self) -> bool:
        return self.cursor == self.tip

    def push(self, frame: Frame) -> None:
        if not self.at_tip:
            raise RuntimeError("must be at tip to push (forking deferred)")
        self.frames.append(frame)
        self.cursor = self.tip

    def back(self) -> str:
        """Move cursor back, return fen to display."""
        if self.cursor >= 0:
            self.cursor -= 1
        return self.view_fen()

    def forward(self) -> str:
        if self.cursor < self.tip:
            self.cursor += 1
        return self.view_fen()

    def view_fen(self) -> str:
        if self.cursor < 0:
            return self.initial_fen
        return self.frames[self.cursor].fen

    def current(self) -> Frame | None:
        if self.cursor < 0:
            return None
        return self.frames[self.cursor]
