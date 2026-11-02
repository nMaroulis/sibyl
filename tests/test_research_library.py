"""Real extraction, transactional indexing and attributable native-agent retrieval."""

import base64
import io
from datetime import UTC, datetime

import pytest
from protolink import create_llm

from sibyl.news.repository import NewsRepository
from sibyl.research_library.extraction import extract
from sibyl.research_library.service import ResearchLibrary


@pytest.fixture
def library(settings):
    return ResearchLibrary(settings.data_dir, NewsRepository(settings.data_dir))


def test_document_search_citations_deduplication_and_deletion(library):
    text = ("A liquidity reserve is not a promise of solvency.\n" * 100).encode()
    item = library.import_document(
        "memo.md",
        text,
        title="Liquidity memorandum",
        publisher="Research desk",
        url="https://example.org/memo",
        published_at="2026-01-02",
    )
    assert item["total_passages"] > 1
    first = item["passages"][0]
    assert first["text"] == text.decode()[first["start"] : first["stop"]]
    assert library.passage(first["id"])["source"]["title"] == "Liquidity memorandum"
    matches = library.search("liquidity")
    assert matches["items"] and matches["items"][0]["source"]["source_url"] == "https://example.org/memo"
    assert "original" not in str(item.keys()) and "data_base64" not in str(matches)
    duplicate = library.import_document("other.txt", text, title="Must not overwrite")
    assert duplicate["duplicate"] and duplicate["id"] == item["id"] and duplicate["title"] == item["title"]
    assert library.reindex(item["id"])["fingerprint"] == item["fingerprint"]
    library.delete(item["id"])
    assert not library.search("liquidity")["items"]
    with pytest.raises(LookupError):
        library.passage(first["id"])


def test_reindex_never_reassigns_an_old_citation_to_changed_text(library, monkeypatch):
    item = library.import_document("source.txt", b"Original passage evidence.")
    old = item["passages"][0]["id"]
    monkeypatch.setattr(
        "sibyl.research_library.service.extract",
        lambda *a: [{"page": 1, "text": "Changed extraction evidence."}],
    )
    changed = library.reindex(item["id"])
    assert changed["passages"][0]["id"] != old
    with pytest.raises(LookupError):
        library.passage(old)


def test_news_index_only_uses_retained_archive_and_removes_expired_copies(library):
    now = datetime.now(UTC)
    article = {
        "id": "archive-1",
        "source_id": "publisher",
        "title": "Network memo",
        "body": "A unique quasar network observation.",
        "url": "https://example.org/news",
        "publisher": "Test publisher",
        "published_at": now.isoformat(),
    }
    library.news.save("publisher", {}, [article], now, 30)
    assert library.synchronize_news()["indexed_news"] == 1
    result = library.search("quasar", kind="news")["items"][0]
    assert result["kind"] == "news" and result["source"]["publisher"] == "Test publisher"
    with pytest.raises(ValueError, match="archive"):
        library.delete(result["document_id"])
    with library.news.connect() as db:
        db.execute("DELETE FROM articles")
    library.synchronize_news()
    assert not library.search("quasar")["items"]


def test_headline_only_news_still_has_searchable_attributable_text(library):
    now = datetime.now(UTC)
    library.news.save(
        "publisher",
        {},
        [
            {
                "id": "headline",
                "source_id": "publisher",
                "title": "Quasar network headline",
                "published_at": now.isoformat(),
            }
        ],
        now,
        30,
    )
    library.synchronize_news()
    result = library.search("quasar", kind="news")["items"][0]
    assert result["text"] == "Quasar network headline"


@pytest.mark.parametrize("query", ['" OR * NOT (', "RSI; DROP TABLE documents; --", "\x00", "猫éthereum"])
def test_query_syntax_is_data_not_fts_or_sql_instructions(library, query):
    library.import_document("rsi.txt", b"RSI compares smoothed gains and losses.")
    library.search(query)
    assert library.catalog()["counts"]["document"] == 1


def pdf_bytes(*, encrypted=False, blank=False):
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=600, height=800)
    if not blank:
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
        )
        stream = DecodedStreamObject()
        stream.set_data(b"BT /F1 12 Tf 40 700 Td (Liquidity reserve research) Tj ET")
        page[NameObject("/Contents")] = writer._add_object(stream)
    if encrypted:
        writer.encrypt("not-imported")
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def test_real_pdf_text_extraction_in_child_process(library):
    result = library.import_document("source.pdf", pdf_bytes())
    assert "Liquidity reserve research" in result["passages"][0]["text"]
    assert result["passages"][0]["page"] == 1


