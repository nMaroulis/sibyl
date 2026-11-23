"""Reduce native request metadata before signing, without exposing signed URLs."""

import hashlib
from functools import wraps

from sibyl.market_data.quotas.policies import request


def bind(native, control, source):
    """Wrap the installed SDK's fetch2 primitive; explicit reads keep native nonce/signing."""
    original = getattr(native, "fetch2", None)
    if not callable(original):
        return
    key = getattr(native, "apiKey", None)
    partition = hashlib.sha256(key.encode()).hexdigest() if isinstance(key, str) and key else "unverified"

    @wraps(original)
    def fetch2(path, api="public", method="GET", params=None, headers=None, body=None, config=None):
        call = request(source, api, method, path, params, partition)
        previous = getattr(control._local, "quota", None)
        control._local.quota = call
        try:
            # Wait before the SDK creates its signed URL or nonce. A race at the
            # actual transport gate defers without sending, never replays a URL.
            control.wait_quota(source, call)
            return original(
                path,
                api,
                method,
                {} if params is None else params,
                headers,
                body,
                {} if config is None else config,
            )
        finally:
            control._local.quota = previous

    native.fetch2 = fetch2
