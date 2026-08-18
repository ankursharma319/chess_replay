import httpx

from chess_replay.ingestion.chess_com import ChessComClient


def test_fetches_archive_and_reuses_cached_response_after_304() -> None:
    requests: list[httpx.Request] = []
    payload = {
        "games": [
            {
                "url": "https://www.chess.com/game/live/42",
                "pgn": '[Event "Live Chess"]\n\n1. e4 e5 1/2-1/2',
                "end_time": 1_787_068_800,
                "time_control": "300",
                "time_class": "blitz",
                "rules": "chess",
                "rated": True,
                "fen": "test-fen",
                "tournament": "https://www.chess.com/tournament/live/test-event",
                "white": {"username": "White", "rating": 2000, "result": "agreed"},
                "black": {"username": "Black", "rating": 2001, "result": "agreed"},
            }
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json=payload, headers={"ETag": '"archive-v1"'})
        assert request.headers["If-None-Match"] == '"archive-v1"'
        return httpx.Response(304)

    with ChessComClient(
        "test/1.0 (contact: test@example.com)",
        transport=httpx.MockTransport(handler),
    ) as client:
        first = client.get_player_month("player", 2026, 8)
        second = client.get_player_month("player", 2026, 8)

    assert first == second
    assert first[0].source_id == "42"
    assert first[0].white.username == "White"
    assert len(requests) == 2


def test_fetches_profile_and_downloads_optional_avatar(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/pub/player/player":
            return httpx.Response(
                200,
                json={
                    "username": "Player",
                    "name": "Real Name",
                    "title": "GM",
                    "avatar": "https://images.example/avatar.png",
                    "fide": 2700,
                    "country": "https://api.chess.com/pub/country/US",
                },
            )
        return httpx.Response(200, content=b"image", headers={"Content-Type": "image/png"})

    with ChessComClient(
        "test/1.0 (contact: test@example.com)",
        transport=httpx.MockTransport(handler),
    ) as client:
        profile = client.get_player("player")
        avatar = client.download_avatar(profile, tmp_path)

    assert profile.name == "Real Name"
    assert profile.title == "GM"
    assert profile.fide_rating == 2700
    assert avatar == tmp_path / "player.png"
    assert avatar.read_bytes() == b"image"