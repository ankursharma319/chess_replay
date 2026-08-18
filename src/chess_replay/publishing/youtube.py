"""YouTube Data API OAuth and resumable upload support."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


@dataclass(frozen=True, slots=True)
class YouTubeVideo:
    title: str
    description: str
    tags: tuple[str, ...] = ()
    category_id: str = "20"
    privacy_status: str = "private"


class YouTubePublisher:
    scopes = ("https://www.googleapis.com/auth/youtube.upload",)

    def __init__(self, client_secrets_path: Path, token_path: Path) -> None:
        self.client_secrets_path = client_secrets_path
        self.token_path = token_path

    def upload(self, video_path: Path, metadata: YouTubeVideo) -> str:
        if not video_path.is_file():
            raise FileNotFoundError(video_path)
        if metadata.privacy_status not in {"private", "unlisted", "public"}:
            raise ValueError("privacy_status must be private, unlisted, or public")

        youtube = build("youtube", "v3", credentials=self._credentials())
        body = {
            "snippet": {
                "title": metadata.title,
                "description": metadata.description,
                "tags": list(metadata.tags),
                "categoryId": metadata.category_id,
            },
            "status": {"privacyStatus": metadata.privacy_status},
        }
        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=MediaFileUpload(str(video_path), chunksize=-1, resumable=True),
        )
        response: dict[str, Any] | None = None
        while response is None:
            _, response = request.next_chunk()
        return str(response["id"])

    def _credentials(self) -> Credentials:
        credentials: Credentials | None = None
        if self.token_path.is_file():
            credentials = Credentials.from_authorized_user_file(
                str(self.token_path),
                self.scopes,
            )
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        if not credentials or not credentials.valid:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(self.client_secrets_path),
                self.scopes,
            )
            credentials = flow.run_local_server(port=0)
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        self.token_path.write_text(credentials.to_json(), encoding="utf-8")
        return credentials