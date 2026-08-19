"""Render a player's games from one UTC date as a compilation video."""

from __future__ import annotations

import json
import shutil
import tempfile
from collections.abc import Callable, Mapping
from datetime import date
from pathlib import Path

import chess

from chess_replay.chess.pgn import ParsedGame, parse_pgn
from chess_replay.ingestion.chess_com import ArchivedGame, ChessComClient, PlayerProfile
from chess_replay.ingestion.discovery import discover_daily_games
from chess_replay.ingestion.tournament import result_label, result_points
from chess_replay.jobs.pipeline import RenderResult, ReplayPipeline
from chess_replay.jobs.tournament_pipeline import CompilationResult
from chess_replay.media.ffmpeg import FFmpegEncoder
from chess_replay.rendering.presentation import PlayerPresentation, ReplayPresentation
from chess_replay.rendering.transition import TransitionPresentation, TransitionRenderer


class DailyCompilationPipeline:
    """Compile chronologically ordered games from one day without tournament context."""

    def __init__(
        self,
        client: ChessComClient,
        replay_pipeline: ReplayPipeline,
        transition_renderer: TransitionRenderer,
        encoder: FFmpegEncoder,
        *,
        avatar_directory: Path,
        transition_seconds: float = 4.0,
        progress: Callable[[str], None] | None = None,
    ) -> None:
        if transition_seconds <= 0:
            raise ValueError("transition_seconds must be positive")
        self.client = client
        self.replay_pipeline = replay_pipeline
        self.transition_renderer = transition_renderer
        self.encoder = encoder
        self.avatar_directory = avatar_directory
        self.transition_seconds = transition_seconds
        self.progress = progress or (lambda _: None)

    def render(
        self,
        player: PlayerProfile,
        games: tuple[ArchivedGame, ...],
        event_date: date,
        output_path: Path,
        *,
        include_commentary: bool,
        keep_intermediates: bool = False,
    ) -> CompilationResult:
        if not games:
            raise ValueError("At least one daily game is required")
        if keep_intermediates:
            work_directory = output_path.parent / f"{output_path.stem}-parts"
            if work_directory.exists():
                shutil.rmtree(work_directory)
            work_directory.mkdir(parents=True)
            return self._render_in_directory(
                player,
                games,
                event_date,
                output_path,
                work_directory,
                include_commentary,
            )
        with tempfile.TemporaryDirectory(prefix="chess-replay-daily-") as temporary:
            return self._render_in_directory(
                player,
                games,
                event_date,
                output_path,
                Path(temporary),
                include_commentary,
            )

    def _render_in_directory(
        self,
        player: PlayerProfile,
        games: tuple[ArchivedGame, ...],
        event_date: date,
        output_path: Path,
        work_directory: Path,
        include_commentary: bool,
    ) -> CompilationResult:
        player_key = player.username.casefold()
        profiles: dict[str, PlayerProfile] = {player_key: player}
        avatars: dict[str, Path | None] = {}
        flags: dict[str, Path | None] = {}
        self._cache_media(player, avatars, flags)
        segments: list[Path] = []
        game_manifests: list[dict[str, object]] = []
        total_duration = 0.0
        wins = draws = losses = 0
        points = 0.0
        total_games = len(games)
        session_label = f"{player.name or player.username} | {_date_label(event_date)}"
        daily_games: dict[str, tuple[ArchivedGame, ...]] = {player_key: games}

        for index, archived in enumerate(games, start=1):
            parsed = parse_pgn(archived.pgn)
            opponent_username, player_result = _player_game_details(archived, player_key)
            opponent = self._profile(opponent_username, profiles, avatars, flags)
            opponent_key = opponent.username.casefold()
            if opponent_key not in daily_games:
                opponent_archive = self.client.get_player_month(
                    opponent.username,
                    event_date.year,
                    event_date.month,
                )
                daily_games[opponent_key] = discover_daily_games(
                    opponent_archive,
                    event_date,
                )
            records = {
                player_key: (wins, draws, losses),
                opponent_key: _record_before(
                    daily_games[opponent_key],
                    opponent_key,
                    archived,
                ),
            }
            presentation = self._presentation(
                parsed,
                player,
                profiles,
                avatars,
                flags,
                session_label,
                archived.game_format_label,
                index,
                total_games,
                records,
            )
            self.progress(f"Rendering game {index}/{total_games}: {archived.url}")
            stem = f"game-{index:02d}"
            pgn_path = work_directory / f"{stem}.pgn"
            pgn_path.write_text(archived.pgn, encoding="utf-8")
            game_path = work_directory / f"{stem}.mp4"
            rendered = self.replay_pipeline.render_pgn(
                pgn_path,
                game_path,
                presentation=presentation,
                include_commentary=include_commentary,
            )
            segments.append(game_path)
            total_duration += rendered.duration_seconds

            label = result_label(player_result)
            points += result_points(player_result)
            if label == "Won":
                wins += 1
            elif label == "Drew":
                draws += 1
            else:
                losses += 1
            next_opponent = None
            if index < total_games:
                next_username, _ = _player_game_details(games[index], player_key)
                next_profile = self._profile(next_username, profiles, avatars, flags)
                next_opponent = next_profile.name or next_profile.username
            transition = TransitionPresentation(
                player_name=player.name or player.username,
                player_title=player.title,
                opponent_name=opponent.name or opponent.username,
                opponent_title=opponent.title,
                result_label=label,
                termination_label=archived.termination_label,
                game_format=archived.game_format_label,
                score_after=points,
                wins=wins,
                draws=draws,
                losses=losses,
                round_number=index,
                total_rounds=total_games,
                tournament_name=session_label,
                next_opponent=next_opponent,
                score_heading=f"Game {index} of {total_games}",
                progress_label=f"Daily record after {index} game{'s' if index != 1 else ''}",
                completion_label="Daily session complete",
            )
            transition_image = work_directory / f"{stem}-result.png"
            transition_path = work_directory / f"{stem}-result.mp4"
            self.transition_renderer.render(transition, transition_image)
            self.encoder.encode_still(
                transition_image,
                transition_path,
                duration_seconds=self.transition_seconds,
                frame_rate=self.replay_pipeline.frame_rate,
            )
            segments.append(transition_path)
            total_duration += self.transition_seconds
            game_manifests.append(
                _daily_game_manifest(
                    index,
                    archived,
                    rendered,
                    opponent,
                    label,
                    wins,
                    draws,
                    losses,
                    records[player_key],
                    records[opponent_key],
                )
            )

        self.progress(f"Concatenating {total_games} games into {output_path}")
        self.encoder.concatenate(segments, output_path)
        manifest_path = output_path.with_suffix(".json")
        manifest = {
            "video_path": str(output_path),
            "player": {
                "username": player.username,
                "name": player.name,
                "title": player.title,
            },
            "date": event_date.isoformat(),
            "non_tournament_only": all(game.tournament_url is None for game in games),
            "game_count": total_games,
            "total_duration_seconds": round(total_duration, 3),
            "transition_seconds": self.transition_seconds,
            "evaluation_enabled": self.replay_pipeline.evaluator is not None,
            "primary_player_at_bottom": True,
            "games": game_manifests,
        }
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return CompilationResult(
            video_path=output_path,
            manifest_path=manifest_path,
            game_count=total_games,
            total_duration_seconds=round(total_duration, 3),
        )

    def _presentation(
        self,
        game: ParsedGame,
        player: PlayerProfile,
        profiles: dict[str, PlayerProfile],
        avatars: dict[str, Path | None],
        flags: dict[str, Path | None],
        session_label: str,
        game_format: str,
        game_number: int,
        total_games: int,
        daily_records: Mapping[str, tuple[int, int, int]],
    ) -> ReplayPresentation:
        player_key = player.username.casefold()
        white_game_number = (
            game_number
            if game.headers.get("White", "").casefold() == player_key
            else None
        )
        black_game_number = (
            game_number
            if game.headers.get("Black", "").casefold() == player_key
            else None
        )
        white = self._player_presentation(
            game.headers.get("White", "White"),
            game.headers.get("WhiteElo", ""),
            profiles,
            avatars,
            flags,
            white_game_number,
            daily_records.get(game.headers.get("White", "").casefold()),
        )
        black = self._player_presentation(
            game.headers.get("Black", "Black"),
            game.headers.get("BlackElo", ""),
            profiles,
            avatars,
            flags,
            black_game_number,
            daily_records.get(game.headers.get("Black", "").casefold()),
        )
        return ReplayPresentation(
            white=white,
            black=black,
            tournament_name=session_label,
            game_format=game_format,
            progress_label=f"Game {game_number}/{total_games}",
            bottom_color=(
                chess.BLACK
                if black.username.casefold() == player.username.casefold()
                else chess.WHITE
            ),
        )

    def _player_presentation(
        self,
        username: str,
        rating: str,
        profiles: dict[str, PlayerProfile],
        avatars: dict[str, Path | None],
        flags: dict[str, Path | None],
        game_number: int | None,
        daily_record: tuple[int, int, int] | None,
    ) -> PlayerPresentation:
        profile = self._profile(username, profiles, avatars, flags)
        return PlayerPresentation(
            username=profile.username,
            rating=rating,
            name=profile.name,
            title=profile.title,
            avatar_path=avatars[username.casefold()],
            country_code=profile.country_code,
            flag_path=flags[username.casefold()],
            game_number=game_number,
            daily_record=daily_record,
        )

    def _profile(
        self,
        username: str,
        profiles: dict[str, PlayerProfile],
        avatars: dict[str, Path | None],
        flags: dict[str, Path | None],
    ) -> PlayerProfile:
        key = username.casefold()
        if key not in profiles:
            profiles[key] = self.client.get_player(username)
            self._cache_media(profiles[key], avatars, flags)
        return profiles[key]

    def _cache_media(
        self,
        profile: PlayerProfile,
        avatars: dict[str, Path | None],
        flags: dict[str, Path | None],
    ) -> None:
        key = profile.username.casefold()
        avatars[key] = self.client.download_avatar(profile, self.avatar_directory)
        flags[key] = self.client.download_country_flag(
            profile,
            self.avatar_directory.parent / "flags",
        )


