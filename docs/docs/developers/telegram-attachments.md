# Telegram attachments

Telegram can import private documents, extract text from photos and transcribe short voice/audio clips. Each type is **off by default**. Enable it in **Settings → Messaging → Telegram attachments** after setting up your private bot.

## What happens to a file

1. Sibyl verifies the configured human, private chat, connection generation and message date before inspecting attachment metadata. Groups, other senders, forwarded messages and stale messages are ignored without downloading files.
2. A supported attachment is queued with the current consent revision. Changing preferences before processing refuses that old attachment; send it again after reviewing the new settings.
3. The backend downloads at most 8 MiB directly from Telegram. Paths, redirects, declared size and actual streamed bytes are checked. No user-supplied URL or local Bot API path is fetched.
4. The existing research library retains the document or extracted text with source fingerprints and addressable passages. The ordinary native ProtoLink coordinator receives the document ID, then can consult Wiki or Reporter to read and cite it. The complete source is not inserted into the initial prompt.
5. The reply includes the document ID. Open **Research → My research** to inspect it. A reply receipt also records the retained document identity. Repeated identical imports reuse the library's content fingerprint.

You can import a supported file without an AI model. Sibyl confirms retention and explains how to enable reasoning. Saving attachment preferences never starts inference, installs software or downloads models.

## Supported inputs and local requirements

| Input | Implementation | Limits and meaning |
| --- | --- | --- |
| PDF, UTF-8 text, Markdown | Existing text/PDF extraction and library import | 8 MiB; text-bearing PDF up to 100 pages; library extraction/retention limits still apply. Scanned PDFs need prior OCR. |
| Telegram photo | Installed `tesseract` CLI | JPEG/PNG up to 4096 pixels per side and 12 megapixels; at most 64 KiB of extracted text. **OCR reads text, not chart shapes or investment signals.** |
| Voice or audio | Installed `ffmpeg`, `whisper-cli` and an owner-selected whisper.cpp `.bin` model | Ogg, MP3, WAV or FLAC; 8 MiB and two minutes. Decoded PCM duration is checked independently of Telegram metadata. M4A, video and playlists are unsupported. |

Processor programs must be on the **Python backend's PATH**. Select an existing absolute model path on that same machine; the browser's filesystem is unrelated. The saved path is encrypted and is not returned to agents or in settings responses. The UI shows the model basename and local dependency presence. Presence does not verify language availability or recognition accuracy.

Install processors using the official [Tesseract instructions](https://tesseract-ocr.github.io/tessdoc/Installation.html), [FFmpeg downloads](https://ffmpeg.org/download.html) and [whisper.cpp quick start/model instructions](https://github.com/ggml-org/whisper.cpp#quick-start). Tesseract language packs use names such as `eng` or `eng+ell`; Whisper accepts `auto` or a language code such as `en`. Install the language packs/model separately. Sibyl uses fixed argument lists, two CPU threads and no shell; it does not run commands supplied in a chat or attachment.

## Privacy and uncertainty

Document originals remain in the local research library under its existing limits and deletion controls. For photos/audio, only the labeled OCR/transcript with the original SHA-256 fingerprint is retained; original media and temporary decoded files are removed after processing. Extracted text is untrusted evidence and can contain recognition errors. It may be read by the selected AI provider when a specialist retrieves it. Review names, amounts and dates against the original.

Photo processing has a 30-second child deadline. Audio decoding has 25 seconds, transcription 90 seconds, with output bounds. Cancellation kills and drains owned native children. A local import already committing can remain after Pause or cancellation; neither operation reverses retention. An interrupted request is not automatically inferred again. Restoring a workspace disables attachment consent and changes its revision.

This is application-owned preprocessing, not an assertion that every ProtoLink LLM supports image/audio input. The coordinator and specialist tools continue to use native ProtoLink text requests, discovery, evidence and conversation storage.

## HTTP and modules

- `GET /api/v1/settings/messaging/telegram/attachments`: consent, bounds and dependency presence; no model path or token.
- `PUT /api/v1/settings/messaging/telegram/attachments`: typed explicit opt-in, language choices, optional write-only local model path or path removal.
- `messaging/media/contracts.py`: attachment/settings schemas and metadata limits.
- `messaging/media/processors.py`: owned local children and independent image/audio checks.
- `messaging/media/service.py`: consent checks, extraction, library provenance and bounded native question construction.
- `messaging/telegram.py`: direct Bot API download transport. See Telegram's [getFile contract](https://core.telegram.org/bots/api#getfile).

Tests cover unauthorized/disabled input, changed consent, malformed paths and redirects, actual byte bounds, token privacy, retained source identity, native request construction, processor arguments, misleading duration, cancellation/draining and restored consent. Optional processor accuracy and live Telegram attachment acceptance require the owner's installed tools and private bot; offline tests do not claim those were exercised.
