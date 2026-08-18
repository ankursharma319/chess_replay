from chess_replay.chess.pgn import parse_pgn
from chess_replay.media.commentary import CommentaryGenerator, DmitriCommentaryGenerator
from chess_replay.rendering.presentation import PlayerPresentation, ReplayPresentation


def test_generates_original_event_commentary() -> None:
    game = parse_pgn("1. f3 e5 2. g4 Qh4# 0-1")
    presentation = ReplayPresentation(
        white=PlayerPresentation(username="white", name="White Player"),
        black=PlayerPresentation(username="black", name="Black Player"),
    )

    cues = CommentaryGenerator().generate(game, presentation)

    assert cues[0].text == "White Player has White against Black Player."
    assert cues[-1].ply_number == 4
    assert cues[-1].text == "Black Player delivers checkmate with Qh4#."


def test_generates_dmitri_move_key_for_every_ply() -> None:
    game = parse_pgn("1. e4 d5 2. exd5 *")
    presentation = ReplayPresentation(
        white=PlayerPresentation(username="white"),
        black=PlayerPresentation(username="black"),
    )

    cues = DmitriCommentaryGenerator().generate(game, presentation)

    move_cues = [cue for cue in cues if cue.kind == "move"]
    assert [cue.clip_key for cue in move_cues] == ["e4", "d5", "exd5"]