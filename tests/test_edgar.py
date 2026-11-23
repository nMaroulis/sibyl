"""Bound and attribute official EDGAR requests with controlled index responses."""

import httpx
import pytest

from sibyl.services.research.edgar import Edgar

CIK = "0000320193"
PAST = f"CIK{CIK}-submissions-001.json"
CONTACT = "operator@example.test"


def index(*observations):
    ids, dates, forms = zip(*observations, strict=True)
    return {"accessionNumber": list(ids), "filingDate": list(dates), "form": list(forms)}


@pytest.fixture
def source():
    requests = []

    def respond(request):
        requests.append(request)
        assert request.headers["User-Agent"] == f"Sibyl EDGAR lookup {CONTACT}"
        assert "Authorization" not in request.headers
        if request.url.host == "www.sec.gov" and request.url.path == "/files/company_tickers.json":
            return httpx.Response(200, json={"0": {"ticker": "AAPL", "cik_str": int(CIK)}})
        assert request.url.host == "data.sec.gov"
        if request.url.path.endswith(PAST):
            return httpx.Response(200, json=index(("0000320193-02-000020", "2002-09-23", "10-K")))
        assert request.url.path == f"/submissions/CIK{CIK}.json"
        return httpx.Response(
            200,
            json={
                "cik": int(CIK),
                "name": "APPLE INC",
                "filings": {
                    "recent": index(
                        ("0000320193-25-000126", "2025-12-10", "8-K"),
                        ("0000320193-25-000079", "2025-10-31", "10-K"),
                    ),
                    "files": [
                        {"name": PAST, "filingFrom": "1995-01-01", "filingTo": "2003-03-31"},
                        {"name": "../../out", "filingFrom": "1995-01-01", "filingTo": "2003-03-31"},
                    ],
                },
            },
        )

    return Edgar(CONTACT, transport=httpx.MockTransport(respond)), requests


def test_sec_routes_page_filter_and_passive_evidence(client, source, monkeypatch):
    edgar, requests = source
    research = client.app.state.services.research
    monkeypatch.setattr(research, "edgar", edgar)
    endpoint = "/api/v1/equities/disclosures"
    assert client.get(endpoint + "/status").json()["configured"]
    assert not edgar.evidence("AAPL")["items"] and requests == []
    response = client.get(endpoint, params={"issuer": "aapl", "limit": 1})
    assert response.status_code == 200, response.text
    page = response.json()
    assert page["cik"] == CIK and page["total"] == 2
    assert page["items"][0]["url"] == (
        "https://www.sec.gov/Archives/edgar/data/320193/000032019325000126/0000320193-25-000126-index.html"
    )
    assert page["archives"] == [{"id": PAST, "from": "1995-01-01", "to": "2003-03-31"}]
    assert CONTACT not in response.text and len(requests) == 2
    filtered = client.get(endpoint, params={"issuer": "aapl", "form": "10-K"}).json()
    assert filtered["total"] == 1 and len(requests) == 2
    assert len(edgar.evidence("AAPL")["items"]) == 2 and len(requests) == 2
    older = client.get(endpoint, params={"issuer": CIK, "archive": PAST}).json()
    assert older["items"][0]["filed"] == "2002-09-23" and len(requests) == 3
    invalid = client.get(endpoint, params={"issuer": CIK, "archive": "../../out"})
    assert invalid.status_code == 404 and len(requests) == 3


def test_sec_access_failure_is_sanitized_and_defers_further_reads():
    calls = []

    def blocked(request):
        calls.append(request)
        return httpx.Response(429, json={"detail": "private origin details"})

    edgar = Edgar(CONTACT, transport=httpx.MockTransport(blocked))
    with pytest.raises(ValueError, match="could not provide"):
        edgar.page(CIK)
    with pytest.raises(ValueError, match="slow down"):
        edgar.page(CIK)
    assert len(calls) == 1


def test_unconfigured_sec_does_not_make_requests(source):
    edgar, calls = source
    missing = Edgar("invalid operator contact", transport=edgar.transport)
    assert missing.status() == {"configured": False, "source": "SEC EDGAR", "setting": "SIBYL_SEC_CONTACT"}
    with pytest.raises(ValueError, match="SIBYL_SEC_CONTACT"):
        missing.page(CIK)
    assert not calls