def test_small_pdf_with_excessive_decoded_stream_is_rejected_before_indexing(library):
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import DecodedStreamObject, NameObject

    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(pdf_bytes())))
    contents = DecodedStreamObject()
    contents.set_data(b"q\n" * (9 * 1024 * 1024 // 2))
    writer.pages[0][NameObject("/Contents")] = writer._add_object(contents.flate_encode())
    output = io.BytesIO()
    writer.write(output)
    assert len(output.getvalue()) < 100000
    with pytest.raises(ValueError, match="extraction failed"):
        library.import_document("compressed.pdf", output.getvalue())
    assert not library.catalog()["items"]


@pytest.mark.parametrize("content,match", [(b"", "nonempty"), (b"\xff\xfe", "UTF-8")])
def test_invalid_text_is_rejected(library, content, match):
    with pytest.raises(ValueError, match=match):
        library.import_document("source.txt", content)
    assert not library.catalog()["items"]


def test_encrypted_and_scanned_pdfs_are_not_invented_text():
    with pytest.raises(ValueError, match="unencrypted"):
        extract("secret.pdf", pdf_bytes(encrypted=True))
    with pytest.raises(ValueError, match="OCR"):
        extract("scan.pdf", pdf_bytes(blank=True))


def test_upload_api_privacy_native_retrieval_and_missing_citation(client, monkeypatch):
    uploaded = client.post(
        "/api/v1/library/documents",
        json={
            "filename": "memo.txt",
            "title": "Research memorandum",
            "data_base64": base64.b64encode(b"Quasar reserves do not guarantee solvency.").decode(),
        },
    )
    assert uploaded.status_code == 201, uploaded.text
    item = uploaded.json()
    passage = item["passages"][0]
    client.post("/api/v1/settings/llm", json={"provider": "mock"}).raise_for_status()
    monkeypatch.setattr(
        "sibyl.agents.utils.registry.create_llm",
        lambda *a, **k: create_llm(
            "mock",
            sequential_responses=[
                {
                    "type": "tool_call",
                    "tool": "search_research",
                    "args": {"query": "quasar", "kind": "document"},
                },
                f"The memorandum cautions about reserves: {passage['url']}",
            ],
        ),
    )
    reply = client.post(
        "/api/v1/agents/ask",
        json={"module": "wiki", "message": "What does my memorandum say about reserves?"},
    )
    assert reply.status_code == 200, reply.text
    actual = reply.json()["observations"][0]
    assert actual["tool"] == "search_research" and actual["evidence"]["items"][0]["text"] == passage["text"]
    assert (
        client.get("/api/v1/library/search", params={"query": "quasar"}).headers["cache-control"]
        == "no-store"
    )
    client.delete(f"/api/v1/library/documents/{item['id']}").raise_for_status()
    assert client.get("/api/v1/library/passages/" + passage["id"]).status_code == 404


def test_no_llm_library_dialog_returns_selected_source_not_a_glossary(client):
    item = client.app.state.services.library.import_document("memo.txt", b"Quasar reserve research.")
    reply = client.post(
        "/api/v1/agents/ask",
        json={"module": "wiki", "message": "Explain this", "context": {"library_document_id": item["id"]}},
    )
    assert reply.status_code == 200, reply.text
    assert reply.json()["tool"] == "read_research_document"
    assert "source excerpt" in reply.json()["answer"] and "Quasar" in reply.json()["answer"]


def test_native_missing_library_selection_is_correctable(client, monkeypatch):
    client.post("/api/v1/settings/llm", json={"provider": "mock"})
    monkeypatch.setattr(
        "sibyl.agents.utils.registry.create_llm",
        lambda *a, **k: create_llm(
            "mock",
            sequential_responses=[
                {"type": "tool_call", "tool": "read_research_document", "args": {"document_id": "f" * 32}},
                {"type": "tool_call", "tool": "search_research", "args": {"query": "unmatched"}},
                "The source is missing, and no current source matches.",
            ],
        ),
    )
    reply = client.post(
        "/api/v1/agents/ask", json={"module": "reporter", "message": "Read the missing saved source"}
    )
    assert reply.status_code == 200, reply.text
    report = client.app.state.services.agents.network.run_store.get_report(reply.json()["run_id"])
    assert [e.outcome for e in report.tool_evidence] == ["rejected", "completed"]


def test_invalid_upload_does_not_echo_content_or_metadata(client):
    result = client.post(
        "/api/v1/library/documents",
        json={
            "filename": "secret.txt",
            "data_base64": "PRIVATE-NOT-BASE64",
            "source_url": "javascript:PRIVATE-METADATA",
        },
    )
    assert result.status_code == 422 and "PRIVATE" not in result.text
