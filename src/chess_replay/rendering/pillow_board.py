"""Dependency-light chessboard frame renderer using Pillow."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import chess
from PIL import Image, ImageDraw, ImageFont, ImageOps

from chess_replay.analysis.stockfish import PositionEvaluation
from chess_replay.rendering.pieces import piece_sprite
from chess_replay.rendering.presentation import PlayerPresentation


@dataclass(frozen=True, slots=True)
class BoardTheme:
    background: str = "#171917"
    panel: str = "#242824"
    light_square: str = "#E7E0CF"
    dark_square: str = "#66806A"
    highlight: str = "#D6B84D"
    light_piece: str = "#F5F1E8"
    dark_piece: str = "#252925"
    text: str = "#F4F1E8"
    muted_text: str = "#AAAFA8"


class PillowBoardRenderer:
    """Render deterministic 16:9 replay frames without browser dependencies."""

    def __init__(self, width: int = 1920, height: int = 1080, theme: BoardTheme | None = None):
        self.width = width
        self.height = height
        self.theme = theme or BoardTheme()
        self.scale = min(width / 1920, height / 1080)

    def _scaled(self, value: int) -> int:
        return max(1, round(value * self.scale))

    def render(
        self,
        *,
        fen: str,
        output_path: Path,
        white: PlayerPresentation,
        black: PlayerPresentation,
        white_clock: float | None = None,
        black_clock: float | None = None,
        move_label: str = "Start",
        last_move_uci: str | None = None,
        event_label: str = "",
        bottom_color: chess.Color = chess.WHITE,
        evaluation: PositionEvaluation | None = None,
        evaluation_fraction: float | None = None,
    ) -> None:
        board = chess.Board(fen)
        image = Image.new("RGB", (self.width, self.height), self.theme.background)
        draw = ImageDraw.Draw(image)

        board_size = min(
            self.height - self._scaled(120),
            self.width - self._scaled(620),
        )
        board_size -= board_size % 8
        square_size = board_size // 8
        board_left = self._scaled(70)
        board_top = (self.height - board_size) // 2
        panel_left = board_left + board_size + self._scaled(70)
        panel_right = self.width - self._scaled(70)

        highlighted = _highlighted_squares(last_move_uci)
        for row in range(8):
            for column in range(8):
                square = _screen_square(row, column, bottom_color)
                color = (
                    self.theme.light_square
                    if (chess.square_rank(square) + chess.square_file(square)) % 2 == 1
                    else self.theme.dark_square
                )
                if square in highlighted:
                    color = self.theme.highlight
                x = board_left + column * square_size
                y = board_top + row * square_size
                draw.rectangle((x, y, x + square_size, y + square_size), fill=color)

                piece = board.piece_at(square)
                if piece is not None:
                    self._draw_piece(image, piece, x, y, square_size)

        if evaluation is not None:
            self._draw_evaluation_bar(
                draw,
                evaluation,
                left=board_left - self._scaled(38),
                top=board_top,
                height=board_size,
                bottom_color=bottom_color,
                white_fraction=evaluation_fraction,
            )

        draw.rounded_rectangle(
            (panel_left, board_top, panel_right, board_top + board_size),
            radius=self._scaled(8),
            fill=self.theme.panel,
        )
        title_font = _font(self._scaled(46), bold=True)
        name_font = _font(self._scaled(38), bold=True)
        clock_font = _font(self._scaled(64), bold=True)
        detail_font = _font(self._scaled(28))

        draw.text(
            (panel_left + self._scaled(42), board_top + self._scaled(42)),
            move_label,
            fill=self.theme.text,
            font=title_font,
        )
        if event_label:
            draw.text(
                (panel_left + self._scaled(42), board_top + self._scaled(105)),
                event_label,
                fill=self.theme.muted_text,
                font=detail_font,
            )
        top_player = white if bottom_color == chess.BLACK else black
        top_clock = white_clock if bottom_color == chess.BLACK else black_clock
        bottom_player = black if bottom_color == chess.BLACK else white
        bottom_clock = black_clock if bottom_color == chess.BLACK else white_clock
        self._draw_player(
            image,
            draw,
            left=panel_left + self._scaled(42),
            top=board_top + self._scaled(170),
            player=top_player,
            clock=top_clock,
            name_font=name_font,
            clock_font=clock_font,
            detail_font=detail_font,
        )
        self._draw_player(
            image,
            draw,
            left=panel_left + self._scaled(42),
            top=board_top + board_size - self._scaled(300),
            player=bottom_player,
            clock=bottom_clock,
            name_font=name_font,
            clock_font=clock_font,
            detail_font=detail_font,
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(output_path, format="PNG", optimize=True)

    def _draw_evaluation_bar(
        self,
        draw: ImageDraw.ImageDraw,
        evaluation: PositionEvaluation,
        *,
        left: int,
        top: int,
        height: int,
        bottom_color: chess.Color,
        white_fraction: float | None,
    ) -> None:
        width = self._scaled(26)
        fraction = evaluation.white_fraction if white_fraction is None else white_fraction
        white_height = round(height * max(0.0, min(1.0, fraction)))
        draw.rectangle((left, top, left + width, top + height), fill="#202220")
        if bottom_color == chess.WHITE:
            white_top = top + height - white_height
            draw.rectangle((left, white_top, left + width, top + height), fill="#F2EFE6")
        else:
            draw.rectangle((left, top, left + width, top + white_height), fill="#F2EFE6")
        draw.rectangle(
            (left, top, left + width, top + height),
            outline=self.theme.muted_text,
            width=self._scaled(2),
        )
        label_font = _font(self._scaled(18), bold=True)
        label = evaluation.label
        box = draw.textbbox((0, 0), label, font=label_font)
        text_width = box[2] - box[0]
        text_height = box[3] - box[1]
        label_width = max(width, text_width + self._scaled(10))
        label_height = text_height + self._scaled(6)
        label_left = left - (label_width - width) // 2
        label_top = top + height // 2 - label_height // 2
        draw.rectangle(
            (label_left, label_top, label_left + label_width, label_top + label_height),
            fill=self.theme.panel,
        )
        draw.text(
            (
                left + (width - text_width) / 2,
                label_top + self._scaled(3) - box[1],
            ),
            label,
            fill=self.theme.text,
            font=label_font,
        )

    def _draw_piece(
        self,
        image: Image.Image,
        piece: chess.Piece,
        left: int,
        top: int,
        square_size: int,
    ) -> None:
        sprite_size = max(24, int(square_size * 0.9))
        sprite = piece_sprite(piece.symbol(), sprite_size)
        image.paste(
            sprite,
            (
                left + (square_size - sprite.width) // 2,
                top + (square_size - sprite.height) // 2,
            ),
            sprite,
        )

    def _draw_player(
        self,
        image: Image.Image,
        draw: ImageDraw.ImageDraw,
        *,
        left: int,
        top: int,
        player: PlayerPresentation,
        clock: float | None,
        name_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        clock_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        detail_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    ) -> None:
        avatar_size = self._scaled(104)
        self._draw_avatar(image, draw, player, left, top, avatar_size)
        text_left = left + avatar_size + self._scaled(26)
        draw.text((text_left, top), player.display_name, fill=self.theme.text, font=name_font)
        if player.metadata_line:
            metadata_left = text_left
            if player.flag_path and player.flag_path.is_file():
                self._draw_flag(
                    image,
                    draw,
                    player.flag_path,
                    text_left,
                    top + self._scaled(58),
                )
                metadata_left += self._scaled(54)
            draw.text(
                (metadata_left, top + self._scaled(54)),
                player.metadata_line,
                fill=self.theme.muted_text,
                font=detail_font,
            )
        draw.text(
            (text_left, top + self._scaled(105)),
            _format_clock(clock),
            fill=self.theme.text,
            font=clock_font,
        )
        if player.tournament_line:
            draw.text(
                (text_left, top + self._scaled(184)),
                player.tournament_line,
                fill=self.theme.highlight,
                font=detail_font,
            )

    def _draw_avatar(
        self,
        image: Image.Image,
        draw: ImageDraw.ImageDraw,
        player: PlayerPresentation,
        left: int,
        top: int,
        size: int,
    ) -> None:
        if player.avatar_path and player.avatar_path.is_file():
            with Image.open(player.avatar_path) as source:
                avatar = ImageOps.fit(source.convert("RGB"), (size, size))
            mask = Image.new("L", (size, size), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
            image.paste(avatar, (left, top), mask)
            return

        draw.ellipse(
            (left, top, left + size, top + size),
            fill=self.theme.background,
            outline=self.theme.muted_text,
            width=self._scaled(2),
        )
        initial = player.display_name[:1].upper() or "?"
        font = _font(size // 2, bold=True)
        box = draw.textbbox((0, 0), initial, font=font)
        draw.text(
            (
                left + (size - (box[2] - box[0])) / 2,
                top + (size - (box[3] - box[1])) / 2 - box[1],
            ),
            initial,
            fill=self.theme.text,
            font=font,
        )

    def _draw_flag(
        self,
        image: Image.Image,
        draw: ImageDraw.ImageDraw,
        path: Path,
        left: int,
        top: int,
    ) -> None:
        bounds = (self._scaled(42), self._scaled(28))
        with Image.open(path) as source:
            flag = ImageOps.contain(source.convert("RGB"), bounds)
        x = left + (bounds[0] - flag.width) // 2
        y = top + (bounds[1] - flag.height) // 2
        draw.rectangle(
            (left - 1, top - 1, left + bounds[0], top + bounds[1]),
            fill=self.theme.background,
            outline=self.theme.muted_text,
            width=1,
        )
        image.paste(flag, (x, y))


def _highlighted_squares(last_move_uci: str | None) -> set[chess.Square]:
    if not last_move_uci:
        return set()
    try:
        move = chess.Move.from_uci(last_move_uci)
    except ValueError:
        return set()
    return {move.from_square, move.to_square}


def _screen_square(row: int, column: int, bottom_color: chess.Color) -> chess.Square:
    if bottom_color == chess.WHITE:
        return chess.square(column, 7 - row)
    return chess.square(7 - column, row)


def _format_clock(seconds: float | None) -> str:
    if seconds is None:
        return "--:--"
    total_seconds = max(0, math.ceil(seconds))
    minutes, whole_seconds = divmod(total_seconds, 60)
    return f"{minutes:02d}:{whole_seconds:02d}"


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    windows_font = Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf")
    candidates = [windows_font, Path("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")]
    for candidate in candidates:
        try:
            return ImageFont.truetype(str(candidate), size=size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)