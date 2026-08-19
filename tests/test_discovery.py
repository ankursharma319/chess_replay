from datetime import UTC, date, datetime

import httpx

from chess_replay.ingestion.chess_com import ArchivedGame, ChessComClient, Participant
from chess_replay.ingestion.discovery import (
    discover_daily_games,
    discover_tournament,
    resolve_player,
)


def test_resolves_known_real_name_to_profile() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/pub/player/magnuscarlsen"
        return httpx.Response(
            200,
            json={"username": "MagnusCarlsen", "name": "Magnus Carlsen", "title": "GM"},
        )

    with ChessComClient("test/1.0", transport=httpx.MockTransport(handler)) as client:
        profile = resolve_player(client, "Magnus Carlsen")

    assert profile.username == "MagnusCarlsen"


def test_resolves_arjun_erigaisi_to_active_gm_account() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/pub/player/ghandeevam2003"
        return httpx.Response(
            200,
            json={
                "username": "ghandeevam2003",
                "name": "Arjun Erigaisi",
                "title": "GM",
            },
        )

    with ChessComClient("test/1.0", transport=httpx.MockTransport(handler)) as client:
        profile = resolve_player(client, "Arjun Erigaisi")

    assert profile.username == "ghandeevam2003"


def test_resolves_requested_player_aliases_to_active_gm_accounts() -> None:
    aliases = {
        "Nihal Sarin": "nihalsarin",
        "Hans Niemann": "hansontwitch",
        "Gukesh D": "gukeshdommaraju",
        "Pragg": "rpragchess",
        "Vidit": "viditchess",
    }

    for display_name, username in aliases.items():
        def handler(
            request: httpx.Request,
            expected=username,
            expected_name=display_name,
        ) -> httpx.Response:
            assert request.url.path == f"/pub/player/{expected}"
            return httpx.Response(
                200,
                json={
                    "username": expected,
                    "name": expected_name,
                    "title": "GM",
                },
            )

        with ChessComClient(
            "test/1.0",
            transport=httpx.MockTransport(handler),
        ) as client:
            profile = resolve_player(client, display_name)

        assert profile.username == username


def test_discovers_unique_tournament_by_utc_date_and_name() -> None:
    tournament_url = (
        "https://www.chess.com/tournament/live/"
        "titled-tuesday-blitz-august-18-2026-6666505"
    )
    games = (
        _game("2", tournament_url, "2026.08.18", 20),
        _game("1", tournament_url, "2026.08.18", 10),
        _game("3", tournament_url, "2026.08.19", 30),
    )

    discovered = discover_tournament(games, date(2026, 8, 18), "Titled Tuesday")

    assert discovered.slug == "titled-tuesday-blitz-august-18-2026-6666505"
    assert [game.source_id for game in discovered.games] == ["1", "2"]


def test_discovers_non_tournament_daily_games_in_chronological_order() -> None:
    games = (
        _game("2", None, "2026.08.17", 20),
        _game("1", None, "2026.08.17", 10),
        _game("3", "event-url", "2026.08.17", 30),
        _game("4", None, "2026.08.18", 40),
    )

    selected = discover_daily_games(games, date(2026, 8, 17))

    assert [game.source_id for game in selected] == ["1", "2"]


def _game(
    source_id: str,
    tournament_url: str | None,
    utc_date: str,
    end_second: int,
) -> ArchivedGame:
    participant = Participant("Player", 3000, "win")
    return ArchivedGame(
        source_id=source_id,
        url=f"https://www.chess.com/game/live/{source_id}",
        pgn=f'[UTCDate "{utc_date}"]\n\n*',
        end_time=datetime(2026, 8, 18, 15, 0, end_second, tzinfo=UTC),
        time_control="300",
        time_class="blitz",
        rules="chess",
        rated=True,
        final_fen="",
        tournament_url=tournament_url,
        white=participant,
        black=Participant("Opponent", 3000, "resigned"),
    )