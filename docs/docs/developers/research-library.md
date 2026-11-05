---
title: Research library contracts
description: Bounded ingestion, coherent SQLite retrieval, exact citations and native read-only tools.
---

# Research library contracts

`research_library/` owns ingestion, text extraction and retrieval; its `ResearchLibrary` instance is shared by FastAPI and the existing Wiki/Reporter agent declarations. It does not add an agent router, vector framework or embedding SDK dependency. Optional embeddings use the existing HTTPX and NumPy dependencies in `research_library/semantic/`.

## Persistence and extraction

`research-library.sqlite` stores source metadata, original upload BLOBs, extracted pages and passage/FTS5 rows. Imports publish all rows in one transaction. A content SHA-256 prevents duplicate uploads from overwriting original attribution. Document reads use a coherent transaction across metadata, passage rows and counts.

Text/Markdown must be UTF-8. PDFs use `pypdf` in a disposable child process with a twenty-second parent deadline, CPU limits where supported, page/text/decoded-stream limits and at most two simultaneous extractions. The child does not execute PDF JavaScript, fetch URLs or perform OCR. These are parsing limits, not an OS-independent memory sandbox. Failed/empty/oversized extraction publishes no source.

Passages are exact, overlapping, page-bounded slices: up to 1,600 characters with 160-character overlap. IDs include document ID, ordinal and a text fingerprint. Reindexing replaces the complete search representation; changed passages do not reuse old citation IDs. Removal deletes active entries, not copies in old reports/backups or securely erased storage.

Search tokenizes a bounded query into quoted OR terms, binds SQL parameters and ranks SQLite FTS5 matches with BM25. It returns actual text, source metadata and in-app passage links. Ranking is lexical relevance, not semantic grounding or confidence. FTS5-enabled SQLite is required. Keyword search stays the default and never contacts an embedding provider. Cited web search remains pending.

## Optional local vector space

`SemanticIndex` composes the library, rather than replacing it. `semantic_settings` and `semantic_vectors` live in the same SQLite database and workspace backups. Vectors are normalized little-endian float32, keyed by passage ID and complete text SHA-256. The adapter rejects non-numeric, Boolean, non-finite, zero-direction, excessive or inconsistent vectors. Limits are 4,096 dimensions, 5,000 passages and 64 MiB of vectors; search scans this bounded local index without a vector database.

The Ollama adapter accepts loopback HTTP endpoints only, ignores proxy environment settings and refuses redirects. Only fixed `/api/version`, `/api/tags`, `/api/show` and `/api/embed` paths are used. Locally installed models must advertise embedding capability; reported `remote_host`/`remote_model` fields are rejected before sending passages. Model name, digest, server version and dimension are pinned. Observed identity is checked before and after embedding, but the trusted local server does not provide an atomic name/digest attestation. Responses are bounded to 8 MiB; calls have connection/read deadlines. The native [embedding contract](https://docs.ollama.com/api/embed) receives `truncate: false`, up to 32 exact passages per request. No model pulling, API credentials, startup inference or automatic indexing is introduced. Catalog metadata is defined by Ollama's [API specification](https://github.com/ollama/ollama/blob/main/docs/openapi.yaml).

Explicit UI indexing checkpoints one batch per request. Stop/unmount stops future requests, not the Python thread or current HTTP call. Two semantic operations may run concurrently, with one indexing batch per service instance; completed batches survive restart. Settings use optimistic revisions: reconfiguration/clear invalidates in-flight batches and query results. Transactions recheck revision and current source text before publication; deleted/changed sources are skipped. The final vector count/size is checked within the write transaction. Multiple-worker coordination remains outside the local app's supported deployment.

Semantic search returns the nearest indexed passages by cosine similarity, with stable ID tie-breaking. Hybrid uses reciprocal-rank fusion (`k=60`) over up to 50 keyword and 50 semantic candidates in one coherent database read. It can include keyword matches from unindexed documents. It returns original passage citations, source fingerprints, raw similarity and (for Hybrid) fusion score, plus model identity and actual scoped coverage. It does not calibrate a no-answer threshold, verify truth or infer confidence. Deleted/reindexed/expired sources invalidate their vectors in the same transaction as passage removal. Corrupt or mismatched vector data fails explicitly. Configuration or provider failure never silently substitutes keyword results or Demo data.

Controlled-vector tests establish transport, ranking, isolation and citation contracts; they do not establish empirical relevance for a real embedding model. Broader corpus/model evaluation, calibrated thresholds and hosted embedding providers remain pending.

## Retained news

A supervised worker copies the existing bounded news archive into the same index. It does no publisher HTTP work. Source/date/excerpt labels remain explicit; expired articles are removed on the next sync. A manual sync endpoint provides the same operation. Long retained excerpts are bounded for indexing; this is not licensed full-article ingestion.

## HTTP and native tools

All endpoints below are under `/api/v1/library`, use normal workspace access control and return `Cache-Control: no-store`.

| Method / path | Behavior |
| --- | --- |
| `GET /` | Bounded source metadata, counts and pagination. |
| `POST /documents` | Bounded JSON/base64 upload with optional attribution. |
| `GET /search` | Exact passage retrieval with `method=keyword` (default), `semantic` or `hybrid`. |
| `GET /documents/{id}` | Source metadata plus twelve passages at a time. |
| `GET /passages/{id}` | One exact retained citation, or 404. |
| `POST /documents/{id}/reindex` | Explicit re-extraction of the retained original. |
| `DELETE /documents/{id}` | Explicit removal of an uploaded source. |
| `POST /synchronize-news` | Rebuild changed retained-news copies without fetching publishers. |
| `GET /semantic` | Passive saved model identity, revision, actual per-scope coverage and limits. |
| `POST /semantic/models` | Explicitly list model metadata at a validated loopback endpoint. |
| `POST /semantic/settings` | Revision-checked compatibility probe and new profile; clears vectors. |
| `POST /semantic/index` | Revision-checked batch of at most 32 missing passages. |
| `POST /semantic/clear` | Revision-checked vector removal, retaining configuration. |
| `DELETE /semantic?revision=…` | Disable configuration and remove vectors; retain all sources. |

Wiki and Reporter each declare native typed `search_research`, `research_search_status`, `read_research_document` and `read_research_passage` tools in their own files. Their docstrings explain purpose, selection, limits and source trust. Missing records and semantic setup use native `ToolRejectedError`; storage failures remain operational failures. Document/passages and query/source scope/retrieval method selected in the page use existing private request context. Sibyl discovers the agents through ProtoLink, with delegation still disabled for specialists.

The no-model Wiki dialog runs an explicit native selected-document/passage read or research search and presents excerpts as excerpts. No model reasoning, routing wrapper or answer rewriting is introduced. Uploaded text is private content that may reach the configured model through requested evidence tools; originals are not returned by those tools.

`tests/test_research_library.py` exercises real PDF extraction, exact slices, changed citation IDs, deduplication, news expiry, query syntax, HTTP privacy and native retrieval/rejection. `tests/test_semantic_research.py` covers Ollama HTTP contracts with controlled vectors, rank fusion, coverage, persistence, model changes, concurrent deletion/configuration, bounded storage, invalid responses and native tools. The native evaluation catalog includes imported-source and empty-library cases.

PDF extraction follows the [pypdf text-extraction API and its documented limitations](https://pypdf.readthedocs.io/en/stable/user/extract-text.html).
