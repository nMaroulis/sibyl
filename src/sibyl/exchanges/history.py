"""Reviewed, one-page spot-fill pagination; all cursor state stays on the server."""

from dataclasses import dataclass
from datetime import UTC, datetime

import ccxt

from sibyl.exchanges.base import number


@dataclass(frozen=True)
class TradePage:
    """Normalized fills and the next durable checkpoint, including an end-of-pass flag.

    ``caught_up`` means the selected provider page range was exhausted, not that
    the account's history or cost basis is complete. A subsequent pass may find
    new fills, including overlapping records that must be upserted by native ID.
    """

    items: list[dict]
    cursor: dict
    caught_up: bool


def normalize_trade(row: dict) -> dict:
    """Strip raw metadata while retaining fee currencies and negative fee rebates."""
    fees = row.get("fees") or ([row["fee"]] if row.get("fee") else [])
    normalized = [{"currency": fee.get("currency"), "cost": number(fee.get("cost"))} for fee in fees]
    return {
        **{key: row.get(key) for key in ("id", "order", "symbol", "side")},
        **{key: number(row.get(key)) for key in ("timestamp", "amount", "price", "cost")},
        "fee": normalized[0] if normalized else {"currency": None, "cost": None},
        "fees": normalized,
    }


def _token(value) -> str | None:
    """Reject malformed provider cursors instead of silently ending a partial import."""
    if value in (None, ""):
        return None
    if not isinstance(value, str) or len(value) > 8192:
        raise ccxt.ExchangeError("Invalid history cursor.")
    return value


def _window(cursor: dict, scale: int = 1000) -> tuple[int, int]:
    """Freeze an import's upper time bound; subsequent passes overlap one day."""
    start = cursor.get("start", 0)
    end = cursor.get("end") or int(datetime.now(UTC).timestamp() * scale)
    return start, end


def fetch_trade_page(exchange, kind: str, symbol: str, cursor: dict, limit: int) -> TradePage:
    """Fetch exactly one native page through CCXT's authenticated transport.

    Binance uses increasing trade IDs, Coinbase Advanced Trade uses its opaque
    token, Exchange Sandbox uses response-header cursors, and Kraken uses its
    cursor API with non-position trades. No generic timestamp-only pagination is
    assumed: fills can share a timestamp and providers have different defaults.
    """
    market = exchange.market(symbol)
    from sibyl.exchanges.spot_history import KINDS, fetch_spot_page

    if kind in KINDS:
        return fetch_spot_page(exchange, kind, symbol, cursor, limit)
    if kind == "binance-id":
        after = int(cursor.get("from_id", "0"))
        rows = exchange.fetch_my_trades(symbol, limit=limit, params={"fromId": str(after)})
        identities = [str(row.get("id", "")) for row in rows]
        if any(not identity.isdecimal() or int(identity) < after for identity in identities):
            raise ccxt.ExchangeError("Invalid history trade IDs.")
        following = str(max(map(int, identities)) + 1) if rows else str(after)
        return TradePage([normalize_trade(row) for row in rows], {"from_id": following}, not rows)

    if kind == "coinbase-cursor":
        start, end = _window(cursor)
        request = {
            "product_ids": [market["id"]],
            "product_types": ["SPOT"],
            "limit": limit,
            "end_sequence_timestamp": exchange.iso8601(end),
        }
        if start:
            request["start_sequence_timestamp"] = exchange.iso8601(start)
        if cursor.get("page"):
            request["cursor"] = cursor["page"]
        response = exchange.v3PrivateGetBrokerageOrdersHistoricalFills(request)
        if response.get("proof_token_required"):
            raise ccxt.PermissionDenied("Additional provider history verification is required.")
        rows = response["fills"]
        following = _token(response.get("cursor"))
        if following and following == cursor.get("page"):
            raise ccxt.ExchangeError("History cursor did not advance.")
        # An empty native page terminates the pass, even if a terminal token is present.
        done = not rows or not following
        next_cursor = (
            {"start": max(0, end - 86_400_000)} if done else {"start": start, "end": end, "page": following}
        )
        parsed = exchange.parse_trades(rows, market)
        if len(parsed) != len(rows):
            raise ccxt.ExchangeError("Unexpected market in fill history.")
        return TradePage([normalize_trade(row) for row in parsed], next_cursor, done)

    if kind == "coinbase-exchange-cursor":
        start, end = _window(cursor)
        request = {"product_id": market["id"], "limit": limit, "end_date": exchange.iso8601(end)}
        if start:
            request["start_date"] = exchange.iso8601(start)
        if cursor.get("page"):
            request["after"] = cursor["page"]
        rows = exchange.privateGetFills(request)
        headers = {key.lower(): value for key, value in (exchange.last_response_headers or {}).items()}
        following = _token(headers.get("cb-after"))
        if following and following == cursor.get("page"):
            raise ccxt.ExchangeError("History cursor did not advance.")
        if rows and len(rows) >= limit and not following:
            raise ccxt.ExchangeError("Missing history pagination header.")
        done = not rows or not following
        next_cursor = (
            {"start": max(0, end - 86_400_000)} if done else {"start": start, "end": end, "page": following}
        )
        parsed = exchange.parse_trades(rows, market)
        if len(parsed) != len(rows):
            raise ccxt.ExchangeError("Unexpected market in fill history.")
        return TradePage([normalize_trade(row) for row in parsed], next_cursor, done)

    if kind == "kraken-cursor":
        start, end = _window(cursor, scale=1)
        request = {
            "type": "no position",
            "pair": market["id"],
            "with_cursor": True,
            "consolidate_taker": False,
            "limit": limit,
            "end": end,
        }
        if start:
            request["start"] = start
        if cursor.get("page"):
            request["cursor"] = cursor["page"]
        result = exchange.privatePostTradesHistory(request)["result"]
        rows = [{**row, "id": identity} for identity, row in result["trades"].items()]
        following = _token((result.get("cursor") or {}).get("next"))
        if following and following == cursor.get("page"):
            raise ccxt.ExchangeError("History cursor did not advance.")
        if "cursor" not in result and (len(rows) >= limit or (number(result.get("count")) or 0) > len(rows)):
            raise ccxt.ExchangeError("Missing history pagination cursor.")
        done = not rows or not following
        next_cursor = (
            {"start": max(0, end - 86_400)} if done else {"start": start, "end": end, "page": following}
        )
        parsed = exchange.parse_trades(rows, market)
        if len(parsed) != len(rows):
            raise ccxt.ExchangeError("Unexpected market in fill history.")
        return TradePage([normalize_trade(row) for row in parsed], next_cursor, done)
    raise ccxt.NotSupported("Durable history import is not enabled for this provider.")
