from collections.abc import Mapping
from typing import Any

from chess_replay.ingestion.tournament import TournamentContextLoader


class FakeTournamentSource:
    def get_tournament(self, slug: str) -> Mapping[str, Any]:
        return {"name": "Test Swiss", "settings": {"total_rounds": 3}}

    def get_tournament_round_groups(
        self,
        slug: str,
        round_number: int,
    ) -> tuple[Mapping[str, Any], ...]:
        players = [{"username": username, "points": 99} for username in "ABCD"]
        games = {
            1: [
                _game("round-1-a", "A", "win", "C", "resigned"),
                _game("round-1-b", "B", "win", "D", "resigned"),
            ],
            2: [_game("target", "A", "agreed", "B", "agreed")],
            3: [],
        }
        return ({"players": players, "games": games[round_number]},)


def test_reconstructs_score_game_number_and_score_rank_before_round() -> None:
    context = TournamentContextLoader(FakeTournamentSource()).load("event", "target")

    assert context.tournament_name == "Test Swiss"
    assert context.round_number == 2
    assert context.total_rounds == 3
    assert context.white.score_before == 1
    assert context.black.score_before == 1
    assert context.white.game_number == 2
    assert context.black.game_number == 2
    assert context.white.standing_label == "T-1"
    assert context.black.standing_label == "T-1"


def test_loads_player_run_with_score_and_record_progression() -> None:
    games = TournamentContextLoader(FakeTournamentSource()).load_player("event", "A")

    assert len(games) == 2
    assert games[0].context.round_number == 1
    assert games[0].result_label == "Won"
    assert games[0].score_after == 1
    assert (games[0].wins_after, games[0].draws_after, games[0].losses_after) == (1, 0, 0)
    assert games[1].context.round_number == 2
    assert games[1].result_label == "Drew"
    assert games[1].score_after == 1.5
    assert (games[1].wins_after, games[1].draws_after, games[1].losses_after) == (1, 1, 0)


def _game(
    url: str,
    white: str,
    white_result: str,
    black: str,
    black_result: str,
) -> Mapping[str, Any]:
    return {
        "url": url,
        "white": {"username": white, "result": white_result},
        "black": {"username": black, "result": black_result},
    }