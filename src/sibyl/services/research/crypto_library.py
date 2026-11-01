"""Read-through public crypto profiles, with attributed history and independent source failures."""

import html
import json
import math
import os
import re
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx


@dataclass(frozen=True)
class CryptoAsset:
    """A deliberate editorial selection, not a live market-cap ranking."""

    id: str
    symbol: str
    name: str
    category: str
    wikipedia: str
    color: str


ASSETS = {
    asset.id: asset
    for asset in [
        CryptoAsset("btc-bitcoin", "BTC", "Bitcoin", "Payments", "Bitcoin", "#c6974e"),
        CryptoAsset("eth-ethereum", "ETH", "Ethereum", "Smart contracts", "Ethereum", "#7888c1"),
        CryptoAsset("usdt-tether", "USDT", "Tether", "Stablecoins", "Tether (cryptocurrency)", "#5b9e87"),
        CryptoAsset("bnb-binance-coin", "BNB", "BNB", "Smart contracts", "Binance", "#b89c4c"),
        CryptoAsset("xrp-xrp", "XRP", "XRP", "Payments", "XRP Ledger", "#6d8295"),
        CryptoAsset(
            "sol-solana", "SOL", "Solana", "Smart contracts", "Solana (blockchain platform)", "#8f7dbb"
        ),
        CryptoAsset("usdc-usd-coin", "USDC", "USDC", "Stablecoins", "USD Coin", "#668fbf"),
        CryptoAsset("doge-dogecoin", "DOGE", "Dogecoin", "Meme coins", "Dogecoin", "#b49a5e"),
        CryptoAsset(
            "ada-cardano", "ADA", "Cardano", "Smart contracts", "Cardano (blockchain platform)", "#6483b4"
        ),
        CryptoAsset("trx-tron", "TRX", "TRON", "Smart contracts", "Tron (blockchain)", "#be777a"),
        CryptoAsset(
            "avax-avalanche",
            "AVAX",
            "Avalanche",
            "Smart contracts",
            "Avalanche (blockchain platform)",
            "#bc7a77",
        ),
        CryptoAsset("link-chainlink", "LINK", "Chainlink", "Oracles", "Chainlink (blockchain)", "#6487bc"),
        CryptoAsset(
            "dot-polkadot", "DOT", "Polkadot", "Smart contracts", "Polkadot (cryptocurrency)", "#b5779a"
        ),
        CryptoAsset("ltc-litecoin", "LTC", "Litecoin", "Payments", "Litecoin", "#7994b3"),
        CryptoAsset("bch-bitcoin-cash", "BCH", "Bitcoin Cash", "Payments", "Bitcoin Cash", "#76a28d"),
        CryptoAsset("xmr-monero", "XMR", "Monero", "Privacy", "Monero", "#bc926d"),
        CryptoAsset("xlm-stellar", "XLM", "Stellar", "Payments", "Stellar (payment network)", "#7b8fa1"),
        CryptoAsset(
            "shib-shiba-inu", "SHIB", "Shiba Inu", "Meme coins", "Shiba Inu (cryptocurrency)", "#bf9371"
        ),
        CryptoAsset("uni-uniswap", "UNI", "Uniswap", "DeFi", "Uniswap", "#bd85a3"),
        CryptoAsset(
            "etc-ethereum-classic",
            "ETC",
            "Ethereum Classic",
            "Smart contracts",
            "Ethereum Classic",
            "#779c8c",
        ),
    ]
}


class CryptoSourceError(Exception):
    """A safe, source-specific failure without upstream response bodies or secrets."""


def text(value, limit=5000) -> str:
    """Return bounded plain text; provider HTML is never rendered as markup."""
    if not isinstance(value, str):
        return ""
    return html.unescape(re.sub(r"<[^>]*>", "", value)).strip()[:limit]


def safe_url(value) -> str | None:
    """Only expose credential-free HTTP(S) source links."""
    if not isinstance(value, str) or len(value) > 2000:
        return None
    try:
        url = urlsplit(value)
        _ = url.port
        if not url.hostname or any(char.isspace() or ord(char) < 32 for char in value) or "%" in url.hostname:
            return None
        return (
            value
            if url.scheme in {"http", "https"} and url.hostname and not url.username and not url.password
            else None
        )
    except ValueError:
        return None


