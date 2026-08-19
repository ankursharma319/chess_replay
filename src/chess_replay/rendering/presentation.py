"""Display metadata for replay frames."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import chess


@dataclass(frozen=True, slots=True)
class PlayerPresentation:
    username: str
    rating: str = ""
    name: str | None = None
    title: str | None = None
    avatar_path: Path | None = None
    country_code: str | None = None
    flag_path: Path | None = None
    score_before: float | None = None
    game_number: int | None = None
    standing_label: str | None = None

    @property
    def display_name(self) -> str:
        return self.name or self.username

    @property
    def metadata_line(self) -> str:
        parts = [self.title, f"@{self.username}", self.rating]
        return "  ·  ".join(part for part in parts if part)

    @property
    def tournament_line(self) -> str:
        parts: list[str] = []
        if self.score_before is not None:
            parts.append(f"{self.score_before:g} pts")
        if self.game_number is not None:
            parts.append(f"Game {self.game_number}")
        if self.standing_label is not None:
            parts.append(f"{self.standing_label} by score")
        return "  ·  ".join(parts)


@dataclass(frozen=True, slots=True)
class ReplayPresentation:
    white: PlayerPresentation
    black: PlayerPresentation
    tournament_name: str | None = None
    round_number: int | None = None
    total_rounds: int | None = None
    game_format: str | None = None
    bottom_color: chess.Color = chess.WHITE

    @property
    def event_line(self) -> str:
        detail_parts: list[str] = []
        event_name = (
            self.tournament_name.replace("-", " ") if self.tournament_name else ""
        )
        if self.game_format:
            detail_parts.append(self.game_format)
        if self.round_number is not None:
            round_text = f"Round {self.round_number}"
            if self.total_rounds is not None:
                round_text += f"/{self.total_rounds}"
            detail_parts.append(round_text)
        details = "  ·  ".join(detail_parts)
        return "\n".join(part for part in (event_name, details) if part)