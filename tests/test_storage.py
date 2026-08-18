from datetime import UTC, datetime

from chess_replay.ingestion.chess_com import ArchivedGame, Participant
from chess_replay.storage.catalog import GameCatalog


def test_catalog_upsert_is_idempotent(tmp_path) -> None:
    catalog = GameCatalog(tmp_path / "catalog.db")
    catalog.initialize()
    game = ArchivedGame(
        source_id="42",
        url="https://www.chess.com/game/live/42",
        pgn="1. e4 e5 *",
        end_time=datetime(2026, 8, 18, tzinfo=UTC),
        time_control="300",
        time_class="blitz",
        rules="chess",
        rated=True,
        final_fen="fen",
        tournament_url="https://www.chess.com/tournament/live/test",
        white=Participant("White", 2000, "win"),
        black=Participant("Black", 2000, "resigned"),
    )

    catalog.upsert_game(game)
    catalog.upsert_game(game)

    assert catalog.contains("42")
    assert catalog.count_games() == 1