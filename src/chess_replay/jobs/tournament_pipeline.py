"""Render a player's complete tournament run as one compilation video."""

from __future__ import annotations

import json
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import chess

from chess_replay.chess.pgn import ParsedGame, parse_pgn
from chess_replay.ingestion.chess_com import ArchivedGame, ChessComClient, PlayerProfile
from chess_replay.ingestion.discovery import DiscoveredTournament
from chess_replay.ingestion.tournament import (
    PlayerTournamentGame,
    PlayerTournamentState,
    TournamentContextLoader,
    TournamentGameContext,
)
from chess_replay.jobs.pipeline import RenderResult, ReplayPipeline
from chess_replay.media.ffmpeg import FFmpegEncoder
from chess_replay.rendering.presentation import PlayerPresentation, ReplayPresentation
from chess_replay.rendering.transition import TransitionPresentation, TransitionRenderer


@dataclass(frozen=True, slots=True)
class CompilationResult:
    video_path: Path
    manifest_path: Path
    game_count: int
    total_duration_seconds: float


class TournamentCompilationPipeline:
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
        tournament: DiscoveredTournament,
        output_path: Path,
        *,
        include_commentary: bool,
        keep_intermediates: bool = False,
    ) -> CompilationResult:
        run = TournamentContextLoader(self.client).load_player(
            tournament.slug,
            player.username,
        )
        archive_by_url = {game.url: game for game in tournament.games}
        missing = [entry.game_url for entry in run if entry.game_url not in archive_by_url]
        if missing:
            raise ValueError(
                "Monthly archive is missing tournament games: " + ", ".join(missing)
            )

        if keep_intermediates:
            work_directory = output_path.parent / f"{output_path.stem}-parts"
            if work_directory.exists():
                shutil.rmtree(work_directory)
            work_directory.mkdir(parents=True)
            return self._render_in_directory(
                player,
                tournament,
                run,
                archive_by_url,
                output_path,
                work_directory,
                include_commentary,
            )
        with tempfile.TemporaryDirectory(prefix="chess-replay-tournament-") as temporary:
            return self._render_in_directory(
                player,
                tournament,
                run,
                archive_by_url,
                output_path,
                Path(temporary),
                include_commentary,
            )

    def _render_in_directory(
        self,
        player: PlayerProfile,
        tournament: DiscoveredTournament,
        run: tuple[PlayerTournamentGame, ...],
        archive_by_url: dict[str, ArchivedGame],
        output_path: Path,
        work_directory: Path,
        include_commentary: bool,
    ) -> CompilationResult:
        profiles: dict[str, PlayerProfile] = {player.username.casefold(): player}
        avatars: dict[str, Path | None] = {}
        flags: dict[str, Path | None] = {}
        target_avatar = self.client.download_avatar(player, self.avatar_directory)
        avatars[player.username.casefold()] = target_avatar
        flags[player.username.casefold()] = self.client.download_country_flag(
            player,
            self.avatar_directory.parent / "flags",
        )
        segments: list[Path] = []
        game_manifests: list[dict[str, object]] = []
        total_duration = 0.0

        for index, entry in enumerate(run):
            archived = archive_by_url[entry.game_url]
            parsed = parse_pgn(archived.pgn)
            presentation = self._presentation(
                parsed,
                entry.context,
                profiles,
                avatars,
                flags,
                player.username,
                game_format=archived.game_format_label,
            )
            round_number = entry.context.round_number
            self.progress(f"Rendering round {round_number}: {entry.game_url}")

            pgn_path = work_directory / f"round-{round_number:02d}.pgn"
            pgn_path.write_text(archived.pgn, encoding="utf-8")
            game_path = work_directory / f"round-{round_number:02d}.mp4"
            render_result = self.replay_pipeline.render_pgn(
                pgn_path,
                game_path,
                presentation=presentation,
                include_commentary=include_commentary,
            )
            segments.append(game_path)
            total_duration += render_result.duration_seconds

            next_opponent = None
            if index + 1 < len(run):
                next_username = run[index + 1].opponent_username
                next_key = next_username.casefold()
                if next_key not in profiles:
                    profiles[next_key] = self.client.get_player(next_username)
                next_profile = profiles[next_key]
                next_opponent = next_profile.name or next_profile.username
            opponent_profile = profiles[entry.opponent_username.casefold()]
            transition = TransitionPresentation(
                player_name=player.name or player.username,
                player_title=player.title,
                opponent_name=opponent_profile.name or opponent_profile.username,
                opponent_title=opponent_profile.title,
                result_label=entry.result_label,
                termination_label=archived.termination_label,
                game_format=archived.game_format_label,
                score_after=entry.score_after,
                wins=entry.wins_after,
                draws=entry.draws_after,
                losses=entry.losses_after,
                round_number=round_number,
                total_rounds=entry.context.total_rounds,
                tournament_name=entry.context.tournament_name,
                next_opponent=next_opponent,
            )
            transition_image = work_directory / f"round-{round_number:02d}-result.png"
            transition_path = work_directory / f"round-{round_number:02d}-result.mp4"
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
                _game_manifest(entry, archived, render_result, opponent_profile)
            )

        self.progress(f"Concatenating {len(run)} games into {output_path}")
        self.encoder.concatenate(segments, output_path)
        manifest_path = output_path.with_suffix(".json")
        manifest = {
            "video_path": str(output_path),
            "player": {
                "username": player.username,
                "name": player.name,
                "title": player.title,
            },
            "tournament_url": tournament.url,
            "tournament_slug": tournament.slug,
            "game_count": len(run),
            "total_duration_seconds": round(total_duration, 3),
            "transition_seconds": self.transition_seconds,
            "evaluation_enabled": getattr(self.replay_pipeline, "evaluator", None) is not None,
            "primary_player_at_bottom": True,
            "games": game_manifests,
        }
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return CompilationResult(
            video_path=output_path,
            manifest_path=manifest_path,
            game_count=len(run),
            total_duration_seconds=round(total_duration, 3),
        )

    def _presentation(
        self,
        game: ParsedGame,
        context: TournamentGameContext,
        profiles: dict[str, PlayerProfile],
        avatars: dict[str, Path | None],
        flags: dict[str, Path | None],
        primary_username: str,
        *,
        game_format: str | None = None,
    ) -> ReplayPresentation:
        white = self._player_presentation(
            game.headers.get("White", "White"),
            game.headers.get("WhiteElo", ""),
            context.white,
            profiles,
            avatars,
            flags,
        )
        black = self._player_presentation(
            game.headers.get("Black", "Black"),
            game.headers.get("BlackElo", ""),
            context.black,
            profiles,
            avatars,
            flags,
        )
        return ReplayPresentation(
            white=white,
            black=black,
            tournament_name=context.tournament_name,
            round_number=context.round_number,
            total_rounds=context.total_rounds,
            game_format=game_format,
            bottom_color=(
                chess.BLACK
                if black.username.casefold() == primary_username.casefold()
                else chess.WHITE
            ),
        )

    def _player_presentation(
        self,
        username: str,
        rating: str,
        state: PlayerTournamentState,
        profiles: dict[str, PlayerProfile],
        avatars: dict[str, Path | None],
        flags: dict[str, Path | None],
    ) -> PlayerPresentation:
        key = username.casefold()
        if key not in profiles:
            profiles[key] = self.client.get_player(username)
        profile = profiles[key]
        if key not in avatars:
            avatars[key] = self.client.download_avatar(profile, self.avatar_directory)
        if key not in flags:
            flags[key] = self.client.download_country_flag(
                profile,
                self.avatar_directory.parent / "flags",
            )
        return PlayerPresentation(
            username=profile.username,
            rating=rating,
            name=profile.name,
            title=profile.title,
            avatar_path=avatars[key],
            country_code=profile.country_code,
            flag_path=flags[key],
            score_before=state.score_before,
            game_number=state.game_number,
            standing_label=state.standing_label,
        )


def _game_manifest(
    entry: PlayerTournamentGame,
    archived: ArchivedGame,
    rendered: RenderResult,
    opponent: PlayerProfile,
) -> dict[str, object]:
    return {
        "round": entry.context.round_number,
        "game_url": archived.url,
        "opponent": opponent.name or opponent.username,
        "opponent_username": opponent.username,
        "opponent_title": opponent.title,
        "result": entry.result_label,
        "termination": archived.termination_label,
        "game_format": archived.game_format_label,
        "score_after": entry.score_after,
        "record_after": {
            "wins": entry.wins_after,
            "draws": entry.draws_after,
            "losses": entry.losses_after,
        },
        "duration_seconds": rendered.duration_seconds,
    }