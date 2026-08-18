"""Reconstruct per-game Swiss tournament context from PubAPI round results."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

_DRAW_RESULTS = {
    "agreed",
    "repetition",
    "stalemate",
    "insufficient",
    "50move",
    "timevsinsufficient",
}


class TournamentDataSource(Protocol):
    def get_tournament(self, slug: str) -> Mapping[str, Any]: ...

    def get_tournament_round_groups(
        self,
        slug: str,
        round_number: int,
    ) -> tuple[Mapping[str, Any], ...]: ...


@dataclass(frozen=True, slots=True)
class PlayerTournamentState:
    username: str
    score_before: float
    game_number: int
    score_rank: int
    tied_at_score: int

    @property
    def standing_label(self) -> str:
        prefix = "T-" if self.tied_at_score > 1 else "#"
        return f"{prefix}{self.score_rank}"


@dataclass(frozen=True, slots=True)
class TournamentGameContext:
    tournament_name: str
    round_number: int
    total_rounds: int
    white: PlayerTournamentState
    black: PlayerTournamentState


class TournamentContextLoader:
    """Find a game and calculate each player's state before that round."""

    def __init__(self, source: TournamentDataSource) -> None:
        self.source = source

    def load(self, slug: str, game_url: str) -> TournamentGameContext:
        tournament = self.source.get_tournament(slug)
        settings = tournament.get("settings", {})
        total_rounds = int(settings.get("total_rounds", len(tournament.get("rounds", []))))
        scores: dict[str, float] = {}
        game_counts: dict[str, int] = {}
        display_names: dict[str, str] = {}

        for round_number in range(1, total_rounds + 1):
            groups = self.source.get_tournament_round_groups(slug, round_number)
            self._register_players(groups, scores, display_names)
            target = _find_game(groups, game_url)
            if target is not None:
                white_username = str(target["white"]["username"])
                black_username = str(target["black"]["username"])
                return TournamentGameContext(
                    tournament_name=str(tournament.get("name", slug)),
                    round_number=round_number,
                    total_rounds=total_rounds,
                    white=_state(white_username, scores, game_counts),
                    black=_state(black_username, scores, game_counts),
                )
            self._apply_round(groups, scores, game_counts, display_names)

        raise ValueError(f"Game {game_url} was not found in tournament {slug}")

    @staticmethod
    def _register_players(
        groups: Sequence[Mapping[str, Any]],
        scores: dict[str, float],
        display_names: dict[str, str],
    ) -> None:
        for group in groups:
            for player in group.get("players", []):
                username = str(player["username"])
                key = username.casefold()
                scores.setdefault(key, 0.0)
                display_names.setdefault(key, username)

    @staticmethod
    def _apply_round(
        groups: Sequence[Mapping[str, Any]],
        scores: dict[str, float],
        game_counts: dict[str, int],
        display_names: dict[str, str],
    ) -> None:
        for group in groups:
            for game in group.get("games", []):
                for color in ("white", "black"):
                    participant = game[color]
                    username = str(participant["username"])
                    key = username.casefold()
                    scores.setdefault(key, 0.0)
                    scores[key] += _result_points(str(participant.get("result", "")))
                    game_counts[key] = game_counts.get(key, 0) + 1
                    display_names.setdefault(key, username)


def _find_game(
    groups: Sequence[Mapping[str, Any]],
    game_url: str,
) -> Mapping[str, Any] | None:
    for group in groups:
        for game in group.get("games", []):
            if str(game.get("url", "")) == game_url:
                return game
    return None


def _result_points(result: str) -> float:
    if result == "win":
        return 1.0
    if result in _DRAW_RESULTS:
        return 0.5
    return 0.0


def _state(
    username: str,
    scores: Mapping[str, float],
    game_counts: Mapping[str, int],
) -> PlayerTournamentState:
    key = username.casefold()
    score = scores.get(key, 0.0)
    score_rank = 1 + sum(value > score for value in scores.values())
    tied_at_score = sum(value == score for value in scores.values())
    return PlayerTournamentState(
        username=username,
        score_before=score,
        game_number=game_counts.get(key, 0) + 1,
        score_rank=score_rank,
        tied_at_score=tied_at_score,
    )