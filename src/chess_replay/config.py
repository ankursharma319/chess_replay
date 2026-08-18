"""Runtime configuration loaded from environment variables and optional .env files."""

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    chess_com_user_agent: str = "chess-replay/0.1 (contact: configure-me)"
    output_directory: Path = Path("output")
    database_path: Path = Path("output/chess_replay.db")
    ffmpeg_path: str = "ffmpeg"
    frame_width: int = Field(default=1920, ge=640, le=7680)
    frame_height: int = Field(default=1080, ge=360, le=4320)
    frame_rate: int = Field(default=30, ge=1, le=120)
    seconds_per_position: float = Field(default=1.2, gt=0, le=30)
    clock_tick_seconds: float = Field(default=1.0, gt=0, le=10)
    ending_hold_seconds: float = Field(default=3.6, gt=0, le=60)
    narrator_mode: str = "off"
    espeak_path: str = "espeak-ng"
    voice_pack_directory: Path | None = None
    stockfish_path: str = "stockfish"
    evaluation_time_ms: int = Field(default=200, ge=10, le=5_000)
    evaluation_depth: int = Field(default=18, ge=1, le=50)
    stockfish_hash_mb: int = Field(default=256, ge=16, le=2_048)
    stockfish_threads: int = Field(default=2, ge=1, le=32)

    @field_validator("chess_com_user_agent")
    @classmethod
    def user_agent_must_identify_client(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("CHESS_COM_USER_AGENT cannot be empty")
        return value.strip()

    def require_pubapi_contact(self) -> str:
        """Return the configured User-Agent or reject the placeholder value."""
        if "configure-me" in self.chess_com_user_agent:
            raise ValueError(
                "Set CHESS_COM_USER_AGENT to identify the client and provide contact information"
            )
        return self.chess_com_user_agent