"""Command-line interface for ingestion, rendering, and publishing."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from chess_replay.chess.pgn import parse_pgn_file
from chess_replay.config import Settings
from chess_replay.ingestion.chess_com import ChessComClient
from chess_replay.ingestion.tournament import TournamentContextLoader
from chess_replay.jobs.pipeline import ReplayPipeline
from chess_replay.jobs.timeline import TimelineBuilder
from chess_replay.media.ffmpeg import FFmpegEncoder
from chess_replay.media.narration import create_narrator
from chess_replay.publishing.youtube import YouTubePublisher, YouTubeVideo
from chess_replay.rendering.pillow_board import PillowBoardRenderer
from chess_replay.rendering.presentation import PlayerPresentation, ReplayPresentation
from chess_replay.storage.catalog import GameCatalog
from chess_replay.tools.dmitlichess import import_dmitlichess


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chess-replay",
        description="Fetch Chess.com games, render replay videos, and publish them.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    inspect = commands.add_parser("inspect-pgn", help="Parse a PGN and print replay metadata")
    inspect.add_argument("pgn", type=Path)
    inspect.set_defaults(handler=_inspect_pgn)

    fetch = commands.add_parser("fetch-player-month", help="Fetch and catalog a PubAPI month")
    fetch.add_argument("username")
    fetch.add_argument("year", type=int)
    fetch.add_argument("month", type=int)
    fetch.add_argument("--tournament", help="Only catalog games from this tournament URL")
    fetch.set_defaults(handler=_fetch_player_month)

    render = commands.add_parser("render-pgn", help="Render one PGN to an MP4 replay")
    render.add_argument("pgn", type=Path)
    render.add_argument("--output", type=Path)
    render.add_argument("--keep-frames", action="store_true")
    render.add_argument("--enrich-pubapi", action="store_true")
    render.add_argument("--commentary", action="store_true")
    render.add_argument(
        "--narrator",
        choices=("off", "auto", "windows-sapi", "espeak", "dmitri"),
    )
    render.add_argument("--voice-pack-dir", type=Path)
    render.set_defaults(handler=_render_pgn)

    ffmpeg = commands.add_parser("ffmpeg-version", help="Verify the configured FFmpeg")
    ffmpeg.set_defaults(handler=_ffmpeg_version)

    upload = commands.add_parser("upload-youtube", help="Upload a rendered replay to YouTube")
    upload.add_argument("video", type=Path)
    upload.add_argument("--title", required=True)
    upload.add_argument("--description", default="")
    upload.add_argument("--tag", action="append", default=[])
    upload.add_argument("--privacy", choices=("private", "unlisted", "public"), default="private")
    upload.add_argument("--client-secrets", type=Path, required=True)
    upload.add_argument("--token", type=Path, default=Path("youtube_token.json"))
    upload.set_defaults(handler=_upload_youtube)

    importer = commands.add_parser(
        "import-dmitlichess",
        help="Create an ignored private Dmitri clip pack from dmitlichess",
    )
    importer_source = importer.add_mutually_exclusive_group(required=True)
    importer_source.add_argument("--extension-dir", type=Path)
    importer_source.add_argument("--download", action="store_true")
    importer.add_argument("--target", type=Path, default=Path("voice-packs/dmitri"))
    importer.add_argument("--clips-per-category", type=int, default=8)
    importer.add_argument("--accept-private-use-only", action="store_true", required=True)
    importer.set_defaults(handler=_import_dmitlichess)
    return parser


def main(arguments: list[str] | None = None) -> int:
    parser = build_parser()
    parsed = parser.parse_args(arguments)
    try:
        return int(parsed.handler(parsed))
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


def _inspect_pgn(arguments: argparse.Namespace) -> int:
    game = parse_pgn_file(arguments.pgn)
    summary = {
        "white": game.headers.get("White"),
        "black": game.headers.get("Black"),
        "result": game.result,
        "plies": len(game.plies),
        "clock_annotations": sum(ply.clock_seconds is not None for ply in game.plies),
        "tournament": game.headers.get("Tournament"),
        "source": game.headers.get("Link"),
        "final_fen": game.final_fen,
    }
    _print_json(summary)
    return 0


def _fetch_player_month(arguments: argparse.Namespace) -> int:
    settings = Settings()
    with ChessComClient(settings.require_pubapi_contact()) as client:
        games = client.get_player_month(arguments.username, arguments.year, arguments.month)
    selected = tuple(
        game
        for game in games
        if arguments.tournament is None or game.tournament_url == arguments.tournament
    )
    catalog = GameCatalog(settings.database_path)
    catalog.initialize()
    for game in selected:
        catalog.upsert_game(game)
    _print_json(
        {
            "fetched": len(games),
            "cataloged": len(selected),
            "database": str(settings.database_path),
        }
    )
    return 0


def _render_pgn(arguments: argparse.Namespace) -> int:
    settings = Settings()
    output_path = arguments.output or settings.output_directory / f"{arguments.pgn.stem}.mp4"
    presentation = (
        _pubapi_presentation(arguments.pgn, output_path, settings)
        if arguments.enrich_pubapi
        else None
    )
    narrator_mode = arguments.narrator or (
        "auto" if arguments.commentary else settings.narrator_mode
    )
    narrator = create_narrator(
        narrator_mode,
        ffmpeg_executable=settings.ffmpeg_path,
        espeak_executable=settings.espeak_path,
        voice_pack_directory=arguments.voice_pack_dir or settings.voice_pack_directory,
    )
    pipeline = ReplayPipeline(
        PillowBoardRenderer(settings.frame_width, settings.frame_height),
        FFmpegEncoder(settings.ffmpeg_path),
        narrator=narrator,
        timeline_builder=TimelineBuilder(
            clock_tick_seconds=settings.clock_tick_seconds,
            fallback_move_seconds=settings.seconds_per_position,
            ending_hold_seconds=settings.ending_hold_seconds,
        ),
        frame_rate=settings.frame_rate,
        seconds_per_position=settings.seconds_per_position,
    )
    result = pipeline.render_pgn(
        arguments.pgn,
        output_path,
        keep_frames=arguments.keep_frames,
        presentation=presentation,
        include_commentary=narrator_mode != "off",
    )
    _print_json(
        {
            "video": str(result.video_path),
            "manifest": str(result.manifest_path),
            "frames": result.frame_count,
            "duration_seconds": result.duration_seconds,
        }
    )
    return 0


def _ffmpeg_version(_: argparse.Namespace) -> int:
    print(FFmpegEncoder(Settings().ffmpeg_path).version())
    return 0


def _upload_youtube(arguments: argparse.Namespace) -> int:
    publisher = YouTubePublisher(arguments.client_secrets, arguments.token)
    video_id = publisher.upload(
        arguments.video,
        YouTubeVideo(
            title=arguments.title,
            description=arguments.description,
            tags=tuple(arguments.tag),
            privacy_status=arguments.privacy,
        ),
    )
    _print_json({"video_id": video_id, "privacy": arguments.privacy})
    return 0


def _import_dmitlichess(arguments: argparse.Namespace) -> int:
    result = import_dmitlichess(
        arguments.target,
        extension_directory=arguments.extension_dir,
        download=arguments.download,
        private_use_accepted=arguments.accept_private_use_only,
        clips_per_category=arguments.clips_per_category,
    )
    _print_json(
        {
            "target": str(result.target_directory),
            "extension_version": result.extension_version,
            "clip_count": result.clip_count,
            "categories": result.categories,
        }
    )
    return 0


def _print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=True))


def _pubapi_presentation(
    pgn_path: Path,
    output_path: Path,
    settings: Settings,
) -> ReplayPresentation:
    game = parse_pgn_file(pgn_path)
    white_username = game.headers.get("White", "White")
    black_username = game.headers.get("Black", "Black")
    tournament_url = game.headers.get("Tournament")
    game_url = game.headers.get("Link")
    avatar_directory = output_path.parent / ".cache" / "avatars"

    with ChessComClient(settings.require_pubapi_contact()) as client:
        white_profile = client.get_player(white_username)
        black_profile = client.get_player(black_username)
        white_avatar = client.download_avatar(white_profile, avatar_directory)
        black_avatar = client.download_avatar(black_profile, avatar_directory)
        tournament = None
        if tournament_url and game_url:
            slug = tournament_url.rstrip("/").rsplit("/", maxsplit=1)[-1]
            tournament = TournamentContextLoader(client).load(slug, game_url)

    return ReplayPresentation(
        white=PlayerPresentation(
            username=white_profile.username,
            name=white_profile.name,
            title=white_profile.title,
            rating=game.headers.get("WhiteElo", ""),
            avatar_path=white_avatar,
            score_before=tournament.white.score_before if tournament else None,
            game_number=tournament.white.game_number if tournament else None,
            standing_label=tournament.white.standing_label if tournament else None,
        ),
        black=PlayerPresentation(
            username=black_profile.username,
            name=black_profile.name,
            title=black_profile.title,
            rating=game.headers.get("BlackElo", ""),
            avatar_path=black_avatar,
            score_before=tournament.black.score_before if tournament else None,
            game_number=tournament.black.game_number if tournament else None,
            standing_label=tournament.black.standing_label if tournament else None,
        ),
        tournament_name=tournament.tournament_name if tournament else None,
        round_number=tournament.round_number if tournament else None,
        total_rounds=tournament.total_rounds if tournament else None,
    )


if __name__ == "__main__":
    raise SystemExit(main())