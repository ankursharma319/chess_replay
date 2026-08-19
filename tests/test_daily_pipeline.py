import json
from datetime import UTC, date, datetime

import chess

from chess_replay.ingestion.chess_com import ArchivedGame, Participant, PlayerProfile
from chess_replay.jobs.daily_pipeline import DailyCompilationPipeline
from chess_replay.jobs.pipeline import RenderResult


class FakeClient:
    def __init__(self, games):
        self.games = games

    def get_player(self, username):
        return PlayerProfile(username, f"Real {username}", "GM", None, None, None)

    def download_avatar(self, profile, directory):
        return None

    def download_country_flag(self, profile, directory):
        return None

    def get_player_month(self, username, year, month):
        return self.games


class FakeReplayPipeline:
    frame_rate = 30
    evaluator = None

    def __init__(self):
        self.presentations = []

    def render_pgn(self, pgn_path, output_path, **kwargs):
        self.presentations.append(kwargs["presentation"])
        output_path.write_bytes(b"game")
        manifest = output_path.with_suffix(".json")
        manifest.write_text("{}", encoding="utf-8")
        return RenderResult(output_path, manifest, 1, 10)


class FakeTransitionRenderer:
    def __init__(self):
        self.presentations = []

    def render(self, presentation, output_path):
        self.presentations.append(presentation)
        output_path.write_bytes(b"image")


class FakeEncoder:
    def encode_still(self, image_path, output_path, **kwargs):
        output_path.write_bytes(b"transition")

    def concatenate(self, segments, output_path):
        output_path.write_bytes(b"".join(path.read_bytes() for path in segments))


def test_compiles_daily_games_with_sequence_and_running_record(tmp_path) -> None:
    games = (_game(1, player_is_white=True), _game(2, player_is_white=False))
    replay = FakeReplayPipeline()
    transitions = FakeTransitionRenderer()
    pipeline = DailyCompilationPipeline(
        FakeClient(games),
        replay,
        transitions,
        FakeEncoder(),
        avatar_directory=tmp_path / "avatars",
        transition_seconds=4,
    )
    output = tmp_path / "daily.mp4"

    result = pipeline.render(
        PlayerProfile("Player", "Real Player", "GM", None, None, None),
        games,
        date(2026, 8, 17),
        output,
        include_commentary=False,
    )

    assert output.read_bytes() == b"gametransitiongametransition"
    assert result.game_count == 2
    assert result.total_duration_seconds == 28
    assert replay.presentations[0].event_line == (
        "Real Player | August 17, 2026\nBlitz 3+0  ·  Game 1/2"
    )
    assert replay.presentations[1].bottom_color == chess.BLACK
    assert replay.presentations[0].white.daily_record == (0, 0, 0)
    assert replay.presentations[0].black.daily_record == (0, 0, 0)
    assert replay.presentations[1].black.daily_record == (1, 0, 0)
    assert replay.presentations[1].white.daily_record == (0, 0, 1)
    assert replay.presentations[1].black.tournament_line == "Game 2  ·  Day 1W · 0D · 0L"
    assert replay.presentations[1].white.tournament_line == "Day 0W · 0D · 1L"
    assert transitions.presentations[0].outcome_heading == "REAL PLAYER WON"
    assert transitions.presentations[1].outcome_heading == "REAL PLAYER LOST"
    assert (transitions.presentations[1].wins, transitions.presentations[1].losses) == (
        1,
        1,
    )
    assert transitions.presentations[1].completion_label == "Daily session complete"
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["date"] == "2026-08-17"
    assert manifest["non_tournament_only"]
    assert manifest["games"][1]["record_after"] == {
        "wins": 1,
        "draws": 0,
        "losses": 1,
    }
    assert manifest["games"][1]["player_record_before"] == [1, 0, 0]
    assert manifest["games"][1]["opponent_record_before"] == [0, 0, 1]


def _game(number: int, *, player_is_white: bool) -> ArchivedGame:
    player = Participant("Player", 3000, "win" if player_is_white else "resigned")
    opponent = Participant(
        "Opponent",
        2900,
        "resigned" if player_is_white else "win",
    )
    white = player if player_is_white else opponent
    black = opponent if player_is_white else player
    result = "1-0"
    return ArchivedGame(
        source_id=str(number),
        url=f"game-{number}",
        pgn=(
            f'[White "{white.username}"]\n'
            f'[Black "{black.username}"]\n'
            f'[WhiteElo "{white.rating}"]\n'
            f'[BlackElo "{black.rating}"]\n'
            '[TimeControl "180"]\n'
            f'[Result "{result}"]\n\n'
            f"1. e4 e5 {result}"
        ),
        end_time=datetime(2026, 8, 17, 15, number, tzinfo=UTC),
        time_control="180",
        time_class="blitz",
        rules="chess",
        rated=True,
        final_fen="",
        tournament_url=None,
        white=white,
        black=black,
    )
