import { useState, type FormEvent } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  BookOpen,
  FileText,
  Upload,
  Search,
  RefreshCw,
  Trash2,
  ExternalLink,
  X,
} from 'lucide-react';
import { api, post, refresh } from '../lib/api';
import { useResource } from '../lib/hooks';
import { AgentButton } from './agents';
import { LibraryEvaluations } from './library-evaluations';
import { LibrarySemantic } from './library-semantic';
import type { SemanticStatus } from '../lib/semantic-types';
import { Badge, Empty, ErrorState, Loading, Modal, Panel, PanelTitle, useToast } from './ui';

type Source = {
  id: string;
  title: string;
  kind: 'document' | 'news';
  publisher: string;
  source_url: string;
  published_at: string;
  imported_at: string;
  indexed_at: string;
  extraction: string;
  pages: number;
  characters: number;
  fingerprint: string;
};
type Passage = {
  kind?: string;
  id: string;
  document_id: string;
  ordinal: number;
  page: number;
  text: string;
  url: string;
  source?: Source;
};
type Document = Source & { passages: Passage[]; total_passages: number; offset: number };
type Catalog = { items: Source[]; counts: Record<string, number> };
type Matches = {
  items: Passage[];
  note: string;
  retrieval: string;
  semantic?: { model: string; coverage: { indexed: number; total: number; partial: boolean } };
};
const date = (value: string) =>
  value
    ? new Date(value).toLocaleDateString('en-GB', {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
      })
    : 'Date not supplied';

