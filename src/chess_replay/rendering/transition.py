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
    result_label: str
    score_after: float
    wins: int
    draws: int
    losses: int
    round_number: int
    total_rounds: int
    tournament_name: str
    next_opponent: str | None = None


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

    def render(self, presentation: TransitionPresentation, output_path: Path) -> None:
        image = Image.new("RGB", (self.width, self.height), self.theme.background)
        draw = ImageDraw.Draw(image)
        result_color = {
            "Won": "#2E8B57",
            "Lost": "#B64A4A",
            "Drew": "#B18A35",
        }.get(presentation.result_label, self.theme.highlight)

        draw.rectangle((0, 0, self.width, 18), fill=result_color)
        draw.text(
            (self.width // 2, 85),
            presentation.tournament_name.replace("-", " "),
            fill=self.theme.muted_text,
            font=_font(34),
            anchor="mm",
        )
        draw.text(
            (self.width // 2, 250),
            presentation.result_label.upper(),
            fill=result_color,
            font=_font(124, bold=True),
            anchor="mm",
        )
        title = f"{presentation.player_title} " if presentation.player_title else ""
        draw.text(
            (self.width // 2, 390),
            f"{title}{presentation.player_name} vs {presentation.opponent_name}",
            fill=self.theme.text,
            font=_font(48, bold=True),
            anchor="mm",
        )

        card_top = 500
        draw.rounded_rectangle(
            (320, card_top, self.width - 320, card_top + 300),
            radius=8,
            fill=self.theme.panel,
        )
        draw.text(
            (self.width // 2, card_top + 80),
            _plural(presentation.score_after, "point"),
            fill=self.theme.text,
            font=_font(72, bold=True),
            anchor="mm",
        )
        draw.text(
            (self.width // 2, card_top + 175),
            f"{_plural(presentation.wins, 'win')}  ·  "
            f"{_plural(presentation.draws, 'draw')}  ·  "
            f"{_plural(presentation.losses, 'loss', 'losses')}",
            fill=self.theme.highlight,
            font=_font(38, bold=True),
            anchor="mm",
        )
        draw.text(
            (self.width // 2, card_top + 245),
            f"Round {presentation.round_number} of {presentation.total_rounds}",
            fill=self.theme.muted_text,
            font=_font(30),
            anchor="mm",
        )

        footer = (
            f"Next: {presentation.next_opponent}"
            if presentation.next_opponent
            else "Tournament run complete"
        )
        draw.text(
            (self.width // 2, 930),
            footer,
            fill=self.theme.text,
            font=_font(36),
            anchor="mm",
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(output_path, format="PNG", optimize=True)


def _plural(value: float, singular: str, plural: str | None = None) -> str:
    noun = singular if value == 1 else (plural or f"{singular}s")
    return f"{value:g} {noun}"