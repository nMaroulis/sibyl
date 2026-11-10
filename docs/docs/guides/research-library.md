---
title: Your research library
description: Import private research, search retained news and discuss exact cited passages with the AI team.
---

# Your research library

Open **Research → My research** to bring documents into Sibyl and search them alongside retained publisher excerpts. Search and the source reader work without an AI model.

## Add and find a source

1. Select **Add document** and choose a text-bearing PDF, UTF-8 text file or Markdown file.
2. Optionally enter a title, author/publisher, source URL and publication date. A source URL is attribution; Sibyl never fetches it during import.
3. Import the document. Sibyl extracts text, keeps page numbers and indexes overlapping passages. An identical file returns the existing source without replacing its attribution.
4. Search by keyword (or configure the optional semantic search below) and choose **All sources**, **My documents** or **Retained news**.
5. Open a result to read its exact passage, then **Read the document** to continue through its retained text.

The library accepts up to 100 uploaded documents, 8 MiB each and 200 MiB of originals in total. PDFs are limited to 100 pages and one million extracted characters. Encrypted PDFs are rejected; scans need OCR before import. Original files are kept locally for reindexing. The reader displays extracted text, not the PDF's original visual layout.

**Synchronize news** updates the search copy from the existing news archive. It does not contact publishers. A background worker also updates this copy. News entries identify their publisher, publication date, original link and retained-excerpt status; they do not imply access to the full article. Expired archive entries disappear from search on the next synchronization.

## Optional local semantic search

Expand **Semantic search** in My research. This has its own embedding-model configuration, independent of your chat model. A paid API key or chat LLM is not required.

