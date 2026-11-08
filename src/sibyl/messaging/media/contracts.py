"""Bounded attachment descriptors; only the authorized private sender reaches these parsers."""

import re
from pathlib import PurePosixPath
from typing import Literal

from pydantic import Field, field_validator

from sibyl.models import Request

MAX_BYTES = 8 * 1024 * 1024
MAX_SECONDS = 120


class MediaSettings(Request):
    """Explicit local retention consent; no model or processor is downloaded by saving."""

    documents: bool = Field(default=False, strict=True)
    photos: bool = Field(default=False, strict=True)
    audio: bool = Field(default=False, strict=True)
    ocr_language: str = Field(default="eng", pattern=r"^[a-z]{3}(?:\+[a-z]{3}){0,3}$")
    audio_language: str = Field(default="auto", pattern=r"^(?:auto|[a-z]{2,3})$")
    whisper_model: str | None = Field(default=None, max_length=1024)
    clear_model: bool = Field(default=False, strict=True)


class Attachment(Request):
    """Keep native identities and a basename, never a URL or a local filesystem path."""

    kind: Literal["documents", "photos", "audio"]
    file_id: str = Field(min_length=1, max_length=512, pattern=r"^[A-Za-z0-9_-]+$")
    filename: str = Field(min_length=1, max_length=160)
    file_size: int | None = Field(default=None, gt=0, le=MAX_BYTES, strict=True)
    revision: str = Field(pattern=r"^[a-f0-9]{32}$")

    @field_validator("filename")
    @classmethod
    def basename(cls, value):
        if value != PurePosixPath(value).name or "\\" in value or re.search(r"[\x00-\x1f]", value):
            raise ValueError("Use an attachment basename without paths or control characters.")
        return value


def describe(message: dict, revision: str) -> Attachment | None:
    """Describe one supported file without fetching it; reject excess metadata explicitly.

    PDF/text/Markdown documents, photo JPEG/PNG and voice/audio Ogg/MP3/WAV/FLAC
    are supported. Media groups are independent attachments, not a merged album.
    Video, animation, stickers, executables and document-embedded image/audio are
    outside this contract. Declared type/size is not trusted as downloaded content.
    """
    kind, native, filename = "", None, ""
    if message.get("document"):
        kind, native = "documents", message["document"]
        filename = native.get("file_name", "") if isinstance(native, dict) else ""
        if PurePosixPath(filename).suffix.lower() not in {".txt", ".md", ".markdown", ".pdf"}:
            raise ValueError("Send a PDF, UTF-8 text or Markdown document, up to 8 MiB.")
    elif message.get("photo"):
        sizes = message["photo"]
        if not isinstance(sizes, list) or len(sizes) > 10:
            raise ValueError("This photo has invalid size metadata.")
        choices = [
            row
            for row in sizes
            if isinstance(row, dict)
            and type(row.get("width")) is int
            and type(row.get("height")) is int
            and 0 < row["width"] <= 4096
            and 0 < row["height"] <= 4096
            and row["width"] * row["height"] <= 12_000_000
        ]
        if not choices:
            raise ValueError("Send a photo up to 4096 pixels per side and 12 megapixels.")
        kind, native, filename = (
            "photos",
            max(choices, key=lambda row: row["width"] * row["height"]),
            "photo.jpg",
        )
    elif message.get("voice") or message.get("audio"):
        kind, native = "audio", message.get("voice") or message["audio"]
        duration = native.get("duration") if isinstance(native, dict) else None
        if type(duration) not in {int, float} or not 0 < duration <= MAX_SECONDS:
            raise ValueError("Send a voice note or audio clip of at most two minutes.")
        filename = "voice.ogg" if message.get("voice") else native.get("file_name", "audio.mp3")
        if PurePosixPath(filename).suffix.lower() not in {".ogg", ".oga", ".mp3", ".wav", ".flac"}:
            raise ValueError("Supported audio formats are Ogg voice, MP3, WAV and FLAC.")
    if native is None:
        return None
    if not isinstance(native, dict):
        raise ValueError("The attachment metadata is invalid.")
    return Attachment(
        kind=kind,
        file_id=native.get("file_id"),
        filename=filename,
        file_size=native.get("file_size"),
        revision=revision,
    )
