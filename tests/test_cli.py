from chess_replay.cli import build_parser


def test_builds_command_tree() -> None:
    parser = build_parser()

    parsed = parser.parse_args(["inspect-pgn", "game.pgn"])

    assert parsed.command == "inspect-pgn"