"""Serial client for Chess.com's read-only Published-Data API."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.parse import urlparse

import httpx


class ChessComApiError(RuntimeError):
    """Raised when PubAPI cannot satisfy a request."""


@dataclass(frozen=True, slots=True)
class Participant:
    username: str
    rating: int | None
    result: str


@dataclass(frozen=True, slots=True)
class PlayerProfile:
    username: str
    name: str | None
    title: str | None
    avatar_url: str | None
    fide_rating: int | None
    country_url: str | None

    @property
    def country_code(self) -> str | None:
        if self.country_url is None:
            return None
        code = urlparse(self.country_url).path.rstrip("/").rsplit("/", maxsplit=1)[-1]
        if len(code) != 2 or not code.isalpha():
            return None
        return code.upper()

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> PlayerProfile:
        fide = payload.get("fide")
        return cls(
            username=str(payload["username"]),
            name=_optional_string(payload.get("name")),
            title=_optional_string(payload.get("title")),
            avatar_url=_optional_string(payload.get("avatar")),
            fide_rating=int(fide) if fide is not None else None,
            country_url=_optional_string(payload.get("country")),
        )


@dataclass(frozen=True, slots=True)
class ArchivedGame:
    source_id: str
    url: str
    pgn: str
    end_time: datetime
    time_control: str
    time_class: str
    rules: str
    rated: bool
    final_fen: str
    tournament_url: str | None
    white: Participant
    black: Participant

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> ArchivedGame:
        url = str(payload["url"])
        return cls(
            source_id=url.rstrip("/").rsplit("/", maxsplit=1)[-1],
            url=url,
            pgn=str(payload["pgn"]),
            end_time=datetime.fromtimestamp(int(payload["end_time"]), tz=UTC),
            time_control=str(payload.get("time_control", "")),
            time_class=str(payload.get("time_class", "")),
            rules=str(payload.get("rules", "chess")),
            rated=bool(payload.get("rated", False)),
            final_fen=str(payload.get("fen", "")),
            tournament_url=_optional_string(payload.get("tournament")),
            white=_participant(payload["white"]),
            black=_participant(payload["black"]),
        )


@dataclass(slots=True)
class _CacheEntry:
    payload: Any
    etag: str | None
    last_modified: str | None


class ChessComClient:
    """Fetch PubAPI resources serially and reuse responses after HTTP 304."""

    base_url = "https://api.chess.com/pub"

    def __init__(
        self,
        user_agent: str,
        *,
        timeout_seconds: float = 30,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not user_agent.strip():
            raise ValueError("user_agent is required")
        self._client = httpx.Client(
            headers={"User-Agent": user_agent, "Accept": "application/json"},
            timeout=timeout_seconds,
            follow_redirects=True,
            transport=transport,
        )
        self._lock = Lock()
        self._cache: dict[str, _CacheEntry] = {}

    def __enter__(self) -> ChessComClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def get_tournament(self, slug: str) -> Mapping[str, Any]:
        return self._get_json(f"/tournament/{slug}")

    def get_tournament_round_groups(
        self,
        slug: str,
        round_number: int,
    ) -> tuple[Mapping[str, Any], ...]:
        round_payload = self._get_json(f"/tournament/{slug}/{round_number}")
        return tuple(self._get_json_url(str(url)) for url in round_payload.get("groups", []))

    def get_player(self, username: str) -> PlayerProfile:
        return PlayerProfile.from_payload(self._get_json(f"/player/{username}"))

    def download_avatar(self, profile: PlayerProfile, directory: Path) -> Path | None:
        if profile.avatar_url is None:
            return None
        parsed = urlparse(profile.avatar_url)
        suffix = Path(parsed.path).suffix.lower()
        if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
            suffix = ".img"
        destination = directory / f"{profile.username.lower()}{suffix}"
        if destination.is_file():
            return destination

        with self._lock:
            response = self._client.get(profile.avatar_url, headers={"Accept": "image/*"})
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            raise ChessComApiError(
                f"Avatar returned HTTP {response.status_code} for {profile.username}"
            ) from error
        if len(response.content) > 5 * 1024 * 1024:
            raise ChessComApiError(f"Avatar for {profile.username} exceeds 5 MiB")
        content_type = response.headers.get("Content-Type", "")
        if content_type and not content_type.startswith("image/"):
            raise ChessComApiError(f"Avatar for {profile.username} is not an image")
        directory.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(response.content)
        return destination

    def download_country_flag(self, profile: PlayerProfile, directory: Path) -> Path | None:
        code = profile.country_code
        if code is None:
            return None
        destination = directory / f"{code.lower()}.png"
        if destination.is_file():
            return destination

        try:
            with self._lock:
                response = self._client.get(
                    f"https://flagcdn.com/w80/{code.lower()}.png",
                    headers={"Accept": "image/png"},
                )
        except httpx.RequestError:
            return None
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError:
            return None
        if len(response.content) > 256 * 1024:
            return None
        content_type = response.headers.get("Content-Type", "")
        if content_type and not content_type.startswith("image/"):
            return None
        directory.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(response.content)
        return destination

    def get_player_month(self, username: str, year: int, month: int) -> tuple[ArchivedGame, ...]:
        if not 1 <= month <= 12:
            raise ValueError("month must be between 1 and 12")
        payload = self._get_json(f"/player/{username}/games/{year:04d}/{month:02d}")
        return tuple(ArchivedGame.from_payload(game) for game in payload.get("games", []))

    def _get_json(self, path: str) -> Any:
        return self._get_json_url(f"{self.base_url}{path}")

    def _get_json_url(self, url: str) -> Any:
        cached = self._cache.get(url)
        headers: dict[str, str] = {}
        if cached is not None:
            if cached.etag:
                headers["If-None-Match"] = cached.etag
            if cached.last_modified:
                headers["If-Modified-Since"] = cached.last_modified

        with self._lock:
            response = self._client.get(url, headers=headers)

        if response.status_code == httpx.codes.NOT_MODIFIED and cached is not None:
            return cached.payload
        if response.status_code == httpx.codes.TOO_MANY_REQUESTS:
            retry_after = response.headers.get("Retry-After", "unspecified")
            raise ChessComApiError(f"PubAPI rate limit reached; Retry-After={retry_after}")
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            raise ChessComApiError(
                f"PubAPI returned HTTP {response.status_code} for {url}"
            ) from error

        payload = response.json()
        self._cache[url] = _CacheEntry(
            payload=payload,
            etag=response.headers.get("ETag"),
            last_modified=response.headers.get("Last-Modified"),
        )
        return payload


def _participant(payload: Mapping[str, Any]) -> Participant:
    rating = payload.get("rating")
    return Participant(
        username=str(payload["username"]),
        rating=int(rating) if rating is not None else None,
        result=str(payload.get("result", "")),
    )


def _optional_string(value: Any) -> str | None:
    return str(value) if value else None