def _player_game_details(game: ArchivedGame, player_key: str) -> tuple[str, str]:
    if game.white.username.casefold() == player_key:
        return game.black.username, game.white.result
    if game.black.username.casefold() == player_key:
        return game.white.username, game.black.result
    raise ValueError(f"Player is not a participant in {game.url}")


def _date_label(value: date) -> str:
    return f"{value.strftime('%B')} {value.day}, {value.year}"


def _record_before(
    games: tuple[ArchivedGame, ...],
    player_key: str,
    current_game: ArchivedGame,
) -> tuple[int, int, int]:
    wins = draws = losses = 0
    for game in games:
        if game.url == current_game.url or game.end_time >= current_game.end_time:
            continue
        try:
            _, player_result = _player_game_details(game, player_key)
        except ValueError:
            continue
        label = result_label(player_result)
        if label == "Won":
            wins += 1
        elif label == "Drew":
            draws += 1
        else:
            losses += 1
    return wins, draws, losses


def _daily_game_manifest(
    game_number: int,
    archived: ArchivedGame,
    rendered: RenderResult,
    opponent: PlayerProfile,
    label: str,
    wins: int,
    draws: int,
    losses: int,
    player_record_before: tuple[int, int, int],
    opponent_record_before: tuple[int, int, int],
) -> dict[str, object]:
    return {
        "game_number": game_number,
        "game_url": archived.url,
        "opponent": opponent.name or opponent.username,
        "opponent_username": opponent.username,
        "opponent_title": opponent.title,
        "result": label,
        "termination": archived.termination_label,
        "game_format": archived.game_format_label,
        "player_record_before": player_record_before,
        "opponent_record_before": opponent_record_before,
        "record_after": {"wins": wins, "draws": draws, "losses": losses},
        "duration_seconds": rendered.duration_seconds,
    }