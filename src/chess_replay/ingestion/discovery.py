"""Resolve players and discover tournament games from PubAPI archives."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from chess_replay.ingestion.chess_com import (
    ArchivedGame,
    ChessComApiError,
    ChessComClient,
    PlayerProfile,
)

_PLAYER_ALIASES = {
    "magnus carlsen": "magnuscarlsen",
    "hikaru nakamura": "hikaru",
    "arjun erigaisi": "ghandeevam2003",
    "nihal sarin": "nihalsarin",
    "hans niemann": "hansontwitch",
    "hans moke niemann": "hansontwitch",
    "gukesh d": "gukeshdommaraju",
    "gukesh dommaraju": "gukeshdommaraju",
    "pragg": "rpragchess",
    "r praggnanandhaa": "rpragchess",
    "praggnanandhaa rameshbabu": "rpragchess",
    "vidit": "viditchess",
    "vidit gujrathi": "viditchess",
    "artin ashraf": "artin10862",
    "alireza firouzja": "firouzja2003",
    "fabiano caruana": "fabiano_caruana",
}


@dataclass(frozen=True, slots=True)
class DiscoveredTournament:
    url: str
    slug: str
    games: tuple[ArchivedGame, ...]


def resolve_player(client: ChessComClient, identifier: str) -> PlayerProfile:
    """Resolve a username, @username, or supported public display name."""
    cleaned = identifier.strip().removeprefix("@")
    if not cleaned:
        raise ValueError("Player cannot be empty")
    normalized = " ".join(cleaned.casefold().split())
    candidates = [cleaned]
    alias = _PLAYER_ALIASES.get(normalized)
    if alias:
        candidates.insert(0, alias)
    compact = re.sub(r"[^a-z0-9_-]", "", normalized)
    if compact and compact not in candidates:
        candidates.append(compact)

    errors: list[str] = []
    for candidate in dict.fromkeys(candidates):
        try:
            profile = client.get_player(candidate)
        except ChessComApiError as error:
            errors.append(str(error))
            continue
        if " " not in cleaned or _profile_matches(profile, normalized) or candidate == alias:
            return profile
    detail = f" ({'; '.join(errors)})" if errors else ""
    raise ValueError(
        f"Unable to resolve {identifier!r} to a Chess.com username; use @username{detail}"
    )


def discover_tournament(
    games: tuple[ArchivedGame, ...],
    event_date: date,
    tournament_name: str,
) -> DiscoveredTournament:
    """Select a unique tournament and all matching player games for a UTC date."""
    query = _normalize(tournament_name)
    candidates: dict[str, list[ArchivedGame]] = {}
    for game in games:
        if game.tournament_url is None or _game_date(game) != event_date:
            continue
        if query and query not in _normalize(game.tournament_url):
            continue
        candidates.setdefault(game.tournament_url, []).append(game)

    if not candidates:
        raise ValueError(
            f"No {tournament_name!r} games found on {event_date.isoformat()} in the player archive"
        )
    if len(candidates) > 1:
        choices = ", ".join(sorted(candidates))
        raise ValueError(f"Tournament is ambiguous; matching URLs: {choices}")

    url, selected = next(iter(candidates.items()))
    return DiscoveredTournament(
        url=url,
        slug=url.rstrip("/").rsplit("/", maxsplit=1)[-1],
        games=tuple(sorted(selected, key=lambda game: game.end_time)),
    )


def discover_daily_games(
    games: tuple[ArchivedGame, ...],
    event_date: date,
    *,
    non_tournament_only: bool = True,
) -> tuple[ArchivedGame, ...]:
    """Select a player's games for one UTC date in chronological order."""
    selected = tuple(
        sorted(
            (
                game
                for game in games
                if _game_date(game) == event_date
                and (not non_tournament_only or game.tournament_url is None)
            ),
            key=lambda game: game.end_time,
        )
    )
    if not selected:
        qualifier = " non-tournament" if non_tournament_only else ""
        raise ValueError(f"No{qualifier} games found on {event_date.isoformat()}")
    return selected


def _profile_matches(profile: PlayerProfile, normalized_identifier: str) -> bool:
    return (
        profile.name is not None
        and " ".join(profile.name.casefold().split()) == normalized_identifier
    )


def _game_date(game: ArchivedGame) -> date:
    match = re.search(r'^\[UTCDate "(\d{4}\.\d{2}\.\d{2})"\]$', game.pgn, re.MULTILINE)
    if match:
        return date.fromisoformat(match.group(1).replace(".", "-"))
    return game.end_time.date()


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())