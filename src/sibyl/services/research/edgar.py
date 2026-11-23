"""Read official SEC filing indices with explicit operator contact and bounded local caching."""

import json
import re
from collections import OrderedDict
from datetime import date
from threading import Lock
from time import monotonic, sleep

import httpx

DATA = "https://data.sec.gov/submissions/"
SYMBOLS = "https://www.sec.gov/files/company_tickers.json"
ARCHIVES = "https://www.sec.gov/Archives/edgar/data/"
CONTACT = re.compile(r"[!-~]{1,200}@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
TICKER = re.compile(r"[A-Z][A-Z0-9.-]{0,11}")
ACCESSION = re.compile(r"[0-9]{10}-[0-9]{2}-[0-9]{6}")
FORM = re.compile(r"[A-Z0-9 /.-]{1,24}")
MAX_BYTES = 8 * 1024 * 1024
TTL = 900


def day(value):
    """Accept only valid ISO filing dates in the registry's documented form."""
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError
    return value


def filing_rows(cik, columns):
    """Build links from exact accession numbers rather than response-provided URLs."""
    fields = ("accessionNumber", "filingDate", "form")
    if not isinstance(columns, dict) or any(not isinstance(columns.get(key), list) for key in fields):
        raise ValueError
    ids, dates, forms = (columns[key] for key in fields)
    if not len(ids) == len(dates) == len(forms) <= 15000:
        raise ValueError
    result = []
    seen = set()
    for accession, filed, form in zip(ids, dates, forms, strict=True):
        if not ACCESSION.fullmatch(accession) or not FORM.fullmatch(form) or accession in seen:
            raise ValueError
        seen.add(accession)
        result.append(
            {
                "accession": accession,
                "filed": day(filed),
                "form": form,
                "url": f"{ARCHIVES}{int(cik)}/{accession.replace('-', '')}/{accession}-index.html",
            }
        )
    return sorted(result, key=lambda row: (row["filed"], row["accession"]), reverse=True)


class Edgar:
    """Fetch indexed public company filings and share recent results with the Equity Analyst."""

    def __init__(self, contact="", *, transport=None):
        self.contact = contact if CONTACT.fullmatch(contact) else ""
        self.transport = transport
        self.lock = Lock()
        self.cache = OrderedDict()
        self.cooldown_until = self.next_read = 0.0

    def status(self):
        """Return readiness without exposing the operator contact or requesting SEC data."""
        return {"configured": bool(self.contact), "source": "SEC EDGAR", "setting": "SIBYL_SEC_CONTACT"}

    def _read(self, url, *, lifetime=TTL):
        key = ("source", url)
        try:
            return self._cached(key)
        except LookupError:
            pass
        if monotonic() < self.cooldown_until:
            raise ValueError("SEC EDGAR asked this workspace to slow down. Try again in one minute.")
        sleep(max(0.0, self.next_read - monotonic()))
        self.next_read = monotonic() + 0.25
        try:
            with (
                httpx.Client(
                    timeout=httpx.Timeout(8, connect=3),
                    follow_redirects=False,
                    trust_env=False,
                    transport=self.transport,
                ) as client,
                client.stream(
                    "GET",
                    url,
                    headers={
                        "User-Agent": f"Sibyl EDGAR lookup {self.contact}",
                        "Accept": "application/json",
                    },
                ) as response,
            ):
                if response.status_code == 404:
                    raise LookupError("SEC EDGAR could not find this filing index.")
                if response.status_code in {403, 429}:
                    self.cooldown_until = monotonic() + 60
                response.raise_for_status()
                data = bytearray()
                for chunk in response.iter_bytes(chunk_size=65536):
                    data.extend(chunk)
                    if len(data) > MAX_BYTES:
                        raise ValueError("This filing index exceeds the 8 MiB response limit.")
            parsed = json.loads(data)
        except httpx.HTTPError:
            raise ValueError(
                "SEC EDGAR could not provide the filing index. Check availability and operator contact."
            ) from None
        self._remember(key, parsed, lifetime)
        return parsed

    def _remember(self, key, data, lifetime=TTL):
        self.cache[key] = (monotonic() + lifetime, data)
        self.cache.move_to_end(key)
        while len(self.cache) > 18:
            self.cache.popitem(last=False)

    def _cached(self, key):
        item = self.cache.get(key)
        if item is None or item[0] <= monotonic():
            raise LookupError("Load these filings in Research → Equities first.")
        self.cache.move_to_end(key)
        return item[1]

    @staticmethod
    def _ticker(value):
        return value.strip().upper().replace(".", "-")

    def _cik(self, value):
        if re.fullmatch(r"[0-9]{1,10}", value) and int(value):
            return value.zfill(10)
        if not TICKER.fullmatch(value):
            raise ValueError("Enter one exact ticker or EDGAR CIK.")
        payload = self._read(SYMBOLS, lifetime=86400)
        if not isinstance(payload, dict):
            raise ValueError
        matches = {
            str(row["cik_str"]).zfill(10)
            for row in payload.values()
            if isinstance(row, dict)
            and isinstance(row.get("ticker"), str)
            and self._ticker(row["ticker"]) == value
            and type(row.get("cik_str")) is int
            and 0 < row["cik_str"] < 10**10
        }
        if len(matches) != 1:
            raise LookupError("No unique SEC ticker match. Enter the issuer’s CIK.")
        return matches.pop()

    def page(self, issuer, archive=None, form=None, *, offset=0, limit=25):
        """Read recent or explicitly selected older filing metadata for one validated issuer."""
        if not self.contact:
            raise ValueError("Set SIBYL_SEC_CONTACT to the workspace operator’s email and restart Sibyl.")
        issuer = self._ticker(issuer)
        if form and not FORM.fullmatch(form):
            raise ValueError("Enter an exact filing form such as 10-K or 8-K.")
        with self.lock:
            try:
                cik = self._cik(issuer)
                root = self._read(f"{DATA}CIK{cik}.json")
                if str(root["cik"]).zfill(10) != cik or not isinstance(root["name"], str):
                    raise ValueError
                filings = root["filings"]
                pages = [
                    {"id": entry["name"], "from": day(entry["filingFrom"]), "to": day(entry["filingTo"])}
                    for entry in filings["files"]
                    if re.fullmatch(rf"CIK{cik}-submissions-[0-9]{{3,6}}\.json", entry["name"])
                ]
                if archive is not None and archive not in {entry["id"] for entry in pages}:
                    raise LookupError("This historical index does not belong to the selected SEC issuer.")
                columns = self._read(f"{DATA}{archive}") if archive else filings["recent"]
                items = filing_rows(cik, columns)
            except (AttributeError, KeyError, TypeError):
                raise ValueError("SEC EDGAR returned an invalid filing index.") from None
            report = {"source": "SEC EDGAR", "cik": cik, "name": root["name"], "archive": archive}
            self._remember(("result", issuer), {**report, "items": items[:10]})
            selected = [row for row in items if row["form"] == form] if form else items
            return {
                **report,
                "archives": pages,
                "items": selected[offset : offset + limit],
                "total": len(selected),
            }

    def evidence(self, issuer):
        """Read at most ten filings from the latest loaded public index for this issuer."""
        with self.lock:
            try:
                return self._cached(("result", self._ticker(issuer)))
            except LookupError:
                return {"source": "SEC EDGAR", "items": [], "note": "Load filings in Research → Equities."}
