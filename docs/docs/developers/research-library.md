---
title: Research library contracts
description: Bounded ingestion, coherent SQLite retrieval, exact citations and native read-only tools.
---

# Research library contracts

`research_library/` owns ingestion, text extraction and retrieval; its `ResearchLibrary` instance is shared by FastAPI and the existing Wiki/Reporter agent declarations. It does not add an agent router, vector framework or model dependency.

## Persistence and extraction

`research-library.sqlite` stores source metadata, original upload BLOBs, extracted pages and passage/FTS5 rows. Imports publish all rows in one transaction. A content SHA-256 prevents duplicate uploads from overwriting original attribution. Document reads use a coherent transaction across metadata, passage rows and counts.

Text/Markdown must be UTF-8. PDFs use `pypdf` in a disposable child process with a twenty-second parent deadline, CPU limits where supported, page/text/decoded-stream limits and at most two simultaneous extractions. The child does not execute PDF JavaScript, fetch URLs or perform OCR. These are parsing limits, not an OS-independent memory sandbox. Failed/empty/oversized extraction publishes no source.

Passages are exact, overlapping, page-bounded slices: up to 1,600 characters with 160-character overlap. IDs include document ID, ordinal and a text fingerprint. Reindexing replaces the complete search representation; changed passages do not reuse old citation IDs. Removal deletes active entries, not copies in old reports/backups or securely erased storage.

Search tokenizes a bounded query into quoted OR terms, binds SQL parameters and ranks SQLite FTS5 matches with BM25. It returns actual text, source metadata and in-app passage links. Ranking is lexical relevance, not semantic grounding or confidence. FTS5-enabled SQLite is required. Embeddings, hybrid retrieval and cited web search remain pending.

## Retained news

A supervised worker copies the existing bounded news archive into the same index. It does no publisher HTTP work. Source/date/excerpt labels remain explicit; expired articles are removed on the next sync. A manual sync endpoint provides the same operation. Long retained excerpts are bounded for indexing; this is not licensed full-article ingestion.

## HTTP and native tools

All endpoints below are under `/api/v1/library`, use normal workspace access control and return `Cache-Control: no-store`.

| Method / path | Behavior |
| --- | --- |
| `GET /` | Bounded source metadata, counts and pagination. |
| `POST /documents` | Bounded JSON/base64 upload with optional attribution. |
| `GET /search` | Read-only lexical passage retrieval. |
| `GET /documents/{id}` | Source metadata plus twelve passages at a time. |
| `GET /passages/{id}` | One exact retained citation, or 404. |
| `POST /documents/{id}/reindex` | Explicit re-extraction of the retained original. |
| `DELETE /documents/{id}` | Explicit removal of an uploaded source. |
| `POST /synchronize-news` | Rebuild changed retained-news copies without fetching publishers. |

Wiki and Reporter each declare native typed `search_research`, `read_research_document` and `read_research_passage` tools in their own files. Their docstrings explain purpose, selection, limits and source trust. Missing records use native `ToolRejectedError`; storage failures remain operational failures. Document/passages selected in the page use existing private request context. Sibyl discovers the agents through ProtoLink, with delegation still disabled for specialists.

The no-model Wiki dialog runs an explicit native selected-document/passage read and presents excerpts as excerpts. No model reasoning, routing wrapper or answer rewriting is introduced. Uploaded text is private content that may reach the configured model through requested evidence tools; originals are not returned by those tools.

`tests/test_research_library.py` exercises real PDF extraction, exact slices, changed citation IDs, deduplication, news expiry, query syntax, HTTP privacy and native retrieval/rejection. The native evaluation catalog includes imported-source and empty-library cases.

PDF extraction follows the [pypdf text-extraction API and its documented limitations](https://pypdf.readthedocs.io/en/stable/user/extract-text.html).
