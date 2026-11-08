"""Signal through an independently linked loopback signal-cli HTTP daemon.

This is an unofficial bridge, not Signal account registration or a hosted API.
Native replay is limited to the daemon's retained SSE events; gaps are possible
across bridge restarts. Local message identities still suppress duplicate runs.
"""

import json
from uuid import uuid4

import aiohttp

from sibyl.messaging.channels.contracts import Batch, ChannelError, Envelope
from sibyl.messaging.channels.http import call


class SignalClient:
    chunk_units = 3500

    def __init__(self, profile, http):
        self.profile, self.http = profile, http
        self.session, self.response = None, None
        self._event = []

    async def rpc(self, method, params, *, write=False):
        identity = uuid4().hex
        result = await call(
            self.http,
            "POST",
            self.profile["bridge_url"] + "/api/v1/rpc",
            payload={
                "jsonrpc": "2.0",
                "id": identity,
                "method": method,
                "params": params
                if method == "listAccounts"
                else {"account": self.profile["account"], **params},
            },
            write=write,
        )
        if (
            not isinstance(result, dict)
            or result.get("id") != identity
            or "error" in result
            or "result" not in result
        ):
            raise ChannelError("signal-cli did not confirm the command.", ambiguous=write)
        return result["result"]

    async def identity(self):
        # listAccounts must use a multi-account HTTP daemon, as described in setup.
        result = await self.rpc("listAccounts", {})
        if not isinstance(result, list) or not any(
            self.profile["account"] in {row.get("number"), row.get("aci")}
            for row in result
            if isinstance(row, dict)
        ):
            raise ChannelError(
                "Run signal-cli as a multi-account HTTP daemon and link the selected account first."
            )
        return dict(
            bot_id=self.profile["account"],
            bot_username="Linked Signal account",
            target=self.profile["allowed_sender_aci"],
        )

    async def receive(self, cursor):
        if not self.response or self.response.closed:
            await self.close()
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=None, sock_connect=5), trust_env=False
            )
            headers = {"Last-Event-ID": cursor} if cursor else {}
            self.response = await self.session.get(
                self.profile["bridge_url"] + "/api/v1/events", headers=headers, allow_redirects=False
            )
            if self.response.status != 200:
                await self.close()
                raise ChannelError("The local signal-cli event stream is unavailable.")
        for _ in range(100):
            try:
                import asyncio

                line = await asyncio.wait_for(self.response.content.readline(), 1)
            except TimeoutError:
                return Batch(cursor=cursor)
            if not line:
                await self.close()
                raise ChannelError("signal-cli disconnected. Its retained event history may have gaps.")
            if sum(len(part) for part in self._event) + len(line) > 65536:
                await self.close()
                raise ChannelError("signal-cli returned an oversized event.")
            if line.strip():
                self._event.append(line)
                continue
            lines, self._event = self._event, []
            identity = None
            data = []
            for part in lines:
                if part.startswith(b"id:"):
                    identity = part[3:].strip().decode("ascii", errors="ignore")
                elif part.startswith(b"data:"):
                    data.append(part[5:].strip())
            if not data:
                continue
            try:
                payload = json.loads(b"\n".join(data))
            except (ValueError, UnicodeError):
                raise ChannelError("signal-cli returned an unreadable event.") from None
            params = payload.get("params") or {}
            params = params.get("result", params)
            envelope = params.get("envelope") or {}
            message = envelope.get("dataMessage") or {}
            sender = str(envelope.get("sourceUuid", "")).removeprefix("aci:")
            account = params.get("account")
            accepted = (
                payload.get("method") == "receive"
                and account == self.profile["account"]
                and not message.get("groupInfo")
                and not message.get("viewOnce")
                and not envelope.get("syncMessage")
            )
            messages = []
            if accepted and type(envelope.get("timestamp")) is int:
                native = (
                    str(envelope["timestamp"]) + ":" + sender + ":" + str(envelope.get("sourceDevice", ""))
                )
                messages = [
                    Envelope(native, sender, sender, message.get("message", ""), envelope["timestamp"] / 1000)
                ]
            return Batch(messages, identity if identity and len(identity) <= 200 else cursor)
        return Batch(cursor=cursor)

    async def acknowledge(self, batch):
        """The saved Last-Event-ID is the native replay cursor; no extra RPC is sent."""

    async def send(self, target, text):
        if target != self.profile["allowed_sender_aci"]:
            raise ChannelError("The saved private recipient changed.")
        result = await self.rpc("send", {"recipient": [target], "message": text}, write=True)
        if not isinstance(result, dict) or type(result.get("timestamp")) is not int:
            raise ChannelError("signal-cli did not confirm message acceptance.", ambiguous=True)
        return str(result["timestamp"])

    async def close(self):
        if self.response:
            self.response.close()
        if self.session:
            await self.session.close()
        self.response, self.session = None, None
        self._event = []