def finite(value) -> float | None:
    """Normalize missing/non-finite provider numbers rather than inventing zeros."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if math.isfinite(value) else None


def article_sections(extract: str) -> tuple[str, list[dict]]:
    """Preserve fetched history sections and their order without generating a narrative."""
    headings = list(re.finditer(r"(?m)^(={2,6})\s*(.+?)\s*\1\s*$", extract))
    introduction = text(extract[: headings[0].start()] if headings else extract, 3500)
    result, history_level = [], None
    for i, match in enumerate(headings):
        level, heading = len(match[1]), match[2]
        if history_level is not None and level <= history_level:
            history_level = None
        if re.search(r"\b(history|background|origins|founding|creation|launch|development)\b", heading, re.I):
            history_level = level if history_level is None else history_level
        if history_level is None:
            continue
        body = text(
            extract[match.end() : headings[i + 1].start() if i + 1 < len(headings) else len(extract)], 2000
        )
        if body:
            result.append({"title": text(heading, 160), "text": body})
        if len(result) == 8:
            break
    return introduction, result


class CryptoLibrary:
    """Fetch public research independently of the demo/live trading data setting.

    Only whitelisted asset IDs are accepted. Each source has its own persistent
    TTL cache and lock. A failed refresh may serve its previous observation with
    an explicit stale flag; failures never produce fabricated profile content.
    """

    TTL = {"profile": 86400, "history": 86400, "market": 900}
    SOURCE_NAMES = {
        "profile": "CoinPaprika profile",
        "history": "Wikipedia",
        "market": "CoinPaprika market data",
    }

    def __init__(self, directory: Path):
        self.directory = directory / "crypto-research"
        self._locks = {(asset, part): threading.Lock() for asset in ASSETS for part in self.TTL}
        self._network = threading.BoundedSemaphore(4)

    def catalog(self) -> dict:
        """List the 20 selected assets without fetching 20 full profiles on page load."""
        return {
            "items": [asdict(asset) for asset in ASSETS.values()],
            "selection_note": "20 widely known assets, selected for familiarity and variety; not a live ranking or recommendation.",
            "data_note": "Public profiles are fetched by the backend, including in demo trading mode.",
        }

    def _json(self, url: str, **params):
        """Bound provider time, response bytes, and concurrent requests."""
        with self._network:
            try:
                with httpx.stream(
                    "GET",
                    url,
                    params=params,
                    timeout=12,
                    headers={
                        "User-Agent": "Sibyl/0.2 (https://github.com/nMaroulis/sibyl; public research)",
                        "Accept": "application/json",
                    },
                ) as response:
                    response.raise_for_status()
                    data = bytearray()
                    for chunk in response.iter_bytes():
                        data.extend(chunk)
                        if len(data) > 1_000_000:
                            raise CryptoSourceError("The provider response exceeded the supported size.")
                return json.loads(data)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429:
                    raise CryptoSourceError("Provider rate limit reached; retry after one minute.") from exc
                raise CryptoSourceError("The provider could not supply this source.") from exc
            except (httpx.HTTPError, ValueError) as exc:
                raise CryptoSourceError("The source could not be reached or returned invalid data.") from exc

    def _fetch(self, asset: CryptoAsset, part: str) -> dict:
        """Normalize provider payloads into a small, source-labeled contract."""
        if part == "profile":
            data = self._json(f"https://api.coinpaprika.com/v1/coins/{asset.id}")
            if not isinstance(data, dict) or data.get("id") != asset.id:
                raise CryptoSourceError("The provider returned a different or invalid asset.")
            links = []
            for kind in ("website", "source_code", "explorer", "technical_doc"):
                for url in (data.get("links") or {}).get(kind, [])[:3]:
                    if safe_url(url):
                        links.append(
                            {
                                "label": {
                                    "website": "Official website",
                                    "source_code": "Source code",
                                    "explorer": "Block explorer",
                                    "technical_doc": "Technical documentation",
                                }[kind],
                                "url": url,
                            }
                        )
            whitepaper = safe_url((data.get("whitepaper") or {}).get("link"))
            if whitepaper:
                links.append({"label": "Whitepaper", "url": whitepaper})
            return {
                "description": text(data.get("description"), 6000),
                "launch_date": text(data.get("started_at"), 100) or None,
                "proof_type": text(data.get("proof_type"), 100),
                "organization": text(data.get("org_structure"), 100),
                "development_status": text(data.get("development_status"), 100),
                "open_source": data.get("open_source") if isinstance(data.get("open_source"), bool) else None,
                "tags": [text(tag.get("name"), 80) for tag in data.get("tags", [])[:10]],
                "team": [
                    {"name": text(member.get("name"), 100), "position": text(member.get("position"), 120)}
                    for member in data.get("team", [])[:8]
                ],
                "links": links,
            }
        if part == "market":
            data = self._json(f"https://api.coinpaprika.com/v1/tickers/{asset.id}", quotes="USD")
            if not isinstance(data, dict) or data.get("id") != asset.id:
                raise CryptoSourceError("The provider returned a different or invalid asset.")
            quote_data = (data.get("quotes") or {}).get("USD")
            if not isinstance(quote_data, dict):
                raise CryptoSourceError("USD market data is unavailable for this asset.")
            fields = (
                "price",
                "market_cap",
                "volume_24h",
                "percent_change_24h",
                "percent_change_7d",
                "percent_change_30d",
                "percent_change_1y",
                "ath_price",
                "percent_from_price_ath",
            )
            return {
                **{field: finite(quote_data.get(field)) for field in fields},
                **{
                    field: finite(data.get(field))
                    for field in ("rank", "circulating_supply", "total_supply", "max_supply")
                },
                "ath_date": text(quote_data.get("ath_date"), 100) or None,
                "updated_at": text(data.get("last_updated"), 100) or None,
                "first_data_at": text(data.get("first_data_at"), 100) or None,
                "currency": "USD",
            }
        data = self._json(
            "https://en.wikipedia.org/w/api.php",
            action="query",
            format="json",
            formatversion=2,
            prop="extracts|info",
            inprop="url",
            explaintext=1,
            redirects=1,
            titles=asset.wikipedia,
        )
        pages = data.get("query", {}).get("pages", []) if isinstance(data, dict) else []
        if not pages or pages[0].get("missing") or not pages[0].get("extract"):
            raise CryptoSourceError("No encyclopedia background is available for this asset.")
        page = pages[0]
        intro, history = article_sections(page["extract"])
        return {
            "title": text(page.get("title"), 200),
            "introduction": intro,
            "sections": history,
            "url": safe_url(page.get("fullurl")) or f"https://en.wikipedia.org/wiki/{quote(asset.wikipedia)}",
            "revision": finite(page.get("lastrevid")),
            "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
            "article_note": "This article covers Binance as well as the BNB ecosystem."
            if asset.symbol == "BNB"
            else None,
        }

    def _read(self, asset: CryptoAsset, part: str) -> dict:
        """Use cached successes; preserve stale observations if a refresh fails."""
        with self._locks[(asset.id, part)]:
            path = self.directory / f"{asset.id}-{part}.json"
            cached = {}
            try:
                candidate = json.loads(path.read_text())
                if (
                    isinstance(candidate, dict)
                    and candidate.get("version") == 1
                    and finite(candidate.get("checked_at")) is not None
                    and (
                        candidate.get("value") is None
                        or (
                            isinstance(candidate["value"], dict)
                            and finite(candidate.get("fetched_at")) is not None
                        )
                    )
                ):
                    cached = candidate
            except (OSError, ValueError, AttributeError):
                pass
            now = time.time()
            ttl = 60 if cached.get("error") else self.TTL[part]
            fresh = 0 <= now - cached.get("checked_at", 0) < ttl
            if not fresh:
                try:
                    value = self._fetch(asset, part)
                    cached = {
                        "version": 1,
                        "value": value,
                        "fetched_at": now,
                        "checked_at": now,
                        "error": None,
                    }
                except (CryptoSourceError, KeyError, TypeError, AttributeError) as exc:
                    message = (
                        str(exc)
                        if isinstance(exc, CryptoSourceError)
                        else "The provider returned an unsupported response."
                    )
                    cached = {**cached, "version": 1, "checked_at": now, "error": message}
                try:
                    self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
                    with tempfile.NamedTemporaryFile(mode="w", dir=self.directory, delete=False) as file:
                        json.dump(cached, file, allow_nan=False)
                        temporary = file.name
                    os.replace(temporary, path)
                except OSError:
                    pass  # Public research can still be read when caching is unavailable.
            value = cached.get("value")
            # CoinPaprika uses zero for assets without a reported maximum; it is not a zero-token cap.
            if part == "market" and value and (finite(value.get("max_supply")) or 0) <= 0:
                value = {**value, "max_supply": None}
            return {
                "data": value,
                "source": self.SOURCE_NAMES[part],
                "url": (value.get("url") if value and part == "history" else None)
                or (
                    f"https://en.wikipedia.org/wiki/{quote(asset.wikipedia)}"
                    if part == "history"
                    else f"https://coinpaprika.com/coin/{asset.id}/"
                ),
                "cached": fresh,
                "stale": value is not None and bool(cached.get("error")),
                "error": cached.get("error"),
                "as_of": datetime.fromtimestamp(cached["fetched_at"], UTC).isoformat()
                if cached.get("fetched_at")
                else None,
            }

    def profile(self, asset_id: str) -> dict:
        """Fetch only the selected profile, returning partial data when one source fails."""
        if asset_id not in ASSETS:
            raise LookupError("Unknown cryptocurrency profile.")
        asset = ASSETS[asset_id]
        with ThreadPoolExecutor(max_workers=3) as pool:
            values = list(pool.map(lambda part: self._read(asset, part), self.TTL))
        sources = dict(zip(self.TTL, values, strict=True))
        count = sum(source["data"] is not None for source in sources.values())
        return {
            "asset": asdict(asset),
            "profile": sources["profile"]["data"],
            "history": sources["history"]["data"],
            "market": sources["market"]["data"],
            "sources": [
                {"part": part, **{key: value for key, value in source.items() if key != "data"}}
                for part, source in sources.items()
            ],
            "status": "ready"
            if count == 3 and not any(source["error"] for source in sources.values())
            else "partial"
            if count
            else "unavailable",
            "source": "Public research · CoinPaprika / Wikipedia",
            "as_of": datetime.now(UTC).isoformat(),
        }
