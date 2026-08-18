"""Generate concise original commentary from observable chess events."""

from __future__ import annotations

from dataclasses import dataclass

from chess_replay.chess.pgn import ParsedGame
from chess_replay.rendering.presentation import ReplayPresentation


@dataclass(frozen=True, slots=True)
class CommentaryCue:
    ply_number: int
    text: str
    kind: str = "commentary"


class CommentaryGenerator:
    """Create selective factual lines without imitating a named commentator."""

    def generate(
        self,
        game: ParsedGame,
        presentation: ReplayPresentation,
    ) -> tuple[CommentaryCue, ...]:
        white = presentation.white.display_name
        black = presentation.black.display_name
        cues = [CommentaryCue(0, f"{white} has White against {black}.", "intro")]

        for ply in game.plies:
            mover = white if ply.number % 2 == 1 else black
            if ply.is_checkmate:
                cues.append(
                    CommentaryCue(
                        ply.number,
                        f"{mover} delivers checkmate with {ply.san}.",
                        "checkmate",
                    )
                )
            elif ply.promotion_piece:
                cues.append(
                    CommentaryCue(
                        ply.number,
                        f"{mover} promotes the pawn to a {ply.promotion_piece}.",
                        "promotion",
                    )
                )
            elif ply.is_check:
                cues.append(
                    CommentaryCue(ply.number, f"{mover} gives check with {ply.san}.", "check")
                )
            elif ply.is_castling:
                side = "queenside" if ply.san.startswith("O-O-O") else "kingside"
                cues.append(CommentaryCue(ply.number, f"{mover} castles {side}.", "castle"))
            elif ply.captured_piece in {"queen", "rook"}:
                cues.append(
                    CommentaryCue(
                        ply.number,
                        f"{mover} captures the {ply.captured_piece} with {ply.san}.",
                        "capture",
                    )
                )

        if game.plies and not game.plies[-1].is_checkmate:
            result = _spoken_result(game.result)
            cues.append(
                CommentaryCue(
                    game.plies[-1].number,
                    f"The game ends. {result}",
                    "result",
                )
            )
        return tuple(cues)


def _spoken_result(result: str) -> str:
    if result == "1-0":
        return "White wins."
    if result == "0-1":
        return "Black wins."
    if result == "1/2-1/2":
        return "The game is drawn."
    return "The result is not recorded."