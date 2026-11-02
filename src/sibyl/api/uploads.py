"""Bound request bodies before document parsing or archive decryption."""

import asyncio

from fastapi import HTTPException


async def bounded_body(request, limit):
    """Reject an oversized stream even when Content-Length is absent or dishonest."""
    data = bytearray()
    try:
        async with asyncio.timeout(120):
            async for chunk in request.stream():
                if len(data) + len(chunk) > limit:
                    raise HTTPException(413, "Upload exceeds the size limit.")
                data.extend(chunk)
    except TimeoutError:
        raise HTTPException(408, "Upload timed out.") from None
    return bytes(data)