1. Install and start [Ollama](https://ollama.com/download) on the machine running Sibyl's Python backend. Install an embedding model yourself, for example `ollama pull embeddinggemma`. Sibyl does not download it automatically.
2. Keep the default loopback endpoint, or enter another local HTTP port. **Check installed models** lists model names; **Check & save model** verifies embedding capability with a compatibility phrase. Chat-only models and models advertised as cloud/remote are rejected.
3. Select documents, retained news or all sources and **Index passages**. Only this explicit action sends retained passages to local Ollama. Progress counts actual passages, including any missing from a partial index. News synchronization and document imports do not automatically embed text.
4. Use **Stop after this batch** to stop future batches. Completed batches stay saved; **Continue indexing** processes remaining passages. Leaving the page also stops future batches after the active request. There is no background indexing job to restart.
5. Choose **Semantic** or **Hybrid** next to the search field. Semantic searches indexed passages; Hybrid also includes keyword matches from unindexed passages. A partial index can miss relevant sources. Scores are relevance, not confidence.

Each batch contains at most 32 passages. The vector index is bounded to 5,000 passages and 64 MiB. Indexing never silently truncates a passage to fit a model; an input/context error is reported and earlier successful batches remain available. Use a model with sufficient input capacity.

Saving configuration again clears vectors. A changed model digest, embedding dimension or Ollama version requires checking/saving the model again and rebuilding; this prevents mixing observed vector spaces. **Clear index** keeps the configuration and sources; **Disable semantic search** also removes the configuration. Keyword search stays available. Reindexing a document invalidates its vectors, even if the text is unchanged; removed or expired sources leave no active vector entries.

:::note[Local means the backend's machine]

Only loopback HTTP endpoints are supported. In a container, loopback refers to the container; an Ollama server on the host needs a separately supported deployment arrangement. The local Ollama server is trusted: Sibyl rejects advertised remote execution and checks reported identity before and after each call, but cannot independently attest how that server runs a model. Broader model-specific retrieval-quality evaluation remains pending. The hosted options below are separate from this local path.

:::

## Optional hosted semantic search

In **Research → My research → Semantic search**, choose the **OpenAI** or **Mistral** card. This is independent of the assistant's model/provider. It does not require an active chat LLM.

1. Choose a reviewed embedding preset: OpenAI `text-embedding-3-small`, `text-embedding-3-large` or `text-embedding-ada-002`, or Mistral `mistral-embed`.
2. Enter a separate embedding API key. Sibyl encrypts it in the local backend vault; it never returns the key to the UI or gives it to agents. Chat/environment keys are not borrowed. **API key saved → Edit key** replaces an existing hidden credential.
3. Read the hosted-processing notice and explicitly allow text processing. **Check & save hosted model** sends only a fixed compatibility phrase; it can incur a small provider charge. A failed check preserves the previous setup/index.
4. Select which retained sources to index and choose **Index passages**. This sends those text passages to the saved provider. Later **Semantic/Hybrid** searches send query text too, including agent searches and retrieval-quality evaluations. Imports and news synchronization do not automatically embed documents.

:::note[Text leaves the backend]

Hosted calls use the provider's official HTTPS API, and its charges/data policies apply. Your original uploads and vector storage remain local. This permission covers selected passage indexing and future semantic/hybrid queries until you disable or change the configuration. **Disable semantic search** clears vectors/configuration and removes its active saved key. It cannot recall requests already sent or copies kept by a provider.

:::

If the optional SDK is missing, the UI shows the install command. Source installs can use `uv sync --extra openai`; installed packages can add the existing `sibyl[openai]` extra. The same OpenAI-compatible SDK serves both providers; no extra Mistral SDK is required. Restart the backend afterward. Provider account/model access still needs checking with your own key.

Saving any new model/provider resets the vector index, preserving sources and keyword search. Hosted profiles pin the official provider, observed model name and dimensions, **not a provider weight digest**. Same-name/same-dimension hosted model changes cannot be detected independently; rebuild the index if needed. Incompatible dimensions, invalid batches, timeouts and provider errors fail visibly without silently switching to local, keyword or Demo results. Broader real-model quality evaluation, additional hosted providers and live acceptance remain pending.

## Ask about the evidence

Use **Ask Wiki** with a source or passage selected or ask Sibyl to research a topic using your library. Wiki and Reporter have native ProtoLink tools to search sources and read selected documents or passages. Sibyl discovers these capabilities through the existing registry.

Ask for source names, publication dates and passage links. Passage links open the exact retained text in My research. Without an LLM, Ask Wiki returns selected source excerpts or search results and setup guidance, without pretending to interpret them.

:::note[Relevance is not confidence]

Keyword search uses SQLite FTS5/BM25 ranking. Semantic search compares the configured model’s vectors stored locally; Hybrid combines the two rankings. None verifies claims or measures the probability that an answer is correct. Semantic search returns nearest indexed passages even when the library contains no useful answer; inspect the actual text. Documents and news may be historical, incomplete, biased or wrong. A citation establishes what a source says, not its truth.

:::

## Manage and protect your sources

**Reindex** extracts the retained original again. Passages with changed text get different citation IDs; an old changed/deleted passage becomes unavailable rather than pointing silently to different text. **Remove** deletes an uploaded original and its active search entries. News copies follow the news archive's retention policy.

Library data, including saved vectors, is private workspace content, stored locally with restricted file permissions. It is not separately encrypted like exchange credentials. When you ask an AI agent, retrieved passages can be sent to your configured chat model provider. Consented hosted embeddings separately send selected passage text and semantic/hybrid queries to the embedding provider; the original files and stored vectors remain local. Keep API keys, passwords, seed phrases and backup passphrases out of research files. Source text is treated as untrusted evidence, never as agent instructions.

Deleting a source is not secure disk erasure and does not remove copies already retained in investigation reports, exports, backups or model-provider history. Use [encrypted workspace backups](workspace-backups.md) to preserve the library with its source metadata.

## Evaluate retrieval with your questions

Expand **Retrieval quality lab** in My research. Open an actual source, use **Copy passage ID**, and label the passages you judge relevant to a question. Save a titled suite with up to eight distinct questions and up to ten relevant passages per question; choose uploads, retained news or all sources. Labels come from you, not an LLM. Include representative paraphrases and enough relevant passages to avoid penalizing good matches just because your judgments were incomplete.

Select **Keyword**, or also **Semantic/Hybrid** after explicitly configuring and indexing an embedding model. Choose a top-1/3/5/10 cutoff and **Run comparison**. One query/method runs per background iteration. No model is downloaded. Hosted semantic/hybrid comparisons send query text to the selected provider under saved permission and may incur charges; keyword comparisons do not. Keyword needs no model. Only one evaluation is active at once.

Completed reports show macro-averaged precision, recall, reciprocal rank, binary nDCG, hit rate and observed latency. Precision divides by the chosen cutoff even if fewer results are returned; recall divides by all labeled relevant passages. Empty results score zero. Open **Inspect query rankings and citations** for the exact ranked passages, then export full JSON evidence or ask Wiki/Reporter to explain it.

Every run pins the corpus and optional embedding-index fingerprint and records partial coverage. Changing a source or index during a run fails the comparison instead of mixing evidence. **Stop evaluation** discards a late result from an admitted query; a backend restart marks unfinished runs interrupted, without replaying them. Start another run explicitly for fresh evidence. Partial/failed runs retain their evidence but have no full aggregate comparison.

Keep up to 20 suites and 100 reports. **Delete suite & reports** removes that suite's stored judgments and evaluations, preserving the source library. Removing a source does not erase excerpts already retained in these reports. These workspace records are private local data, not separately encrypted credentials.

This lab measures raw retrieval against your judgments and does not grade factual answers or prove broad model quality. Separately, [semantic cutoff calibration](search-calibration.md) fits a top-one abstention policy with distinct fit/held-out questions and explicit activation; ranking comparisons stay unfiltered.
