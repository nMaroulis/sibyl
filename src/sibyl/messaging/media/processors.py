"""Optional local OCR and speech tools, invoked without a shell or inherited credentials.

These processors produce uncertain text, not visual chart analysis or a native
multimodal LLM capability. Executables must already be installed on the backend's
PATH. Every child is owned, time/output bounded, killed and drained on cancellation.
"""

import asyncio
import os
import shutil
import struct
import tempfile
import time
import wave
from pathlib import Path

TEXT_BYTES = 64 * 1024


async def run(command, output: Path, *, timeout: float, max_bytes: int):
    """Execute a fixed argument list and watch its sole output; suppress private diagnostics."""
    # Retain platform/runtime essentials, not provider, exchange or messaging secrets.
    environment = {
        key: value
        for key, value in os.environ.items()
        if key
        in {
            "PATH",
            "SYSTEMROOT",
            "SystemRoot",
            "WINDIR",
            "TEMP",
            "TMP",
            "TMPDIR",
            "LANG",
            "LC_ALL",
            "TESSDATA_PREFIX",
        }
    }
    environment["OMP_THREAD_LIMIT"] = "2"
    process = None
    try:
        process = await asyncio.create_subprocess_exec(
            *map(str, command),
            cwd=output.parent,
            env=environment,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        deadline = time.monotonic() + timeout
        while True:
            if output.exists() and output.stat().st_size > max_bytes:
                raise ValueError("Local media extraction exceeded its output limit.")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ValueError("Local media extraction exceeded its time limit.")
            try:
                await asyncio.wait_for(process.wait(), min(0.2, remaining))
                break
            except TimeoutError:
                pass
        if process.returncode or not output.is_file() or output.stat().st_size > max_bytes:
            raise ValueError(
                "Local media extraction failed. Check the installed processor and language/model."
            )
    except (OSError, NotImplementedError):
        raise ValueError("The local media processor could not start on this backend.") from None
    finally:
        if process is not None and process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            await process.wait()


def image_suffix(content: bytes):
    """Check JPEG/PNG dimensions before any native decoder allocates the image."""
    if content.startswith(b"\x89PNG\r\n\x1a\n") and len(content) >= 33 and content[12:16] == b"IHDR":
        width, height = struct.unpack(">II", content[16:24])
        suffix = ".png"
    elif content.startswith(b"\xff\xd8"):
        offset, width, height = 2, 0, 0
        while offset + 4 <= len(content):
            if content[offset] != 255:
                break
            while offset < len(content) and content[offset] == 255:
                offset += 1
            if offset >= len(content):
                break
            marker, offset = content[offset], offset + 1
            if marker in {0xD8, 0xD9, 0xDA}:
                break
            if marker == 1 or 0xD0 <= marker <= 0xD7:
                continue
            if offset + 2 > len(content):
                break
            size = int.from_bytes(content[offset : offset + 2], "big")
            if size < 2 or offset + size > len(content):
                break
            if marker in {0xC0, 0xC1, 0xC2} and size >= 8:
                height, width = struct.unpack(">HH", content[offset + 3 : offset + 7])
                break
            offset += size
        suffix = ".jpg"
    else:
        raise ValueError("Photo extraction supports JPEG and PNG only.")
    if not 0 < width <= 4096 or not 0 < height <= 4096 or width * height > 12_000_000:
        raise ValueError("The downloaded photo must be at most 4096 pixels per side and 12 megapixels.")
    return suffix


def audio_format(content: bytes):
    """Allow only self-contained audio containers; playlists and remote references are rejected."""
    if content.startswith(b"OggS"):
        return "ogg"
    if content.startswith(b"fLaC"):
        return "flac"
    if content.startswith(b"RIFF") and content[8:12] == b"WAVE":
        return "wav"
    if content.startswith(b"ID3") or (len(content) > 2 and content[0] == 255 and content[1] & 0xE0 == 0xE0):
        return "mp3"
    raise ValueError("The downloaded audio must be Ogg, MP3, WAV or FLAC.")


def text_output(path):
    """Reject empty/oversized transcripts instead of silently clipping them."""
    data = path.read_bytes()
    if not data or len(data) > TEXT_BYTES:
        raise ValueError("No bounded readable text was extracted from this attachment.")
    try:
        text = data.decode("utf-8").strip()
    except UnicodeError:
        raise ValueError("The local processor returned invalid UTF-8 text.") from None
    if not text:
        raise ValueError("No readable text was found in this attachment.")
    return text


class LocalProcessors:
    """Resolve installed tools and convert an attachment entirely on the backend machine."""

    def status(self, model=""):
        return {
            "tesseract": bool(shutil.which("tesseract")),
            "ffmpeg": bool(shutil.which("ffmpeg")),
            "whisper": bool(shutil.which("whisper-cli")),
            "model": bool(model and Path(model).is_file()),
        }

    async def photo(self, content, language):
        suffix = image_suffix(content)
        executable = shutil.which("tesseract")
        if not executable:
            raise ValueError("Install Tesseract on the backend to extract text from photos.")
        with tempfile.TemporaryDirectory(prefix="sibyl-ocr-") as directory:
            root = Path(directory)
            source, output = root / ("photo" + suffix), root / "text.txt"
            source.write_bytes(content)
            source.chmod(0o600)
            await run(
                [executable, source, root / "text", "-l", language, "--psm", "3"],
                output,
                timeout=30,
                max_bytes=TEXT_BYTES,
            )
            return text_output(output)

    async def audio(self, content, language, model):
        fmt = audio_format(content)
        ffmpeg, whisper = shutil.which("ffmpeg"), shutil.which("whisper-cli")
        if not ffmpeg or not whisper or not model or not Path(model).is_file():
            raise ValueError(
                "Install FFmpeg and whisper-cli and select a local Whisper model in Telegram attachment settings."
            )
        with tempfile.TemporaryDirectory(prefix="sibyl-speech-") as directory:
            root = Path(directory)
            source, pcm, output = root / "audio", root / "audio.wav", root / "text.txt"
            source.write_bytes(content)
            source.chmod(0o600)
            # Decode one extra second to detect excess duration, then reject it.
            # Explicit demuxer + file-only protocol prevent input URLs/playlists.
            await run(
                [
                    ffmpeg,
                    "-nostdin",
                    "-v",
                    "error",
                    "-threads",
                    "2",
                    "-protocol_whitelist",
                    "file",
                    "-f",
                    fmt,
                    "-i",
                    source,
                    "-map",
                    "0:a:0",
                    "-vn",
                    "-sn",
                    "-dn",
                    "-t",
                    "121",
                    "-ac",
                    "1",
                    "-ar",
                    "16000",
                    "-c:a",
                    "pcm_s16le",
                    "-f",
                    "wav",
                    pcm,
                ],
                pcm,
                timeout=25,
                max_bytes=4_000_000,
            )
            try:
                with wave.open(str(pcm), "rb") as audio:
                    duration = audio.getnframes() / audio.getframerate()
                    valid = (
                        audio.getnchannels() == 1
                        and audio.getsampwidth() == 2
                        and audio.getframerate() == 16000
                    )
                if not valid or not 0 < duration <= 120:
                    raise ValueError("The decoded audio must be at most two minutes long.")
            except (wave.Error, EOFError):
                raise ValueError("FFmpeg did not produce a readable PCM audio clip.") from None
            await run(
                [
                    whisper,
                    "-m",
                    model,
                    "-f",
                    pcm,
                    "-of",
                    root / "text",
                    "-otxt",
                    "-nt",
                    "-l",
                    language,
                    "-t",
                    "2",
                    "-p",
                    "1",
                    "-ng",
                ],
                output,
                timeout=90,
                max_bytes=TEXT_BYTES,
            )
            return text_output(output)
