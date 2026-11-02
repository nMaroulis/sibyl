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
4. Search by keyword and choose **All sources**, **My documents** or **Retained news**.
5. Open a result to read its exact passage, then **Read the document** to continue through its retained text.

The library accepts up to 100 uploaded documents, 8 MiB each and 200 MiB of originals in total. PDFs are limited to 100 pages and one million extracted characters. Encrypted PDFs are rejected; scans need OCR before import. Original files are kept locally for reindexing. The reader displays extracted text, not the PDF's original visual layout.

**Synchronize news** updates the search copy from the existing news archive. It does not contact publishers. A background worker also updates this copy. News entries identify their publisher, publication date, original link and retained-excerpt status; they do not imply access to the full article. Expired archive entries disappear from search on the next synchronization.

## Ask about the evidence

Use **Ask Wiki** with a source or passage selected or ask Sibyl to research a topic using your library. Wiki and Reporter have native ProtoLink tools to search sources and read selected documents or passages. Sibyl discovers these capabilities through the existing registry.

Ask for source names, publication dates and passage links. Passage links open the exact retained text in My research. Without an LLM, the reader's Ask action returns source excerpts and setup guidance, without pretending to interpret them.

:::note[Relevance is not confidence]

Search uses SQLite FTS5/BM25 keyword ranking. It does not use embeddings, verify claims or measure the probability that an answer is correct. Documents and news may be historical, incomplete, biased or wrong. A citation establishes what a source says, not its truth.

:::

## Manage and protect your sources

**Reindex** extracts the retained original again. Passages with changed text get different citation IDs; an old changed/deleted passage becomes unavailable rather than pointing silently to different text. **Remove** deletes an uploaded original and its active search entries. News copies follow the news archive's retention policy.

Library data is private workspace content, stored locally with restricted file permissions. It is not separately encrypted like exchange credentials. When you ask an AI agent, retrieved passages can be sent to your configured model provider. Keep API keys, passwords, seed phrases and backup passphrases out of research files. Source text is treated as untrusted evidence, never as agent instructions.

Deleting a source is not secure disk erasure and does not remove copies already retained in investigation reports, exports, backups or model-provider history. Use [encrypted workspace backups](workspace-backups.md) to preserve the library with its source metadata.