/** Imported files and retained news share one attributable, exact-passage reader. */
export function ResearchLibrary() {
  const [params, setParams] = useSearchParams();
  const [draft, setDraft] = useState('');
  const [query, setQuery] = useState('');
  const [kind, setKind] = useState<'all' | 'document' | 'news'>('all');
  const [method, setMethod] = useState<'keyword' | 'semantic' | 'hybrid'>('keyword');
  const semantic = useResource<SemanticStatus>('/library/semantic', 5000);
  const [importing, setImporting] = useState(false);
  const [remove, setRemove] = useState<Source>();
  const [busy, setBusy] = useState('');
  const catalog = useResource<Catalog>('/library?kind=document');
  const matches = useResource<Matches>(
    `/library/search?query=${encodeURIComponent(query)}&kind=${kind}&method=${method}`,
    0,
    !!query,
  );
  const document = params.get('document') ?? '';
  const passage = params.get('passage') ?? '';
  const toast = useToast();
  const open = (id: string, selectedPassage = '') =>
    setParams((previous) => {
      const next = new URLSearchParams(previous);
      next.set('tab', 'library');
      next.set('document', id);
      if (selectedPassage) next.set('passage', selectedPassage);
      else next.delete('passage');
      return next;
    });
  const action = async (id: string, operation: 'reindex' | 'delete') => {
    setBusy(id);
    try {
      if (operation === 'delete') {
        await api(`/library/documents/${id}`, { method: 'DELETE' });
        if (document === id)
          setParams((previous) => {
            const next = new URLSearchParams(previous);
            next.delete('document');
            next.delete('passage');
            return next;
          });
        toast('Source and its indexed passages removed.');
        setRemove(undefined);
      } else {
        await post(`/library/documents/${id}/reindex`);
        toast('Source reindexed from its retained original.');
      }
      refresh();
    } catch (error) {
      toast((error as Error).message, true);
    } finally {
      setBusy('');
    }
  };
  return (
    <div className="research-library">
      <Panel>
        <PanelTitle
          title="Your research, with receipts"
          subtitle="Private documents · retained news · exact passages"
          action={
            <AgentButton
              module="wiki"
              context={{
                library_document_id: document || undefined,
                library_passage_id: passage || undefined,
                library_query: query || undefined,
                library_source_type: kind,
                library_search_method: method,
              }}
            />
          }
        />
        <div className="library-toolbar">
          <form
            className="library-search"
            onSubmit={(event) => {
              event.preventDefault();
              setQuery(draft.trim());
            }}
          >
            <label className="library-query">
              <Search size={17} />
              <input
                aria-label="Search research library"
                placeholder="Find a topic, a claim, a connection…"
                value={draft}
                maxLength={300}
                onChange={(event) => setDraft(event.target.value)}
              />
            </label>
            <select
              aria-label="Research source type"
              value={kind}
              onChange={(event) => setKind(event.target.value as typeof kind)}
            >
              <option value="all">All sources</option>
              <option value="document">My documents</option>
              <option value="news">Retained news</option>
            </select>
            <select
              aria-label="Research search method"
              value={method}
              onChange={(event) => setMethod(event.target.value as typeof method)}
            >
              <option value="keyword">Keyword</option>
              <option value="semantic">Semantic</option>
              <option value="hybrid">Hybrid · keywords + meaning</option>
            </select>
            <button className="button primary" type="submit" disabled={!draft.trim()}>
              Search
            </button>
          </form>
          <button className="button" onClick={() => setImporting(true)}>
            <Upload size={16} /> Add document
          </button>
        </div>
        <p className="footnote">
          Keyword search works without an LLM. Agents can retrieve passages from these sources when
          you ask. Import research you are comfortable sharing with your configured model; keep
          credentials out of documents.
        </p>
      </Panel>
      <LibrarySemantic state={semantic} retry={semantic.retry} />
      <LibraryEvaluations
        semanticReady={!!semantic.data?.configured && !!semantic.data.coverage.all.indexed}
      />
      {query && (
        <Panel>
          <PanelTitle
            title={`Results for “${query}”`}
            subtitle={
              method === 'keyword'
                ? 'Keyword matches, with exact retained text'
                : method === 'semantic'
                  ? 'Meaning-based matches, with exact retained text'
                  : 'Combined keyword and meaning-based matches'
            }
            action={
              <button
                className="button small"
                onClick={() => {
                  setQuery('');
                  setDraft('');
                }}
              >
                <X size={14} /> Clear
              </button>
            }
          />
          {matches.error ? (
            <ErrorState message={matches.error} retry={matches.retry} />
          ) : matches.loading ? (
            <Loading />
          ) : !matches.data?.items.length ? (
            <Empty title="No matching passages">
              Try another term, import a source, or synchronize the retained news archive. Semantic
              searches also need indexed passages. An empty match does not establish that a claim is
              false.
            </Empty>
          ) : (
            <div className="library-results">
              {matches.data.items.map((item) => (
                <button
                  className="library-match"
                  key={item.id}
                  onClick={() => open(item.document_id, item.id)}
                >
                  <div>
                    <Badge>{item.kind === 'news' ? 'News excerpt' : 'Document'}</Badge>
                    <span>
                      {item.source?.publisher || 'Imported document'} ·{' '}
                      {date(item.source?.published_at ?? '')}
                    </span>
                    <span>Page {item.page}</span>
                  </div>
                  <h3>{item.source?.title}</h3>
                  <p>{item.text}</p>
                  <span className="text-link">Read exact passage →</span>
                </button>
              ))}
            </div>
          )}
          {matches.data?.semantic && (
            <p className="footnote">
              {matches.data.semantic.model} · {matches.data.semantic.coverage.indexed} /{' '}
              {matches.data.semantic.coverage.total} passages indexed for this source scope
              {matches.data.semantic.coverage.partial ? ' · partial semantic coverage' : ''}.
            </p>
          )}
          <p className="footnote">
            Relevance is not confidence or fact verification. Publisher excerpts and uploaded
            research may be historical, incomplete or incorrect.
          </p>
        </Panel>
      )}
      {document && (
        <DocumentReader
          key={`${document}:${passage}`}
          identity={document}
          selectedPassage={passage}
          onReadDocument={() => open(document)}
          onClose={() =>
            setParams((previous) => {
              const next = new URLSearchParams(previous);
              next.delete('document');
              next.delete('passage');
              return next;
            })
          }
        />
      )}
      <Panel>
        <PanelTitle
          title="Your sources"
          subtitle={`${catalog.data?.counts.document ?? 0} uploaded document${catalog.data?.counts.document === 1 ? '' : 's'}`}
          action={
            <button
              className="button small"
              disabled={!!busy}
              onClick={async () => {
                setBusy('sync');
                try {
                  const result = await post<{ indexed_news: number }>('/library/synchronize-news');
                  toast(
                    `${result.indexed_news} retained news sources indexed. No publishers were fetched.`,
                  );
                  refresh();
                } catch (error) {
                  toast((error as Error).message, true);
                } finally {
                  setBusy('');
                }
              }}
            >
              <RefreshCw size={14} /> Synchronize news
            </button>
          }
        />
        {catalog.error ? (
          <ErrorState message={catalog.error} retry={catalog.retry} />
        ) : catalog.loading ? (
          <Loading />
        ) : !catalog.data?.items.length ? (
          <Empty title="Bring your own research">
            Add a PDF, Markdown or text document. Retained publisher excerpts also become searchable
            as the archive is indexed.
          </Empty>
        ) : (
          <div className="library-source-grid">
            {catalog.data.items.map((source) => (
              <article
                className={`library-source ${document === source.id ? 'is-selected' : ''}`}
                key={source.id}
              >
                <button className="library-source-open" onClick={() => open(source.id)}>
                  <FileText size={23} />
                  <h3>{source.title}</h3>
                  <p>
                    {source.publisher || 'Private document'} · {source.pages} page
                    {source.pages === 1 ? '' : 's'}
                  </p>
                  <small>Added {date(source.imported_at)}</small>
                </button>
                <div className="library-source-actions">
                  <button disabled={!!busy} onClick={() => action(source.id, 'reindex')}>
                    <RefreshCw size={14} /> Reindex
                  </button>
                  <button disabled={!!busy} onClick={() => setRemove(source)}>
                    <Trash2 size={14} /> Remove
                  </button>
                </div>
              </article>
            ))}
          </div>
        )}
        <p className="footnote">
          PDF text extraction supports up to 100 pages and 8 MiB per file. Scans need OCR first. The
          library retains originals for reindexing; publisher news follows the archive's retention
          policy. Local or consented hosted semantic search is optional; cited web search remains
          pending.
        </p>
      </Panel>
      {importing && (
        <ImportDocument
          onClose={() => setImporting(false)}
          onImported={(id) => {
            setImporting(false);
            refresh();
            open(id);
          }}
        />
      )}
      {remove && (
        <Modal title="Remove this source?" onClose={() => !busy && setRemove(undefined)}>
          <p>
            Remove “{remove.title}”, its original file and searchable passages. Existing report
            exports retain their own evidence; links to removed passages will become unavailable.
          </p>
          <div className="dialog-actions">
            <button className="button" disabled={!!busy} onClick={() => setRemove(undefined)}>
              Keep source
            </button>
            <button
              className="button primary"
              disabled={!!busy}
              onClick={() => action(remove.id, 'delete')}
            >
              Remove source
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}

function DocumentReader({
  identity,
  selectedPassage,
  onReadDocument,
  onClose,
}: {
  identity: string;
  selectedPassage: string;
  onReadDocument: () => void;
  onClose: () => void;
}) {
  const [offset, setOffset] = useState(0);
  const toast = useToast();
  const result = useResource<Document>(`/library/documents/${identity}?offset=${offset}`);
  const exact = useResource<Passage>(`/library/passages/${selectedPassage}`, 0, !!selectedPassage);
  const data = result.data;
  const showDocument = !selectedPassage;
  const parts = showDocument ? data?.passages : exact.data ? [exact.data] : [];
  return (
    <Panel className="library-reader">
      <PanelTitle
        title={data?.title ?? 'Source reader'}
        subtitle={
          data
            ? `${data.publisher || 'Private source'} · ${date(data.published_at)} · ${data.extraction}`
            : 'Loading retained evidence'
        }
        action={
          <>
            <button className="icon-button" aria-label="Close source reader" onClick={onClose}>
              <X size={18} />
            </button>
          </>
        }
      />
      {result.error ? (
        <ErrorState message={result.error} retry={result.retry} />
      ) : result.loading ? (
        <Loading />
      ) : (
        <>
          <div className="library-reader-meta">
            <Badge>{data?.kind === 'news' ? 'Retained news excerpt' : 'Uploaded document'}</Badge>
            <span>Indexed {date(data?.indexed_at ?? '')}</span>
            {data?.source_url && /^https?:\/\//.test(data.source_url) && (
              <a className="text-link" href={data.source_url} target="_blank" rel="noreferrer">
                Original source <ExternalLink size={12} />
              </a>
            )}
          </div>
          {!showDocument && (
            <button className="button small" onClick={onReadDocument}>
              <BookOpen size={14} /> Read the document
            </button>
          )}
          {exact.error && !showDocument ? (
            <ErrorState message={exact.error} retry={exact.retry} />
          ) : (
            <div className="library-passages">
              {parts?.map((part) => (
                <section key={part.id}>
                  <div>
                    <Badge>Page {part.page}</Badge>
                    <span>Passage {part.ordinal + 1}</span>
                  </div>
                  <p>{part.text}</p>
                  <small>{part.id}</small>
                  <button
                    className="text-button"
                    onClick={() =>
                      void navigator.clipboard
                        .writeText(part.id)
                        .then(() => toast('Passage ID copied.'))
                        .catch(() => toast('Select and copy the passage ID shown above.'))
                    }
                  >
                    Copy passage ID
                  </button>
                </section>
              ))}
            </div>
          )}
          {showDocument && (
            <div className="library-pagination">
              <button
                className="button small"
                disabled={!offset}
                onClick={() => setOffset(Math.max(0, offset - 12))}
              >
                Previous passages
              </button>
              <span>
                {offset + 1}–{Math.min(offset + 12, data?.total_passages ?? 0)} of{' '}
                {data?.total_passages}
              </span>
              <button
                className="button small"
                disabled={offset + 12 >= (data?.total_passages ?? 0)}
                onClick={() => setOffset(offset + 12)}
              >
                Next passages
              </button>
            </div>
          )}
        </>
      )}
    </Panel>
  );
}

function ImportDocument({
  onClose,
  onImported,
}: {
  onClose: () => void;
  onImported: (id: string) => void;
}) {
  const [file, setFile] = useState<File>();
  const [title, setTitle] = useState('');
  const [publisher, setPublisher] = useState('');
  const [url, setUrl] = useState('');
  const [publishedAt, setPublishedAt] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const toast = useToast();
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!file) return;
    if (file.size > 8 * 1024 * 1024) {
      setError('Choose a file up to 8 MiB.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      const data = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result).split(',')[1]);
        reader.onerror = () => reject(new Error('Could not read this file.'));
        reader.readAsDataURL(file);
      });
      const result = await post<Document & { duplicate: boolean }>('/library/documents', {
        filename: file.name,
        data_base64: data,
        title,
        publisher,
        source_url: url,
        published_at: publishedAt || null,
      });
      toast(
        result.duplicate
          ? 'This document is already in your library.'
          : 'Document imported and indexed.',
      );
      onImported(result.id);
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal title="Add a research source" onClose={() => !busy && onClose()}>
      <form onSubmit={submit} className="workspace-form">
        <label>
          Document
          <input
            required
            type="file"
            accept=".pdf,.md,.markdown,.txt"
            onChange={(event) => setFile(event.target.files?.[0])}
          />
        </label>
        <label>
          Title
          <input
            value={title}
            maxLength={200}
            placeholder={file?.name || 'Use the filename'}
            onChange={(event) => setTitle(event.target.value)}
          />
        </label>
        <details>
          <summary>Source information</summary>
          <label>
            Publisher or author
            <input
              value={publisher}
              maxLength={160}
              onChange={(event) => setPublisher(event.target.value)}
            />
          </label>
          <label>
            Source URL
            <input
              type="url"
              value={url}
              maxLength={2000}
              onChange={(event) => setUrl(event.target.value)}
            />
          </label>
          <label>
            Publication date
            <input
              type="date"
              value={publishedAt}
              onChange={(event) => setPublishedAt(event.target.value)}
            />
          </label>
        </details>
        <p className="footnote">
          Files stay in this workspace. Retrieved passages can be sent to your configured AI
          provider when you ask an agent. Text extraction does not verify a document's claims.
        </p>
        {error && (
          <p role="alert" className="form-error">
            {error}
          </p>
        )}
        <button className="button primary" type="submit" disabled={!file || busy}>
          {busy ? 'Extracting and indexing…' : 'Add document'}
        </button>
      </form>
    </Modal>
  );
}
