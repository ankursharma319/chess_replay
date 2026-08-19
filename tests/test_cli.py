from chess_replay.cli import build_parser


def test_builds_command_tree() -> None:
    parser = build_parser()

    parsed = parser.parse_args(["inspect-pgn", "game.pgn"])

    assert parsed.command == "inspect-pgn"


def test_parses_single_command_tournament_render_with_commentary_off() -> None:
    parser = build_parser()

    parsed = parser.parse_args(
        ["render-tournament", "Magnus Carlsen", "2026-08-18"]
    )

    assert parsed.player == "Magnus Carlsen"
    assert parsed.date.isoformat() == "2026-08-18"
    assert parsed.tournament == "Titled Tuesday"
    assert parsed.narrator == "off"
    assert not parsed.no_evaluation


def test_parses_daily_non_tournament_render_by_default() -> None:
    parsed = build_parser().parse_args(
        ["render-day", "Magnus Carlsen", "2026-08-17"]
    )

    assert parsed.player == "Magnus Carlsen"
    assert parsed.date.isoformat() == "2026-08-17"
    assert parsed.narrator == "off"
    assert not parsed.include_tournament
    assert not parsed.no_evaluation