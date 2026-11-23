"""Exact public callback: provider HMAC/token auth, bounded bodies, no workspace controls."""

import json
import logging
import re
import secrets

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import PlainTextResponse

from sibyl.api.routes import S
from sibyl.api.uploads import bounded_body
from sibyl.messaging.channels.contracts import ChannelError
from sibyl.messaging.channels.whatsapp import WhatsAppClient


class _VerifyTokenFilter(logging.Filter):
    """Webhook handshake URLs carry a private token; omit their entire query in logs."""

    def filter(self, record):
        record.msg = re.sub(r"(/api/v1/webhooks/whatsapp)\?[^\s]+", r"\1?[redacted]", record.getMessage())
        record.args = ()
        return True


logger = logging.getLogger("uvicorn.access")
if not any(isinstance(item, _VerifyTokenFilter) for item in logger.filters):
    logger.addFilter(_VerifyTokenFilter())
router = APIRouter(prefix="/api/v1/webhooks/whatsapp", tags=["WhatsApp webhook"])


@router.get("")
def challenge(request: Request, s: S):
    """Verify Meta's subscription token; disclose no connection or workspace metadata."""
    profile = s.private_channels.profile("whatsapp")
    token = request.query_params.get("hub.verify_token", "")
    value = request.query_params.get("hub.challenge", "")
    if (
        not profile.get("verify_token")
        or request.query_params.get("hub.mode") != "subscribe"
        or not secrets.compare_digest(token.encode(), profile["verify_token"].encode())
        or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", value)
    ):
        raise HTTPException(403, "Webhook verification failed.")
    return PlainTextResponse(value, headers={"Cache-Control": "no-store"})


@router.post("")
async def event(request: Request, s: S):
    """Authenticate raw bytes, ingest authorized messages, then acknowledge the callback."""
    raw = await bounded_body(request, 128 * 1024)
    profile = s.private_channels.profile("whatsapp")
    if not profile.get("app_secret"):
        raise HTTPException(403, "Webhook authentication failed.")
    client = WhatsAppClient(profile, s.private_channels.http)
    if not client.verify(raw, request.headers.get("x-hub-signature-256", "")):
        raise HTTPException(403, "Webhook authentication failed.")
    try:
        body = json.loads(raw)
    except (ValueError, UnicodeError):
        raise HTTPException(400, "Invalid webhook body.") from None
    try:
        batch = client.messages(body)
        if profile.get("enabled"):
            if not s.private_channels.ingest("whatsapp", profile, batch):
                raise HTTPException(503, "Connection changed before the event was retained.")
    except ChannelError:
        raise HTTPException(503, "Webhook intake is temporarily unavailable.") from None
    return Response(status_code=200, headers={"Cache-Control": "no-store"})
