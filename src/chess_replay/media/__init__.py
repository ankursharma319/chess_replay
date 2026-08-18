"""Media encoding and validation."""

from chess_replay.media.commentary import CommentaryCue, CommentaryGenerator
from chess_replay.media.ffmpeg import FFmpegEncoder, FFmpegError
from chess_replay.media.narration import (
	EspeakNarrator,
	LocalClipPackNarrator,
	NarrationUnavailable,
	Narrator,
	NullNarrator,
	WindowsSapiNarrator,
	create_narrator,
)
from chess_replay.media.sound import NarrationClip, SoundKind, SoundtrackBuilder

__all__ = [
	"CommentaryCue",
	"CommentaryGenerator",
	"FFmpegEncoder",
	"FFmpegError",
	"EspeakNarrator",
	"LocalClipPackNarrator",
	"NarrationClip",
	"NarrationUnavailable",
	"Narrator",
	"NullNarrator",
	"SoundKind",
	"SoundtrackBuilder",
	"WindowsSapiNarrator",
	"create_narrator",
]