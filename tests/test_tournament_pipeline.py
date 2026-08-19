import json
from datetime import UTC, datetime

import chess

from chess_replay.chess.pgn import parse_pgn
from chess_replay.ingestion.chess_com import ArchivedGame, Participant, PlayerProfile
from chess_replay.ingestion.discovery import DiscoveredTournament
from chess_replay.ingestion.tournament import (
    PlayerTournamentGame,
    PlayerTournamentState,
    TournamentGameContext,
)
from chess_replay.jobs.pipeline import RenderResult
from chess_replay.jobs.tournament_pipeline import TournamentCompilationPipeline


class FakeClient:
    def download_avatar(self, profile, directory):
        return None

    def get_player(self, username):
        return PlayerProfile(username, f"Real {username}", "GM", None, None, None)

    def download_country_flag(self, profile, directory):
        return None


class FakeReplayPipeline:
    frame_rate = 30

    def render_pgn(self, pgn_path, output_path, **kwargs):
        output_path.write_bytes(b"game")
        manifest = output_path.with_suffix(".json")
        manifest.write_text("{}", encoding="utf-8")
        return RenderResult(output_path, manifest, 1, 10)


class FakeTransitionRenderer:
    def render(self, presentation, output_path):
        output_path.write_bytes(b"image")


class FakeEncoder:
    def encode_still(self, image_path, output_path, **kwargs):
        output_path.write_bytes(b"transition")

    def concatenate(self, segments, output_path):
        output_path.write_bytes(b"".join(path.read_bytes() for path in segments))


def test_compiles_games_and_transitions_into_one_manifest(tmp_path, monkeypatch) -> None:
    context = TournamentGameContext(
        "Titled Tuesday",
        1,
        11,
        PlayerTournamentState("Player", 0, 1, 1, 2),
        PlayerTournamentState("Opponent", 0, 1, 1, 2),
    )
    run = (
        PlayerTournamentGame(
            "game-url",
            context,
            "Opponent",
            "win",
            "Won",
            1,
            1,
            0,
            0,
        ),
    )
    monkeypatch.setattr(
        "chess_replay.jobs.tournament_pipeline.TournamentContextLoader.load_player",
        lambda *_: run,
    )
    archived = _archived_game()
    discovered = DiscoveredTournament("event-url", "event", (archived,))
    output = tmp_path / "compilation.mp4"
    pipeline = TournamentCompilationPipeline(
        FakeClient(),
        FakeReplayPipeline(),
        FakeTransitionRenderer(),
        FakeEncoder(),
        avatar_directory=tmp_path / "avatars",
        transition_seconds=4,
    )

    result = pipeline.render(
        PlayerProfile("Player", "Real Player", "GM", None, None, None),
        discovered,
        output,
        include_commentary=False,
    )

    assert output.read_bytes() == b"gametransition"
    assert result.game_count == 1
    assert result.total_duration_seconds == 14
    assert result.manifest_path.is_file()
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["games"][0]["termination"] == "Resignation"
    assert manifest["games"][0]["game_format"] == "Blitz 5+0"


def test_places_primary_player_at_bottom_when_playing_black(tmp_path) -> None:
    pipeline = TournamentCompilationPipeline(
        FakeClient(),
        FakeReplayPipeline(),
        FakeTransitionRenderer(),
        FakeEncoder(),
        avatar_directory=tmp_path / "avatars",
    )
    context = TournamentGameContext(
        "Event",
        1,
        1,
        PlayerTournamentState("Opponent", 0, 1, 1, 1),
        PlayerTournamentState("Player", 0, 1, 1, 1),
    )

    presentation = pipeline._presentation(
        parse_pgn('[White "Opponent"]\n[Black "Player"]\n\n1. e4 *'),
        context,
        {},
        {},
        {},
        "Player",
        game_format="Blitz 5+0",
    )

    assert presentation.bottom_color == chess.BLACK
    assert presentation.event_line == "Event\nBlitz 5+0  ·  Round 1/1"


def _archived_game() -> ArchivedGame:
    return ArchivedGame(
        "1",
        "game-url",
        '[White "Player"]\n[Black "Opponent"]\n[Result "1-0"]\n\n1. e4 e5 1-0',
        datetime(2026, 8, 18, tzinfo=UTC),
        "300",
        "blitz",
        "chess",
        True,
        "",
        "event-url",
        Participant("Player", 3000, "win"),
        Participant("Opponent", 3000, "resigned"),
    )