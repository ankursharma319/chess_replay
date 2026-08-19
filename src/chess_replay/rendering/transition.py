"""Render between-game tournament result cards."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

from chess_replay.rendering.pillow_board import BoardTheme, _font


@dataclass(frozen=True, slots=True)
class TransitionPresentation:
    player_name: str
    player_title: str | None
    opponent_name: str
    opponent_title: str | None
    result_label: str
    termination_label: str
    game_format: str
    score_after: float
    wins: int
    draws: int
    losses: int
    round_number: int
    total_rounds: int
    tournament_name: str
    next_opponent: str | None = None
    score_heading: str | None = None
    progress_label: str | None = None
    completion_label: str = "Tournament run complete"

    @property
    def outcome_heading(self) -> str:
        if self.result_label == "Drew":
            return "GAME DRAWN"
        return f"{self.player_name} {self.result_label}".upper()

    @property
    def matchup_line(self) -> str:
        player = _titled_name(self.player_name, self.player_title)
        opponent = _titled_name(self.opponent_name, self.opponent_title)
        return f"{player} vs {opponent}"


class TransitionRenderer:
    def __init__(
        self,
        width: int = 1920,
        height: int = 1080,
        theme: BoardTheme | None = None,
    ) -> None:
        self.width = width
        self.height = height
        self.theme = theme or BoardTheme()
        self.scale = min(width / 1920, height / 1080)

    def _scaled(self, value: int) -> int:
        return max(1, round(value * self.scale))

    def render(self, presentation: TransitionPresentation, output_path: Path) -> None:
        image = Image.new("RGB", (self.width, self.height), self.theme.background)
        draw = ImageDraw.Draw(image)
        result_color = {
            "Won": "#2E8B57",
            "Lost": "#B64A4A",
            "Drew": "#B18A35",
        }.get(presentation.result_label, self.theme.highlight)

        draw.rectangle((0, 0, self.width, self._scaled(18)), fill=result_color)
        draw.text(
            (self.width // 2, self._scaled(85)),
            presentation.tournament_name.replace("-", " "),
            fill=self.theme.muted_text,
            font=_font(self._scaled(34)),
            anchor="mm",
        )
        draw.text(
            (self.width // 2, self._scaled(250)),
            presentation.outcome_heading,
            fill=result_color,
            font=_font(self._scaled(92), bold=True),
            anchor="mm",
        )
        draw.text(
            (self.width // 2, self._scaled(390)),
            presentation.matchup_line,
            fill=self.theme.text,
            font=_font(self._scaled(48), bold=True),
            anchor="mm",
        )
        draw.text(
            (self.width // 2, self._scaled(455)),
            f"{presentation.termination_label}  ·  {presentation.game_format}",
            fill=self.theme.muted_text,
            font=_font(self._scaled(32), bold=True),
            anchor="mm",
        )

        card_top = self._scaled(500)
        draw.rounded_rectangle(
            (
                self._scaled(320),
                card_top,
                self.width - self._scaled(320),
                card_top + self._scaled(300),
            ),
            radius=self._scaled(8),
            fill=self.theme.panel,
        )
        draw.text(
            (self.width // 2, card_top + self._scaled(80)),
            presentation.score_heading or _plural(presentation.score_after, "point"),
            fill=self.theme.text,
            font=_font(self._scaled(72), bold=True),
            anchor="mm",
        )
        draw.text(
            (self.width // 2, card_top + self._scaled(175)),
            f"{_plural(presentation.wins, 'win')}  ·  "
            f"{_plural(presentation.draws, 'draw')}  ·  "
            f"{_plural(presentation.losses, 'loss', 'losses')}",
            fill=self.theme.highlight,
            font=_font(self._scaled(38), bold=True),
            anchor="mm",
        )
        draw.text(
            (self.width // 2, card_top + self._scaled(245)),
            presentation.progress_label
            or f"Round {presentation.round_number} of {presentation.total_rounds}",
            fill=self.theme.muted_text,
            font=_font(self._scaled(30)),
            anchor="mm",
        )

        footer = (
            f"Next: {presentation.next_opponent}"
            if presentation.next_opponent
            else presentation.completion_label
        )
        draw.text(
            (self.width // 2, self._scaled(930)),
            footer,
            fill=self.theme.text,
            font=_font(self._scaled(36)),
            anchor="mm",
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(output_path, format="PNG", optimize=True)


def _plural(value: float, singular: str, plural: str | None = None) -> str:
    noun = singular if value == 1 else (plural or f"{singular}s")
    return f"{value:g} {noun}"


def _titled_name(name: str, title: str | None) -> str:
    return f"{title} {name}" if title else name