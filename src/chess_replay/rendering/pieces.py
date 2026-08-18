"""Consistent Cburnett chess-piece sprites from python-chess SVG artwork."""

from __future__ import annotations

import io
from collections import deque
from functools import lru_cache

import chess
import chess.svg
from PIL import Image
from reportlab.graphics import renderPM
from svglib.svglib import svg2rlg

_SUPERSAMPLE_FACTOR = 4


@lru_cache(maxsize=24)
def piece_sprite(symbol: str, size: int) -> Image.Image:
    piece = chess.Piece.from_symbol(symbol)
    render_size = size * _SUPERSAMPLE_FACTOR
    svg = chess.svg.piece(piece, size=render_size)
    drawing = svg2rlg(io.BytesIO(svg.encode("utf-8")))
    if drawing is None:
        raise RuntimeError(f"Unable to parse SVG for chess piece {symbol}")
    png: bytes | None = None
    last_error: Exception | None = None
    for backend in ("rlPyCairo", "_renderPM"):
        try:
            png = renderPM.drawToString(drawing, fmt="PNG", backend=backend)
            break
        except (ImportError, OSError, RuntimeError) as error:
            last_error = error
    if png is None:
        raise RuntimeError("No ReportLab PNG rendering backend is available") from last_error
    sprite = Image.open(io.BytesIO(png)).convert("RGBA")
    _clear_edge_background(sprite)
    return sprite.resize((size, size), Image.Resampling.LANCZOS)


def _clear_edge_background(image: Image.Image) -> None:
    width, height = image.size
    pending = deque(
        [(x, 0) for x in range(width)]
        + [(x, height - 1) for x in range(width)]
        + [(0, y) for y in range(1, height - 1)]
        + [(width - 1, y) for y in range(1, height - 1)]
    )
    pixels = image.load()
    while pending:
        x, y = pending.popleft()
        red, green, blue, alpha = pixels[x, y]
        if alpha == 0 or min(red, green, blue) < 238:
            continue
        pixels[x, y] = (0, 0, 0, 0)
        if x > 0:
            pending.append((x - 1, y))
        if x + 1 < width:
            pending.append((x + 1, y))
        if y > 0:
            pending.append((x, y - 1))
        if y + 1 < height:
            pending.append((x, y + 1))