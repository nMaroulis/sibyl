"""Bounded, read-only Bitcoin mainnet research through mempool.space's Esplora API.

Lookups are explicit and ephemeral. No exchange credentials, arbitrary provider
URLs, transaction broadcasts, retries, background polling or server-side address
history are involved. Demo uses the same normalizers through a separate transport.
"""

import json
import threading
from contextlib import contextmanager
from datetime import UTC, datetime

import httpx

from sibyl.blockchain import demo, normalize
from sibyl.blockchain.identifiers import address, txid

BASE_URL = "https://mempool.space/api"
MAX_RESPONSE = 8 * 1024 * 1024


class BitcoinUnavailable(Exception):
    """A sanitized provider/admission error, without URLs, identifiers or raw response bodies."""

    def __init__(self, message, status=502):
        super().__init__(message)
        self.status = status


def now():
    return datetime.now(UTC).isoformat()


class BitcoinExplorer:
    """Own two concurrent explicit research reads; each releases its HTTP session on completion."""

    def __init__(self, client_factory=None):
        self._client_factory = client_factory or (
            lambda: httpx.Client(timeout=httpx.Timeout(10, connect=5), follow_redirects=False)
        )
        self._capacity = threading.BoundedSemaphore(2)

    def capabilities(self):
        """Describe real scope and explicit examples without a provider request."""
        return {
            "network": "Bitcoin mainnet",
            "source": "mempool.space",
            "source_url": "https://mempool.space/",
            "address_formats": ["P2PKH", "P2SH", "Bech32", "Bech32m"],
            "history_page_size": 25,
            "pending_limit": 50,
            "io_page_size": normalize.PAGE_SIZE,
            "demo": {"txid": demo.TXID, "address": demo.ADDRESS},
            "note": "Public lookups send the entered transaction ID or address to mempool.space. Address activity does not identify its owner or represent a complete wallet.",
        }

    def _read(self, client, path, simulated):
        if simulated:
            return demo.read(path)
        try:
            with client.stream("GET", BASE_URL + path, headers={"Accept": "application/json"}) as response:
                if response.status_code == 404:
                    raise LookupError("The Bitcoin indexer did not find this reference.")
                if response.status_code == 429:
                    raise BitcoinUnavailable(
                        "mempool.space is rate limiting lookups. Wait before refreshing.", 429
                    )
                if not 200 <= response.status_code < 300:
                    raise BitcoinUnavailable("mempool.space could not complete this lookup. Try again later.")
                chunks, size = [], 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > MAX_RESPONSE:
                        raise BitcoinUnavailable(
                            "This Bitcoin response exceeds the supported research size. Open the public explorer for this reference."
                        )
                    chunks.append(chunk)
                body = b"".join(chunks)
                return body.decode("ascii").strip() if path == "/blocks/tip/height" else json.loads(body)
        except (httpx.HTTPError, UnicodeError, json.JSONDecodeError):
            raise BitcoinUnavailable(
                "mempool.space is unavailable or returned an unreadable response. No Demo data was substituted."
            ) from None

    @contextmanager
    def _session(self, simulated):
        if not self._capacity.acquire(blocking=False):
            raise BitcoinUnavailable("Two Bitcoin lookups are already running. Try again shortly.", 429)
        try:
            if simulated:
                yield None
            else:
                with self._client_factory() as client:
                    yield client
        except (KeyError, TypeError, ValueError, OverflowError, AttributeError):
            raise BitcoinUnavailable(
                "The Bitcoin indexer returned inconsistent or unsupported data. No values were inferred."
            ) from None
        finally:
            self._capacity.release()

    def _tip(self, client, simulated):
        try:
            value = self._read(client, "/blocks/tip/height", simulated)
            if not isinstance(value, str) or not value.isascii() or not value.isdecimal():
                return None
            return normalize.integer(int(value), 100_000_000)
        except BitcoinUnavailable as exc:
            if exc.status == 429:
                raise
            return None
        except (LookupError, ValueError):
            return None

    def _metadata(self, simulated, tip, warnings=None):
        return {
            "source": "demo" if simulated else "mempool.space",
            "network": "demo" if simulated else "bitcoin-mainnet",
            "observed_at": now(),
            "tip_height": tip,
            "warnings": (
                ["Synthetic Demo observations; these are not actual on-chain activity."] if simulated else []
            )
            + (["Chain tip unavailable; confirmation depths may be unknown."] if tip is None else [])
            + (warnings or []),
            "note": "Provider observations are not an atomic chain snapshot or proof of finality. Reorganizations and mempool changes can alter results. Address totals are indexed output values, not verified spendable funds; coinbase maturity and script restrictions are not evaluated. An address is not a complete wallet or an identity.",
        }

    def transaction(self, identity, *, simulated=False, input_offset=0, output_offset=0):
        """Inspect one exact transaction, with paged inputs/outputs and integer-satoshi fee evidence."""
        identity = txid(identity)
        for offset in (input_offset, output_offset):
            if type(offset) is not int or not 0 <= offset <= 9999:
                raise ValueError("Use an input/output offset from 0 to 9,999.")
        with self._session(simulated) as client:
            raw = self._read(client, f"/tx/{identity}", simulated)
            if txid(raw["txid"]) != identity:
                raise BitcoinUnavailable("The Bitcoin provider returned a different transaction.")
            tip = self._tip(client, simulated)
            result = normalize.transaction(raw, tip, input_offset, output_offset)
        warnings = []
        if result["missing_prevouts"]:
            warnings.append("Some previous outputs are unavailable; input totals cannot be fully verified.")
        if result["status"]["confirmed"] and result["status"]["confirmations"] is None:
            warnings.append(
                "Inclusion and chain-tip observations do not provide a consistent confirmation count. Refresh before relying on it."
            )
        return {
            **self._metadata(simulated, tip, warnings),
            "kind": "transaction",
            "transaction": result,
            "url": None if simulated else f"https://mempool.space/tx/{identity}",
        }

    def _history(self, client, selected, cursor, pending, simulated, tip):
        suffix = "/mempool" if pending else "/chain" + (f"/{cursor}" if cursor else "")
        raw = self._read(client, f"/address/{selected}/txs{suffix}", simulated)
        limit = 50 if pending else 25
        if not isinstance(raw, list) or len(raw) > limit:
            raise BitcoinUnavailable("The Bitcoin indexer returned an unsupported history page.")
        rows = [normalize.history_row(row, selected, tip) for row in raw]
        identities = [row["txid"] for row in rows]
        if (
            len(set(identities)) != len(identities)
            or cursor in identities
            or any(row["status"]["confirmed"] == pending for row in rows)
        ):
            raise BitcoinUnavailable(
                "Bitcoin history changed or its page did not advance. Refresh the address before continuing."
            )
        return {
            "items": rows,
            "cursor": cursor,
            "next_cursor": identities[-1] if not pending and len(rows) == 25 else None,
            "pending": pending,
            "limit": limit,
            "truncation_possible": pending and len(rows) == limit,
        }

    def address(self, selected, *, simulated=False):
        """Read indexed confirmed totals, pending deltas and the first confirmed history page."""
        selected = address(selected)
        with self._session(simulated) as client:
            raw = self._read(client, f"/address/{selected}", simulated)
            result = normalize.address_stats(raw)
            if result["address"] != selected:
                raise BitcoinUnavailable("The Bitcoin provider returned a different address.")
            tip = self._tip(client, simulated)
            history = self._history(client, selected, None, False, simulated, tip)
        warnings = (
            []
            if result["projected_balance_sats"] is not None
            else ["Pending totals are inconsistent with confirmed funds; a projected balance is unavailable."]
        )
        return {
            **self._metadata(simulated, tip, warnings),
            "kind": "address",
            "address": result,
            "history": history,
            "url": None if simulated else f"https://mempool.space/address/{selected}",
        }

    def history(self, selected, *, cursor=None, pending=False, simulated=False):
        """Read a bounded confirmed page or up to fifty pending transactions; never imply full history."""
        selected = address(selected)
        cursor = txid(cursor) if cursor else None
        if pending and cursor:
            raise ValueError("Pending Bitcoin history does not support a pagination cursor.")
        with self._session(simulated) as client:
            tip = self._tip(client, simulated)
            history = self._history(client, selected, cursor, pending, simulated, tip)
        return {**self._metadata(simulated, tip), "kind": "history", "address": selected, **history}
