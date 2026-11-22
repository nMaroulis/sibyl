import { useState } from 'react';
import { ExternalLink } from 'lucide-react';
import { useResource } from '../lib/hooks';
import { Badge, ErrorState, Loading, Panel, PanelTitle } from './ui';

const PAGE_SIZE = 25;
const FORMS = ['10-K', '10-Q', '8-K', '20-F', '6-K', 'DEF 14A', '4'];

type FilingPage = {
  name: string;
  cik: string;
  archive?: string;
  archives: { id: string; from: string; to: string }[];
  items: { accession: string; filed: string; form: string; url: string }[];
  total: number;
};

/** An explicit SEC request, independent of the equity quote and Demo state. */
export function StockDisclosures({ symbol }: { symbol: string }) {
  const setup = useResource<{ configured: boolean }>('/equities/disclosures/status');
  const [issuer, setIssuer] = useState(symbol);
  const [query, setQuery] = useState({ issuer: '', archive: '', form: '', offset: 0 });
  const parameters = new URLSearchParams({ issuer: query.issuer, offset: String(query.offset) });
  if (query.archive) parameters.set('archive', query.archive);
  if (query.form) parameters.set('form', query.form);
  const filings = useResource<FilingPage>(
    `/equities/disclosures?${parameters}`,
    0,
    !!query.issuer && !!setup.data?.configured,
  );
  const page = filings.data;
  return (
    <Panel>
      <PanelTitle
        title="SEC filings"
        subtitle="Official disclosures and historical filing indices"
        action={<Badge>SEC EDGAR</Badge>}
      />
      {setup.error ? (
        <ErrorState message={setup.error} retry={setup.retry} />
      ) : setup.loading ? (
        <Loading />
      ) : !setup.data?.configured ? (
        <p className="padded footnote">
          Set <code>SIBYL_SEC_CONTACT</code> to your operator email on the backend and restart Sibyl
          to load public SEC filings.
        </p>
      ) : (
        <>
          <form
            className="stock-search"
            onSubmit={(event) => {
              event.preventDefault();
              const value = issuer.trim().toUpperCase();
              if (!value) return;
              if (value === query.issuer && !query.archive && !query.form && query.offset === 0) {
                filings.retry();
              } else {
                setQuery({ issuer: value, archive: '', form: '', offset: 0 });
              }
            }}
          >
            <input
              aria-label="SEC ticker or CIK"
              placeholder="Ticker or CIK"
              required
              maxLength={12}
              value={issuer}
              onChange={(event) => setIssuer(event.target.value)}
            />
            <button type="submit" className="button primary" disabled={filings.loading}>
              Load filings
            </button>
          </form>
          {page && (
            <div className="filter-pills">
              <Badge>
                {page.name} · CIK {page.cik}
              </Badge>
              <select
                aria-label="Filing index"
                value={query.archive}
                disabled={filings.loading}
                onChange={(event) => setQuery({ ...query, archive: event.target.value, offset: 0 })}
              >
                <option value="">Recent filings</option>
                {page.archives.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.from} to {item.to}
                  </option>
                ))}
              </select>
              <select
                aria-label="Filing form"
                value={query.form}
                disabled={filings.loading}
                onChange={(event) => setQuery({ ...query, form: event.target.value, offset: 0 })}
              >
                <option value="">All forms</option>
                {FORMS.map((form) => (
                  <option key={form}>{form}</option>
                ))}
              </select>
            </div>
          )}
          {filings.error ? (
            <ErrorState message={filings.error} retry={filings.retry} />
          ) : filings.loading && query.issuer ? (
            <Loading />
          ) : page ? (
            page.items.length ? (
              <>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Filed</th>
                        <th>Form</th>
                        <th>SEC accession</th>
                      </tr>
                    </thead>
                    <tbody>
                      {page.items.map((item) => (
                        <tr key={item.accession}>
                          <td>{item.filed}</td>
                          <td>{item.form}</td>
                          <td>
                            <a
                              className="text-link"
                              href={item.url}
                              target="_blank"
                              rel="noreferrer"
                            >
                              {item.accession} <ExternalLink size={12} />
                            </a>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {page.total > PAGE_SIZE && (
                  <div className="filter-pills">
                    <button
                      type="button"
                      disabled={!query.offset}
                      onClick={() => setQuery({ ...query, offset: query.offset - PAGE_SIZE })}
                    >
                      Previous
                    </button>
                    <span>
                      {query.offset + 1}–{query.offset + page.items.length} of {page.total}
                    </span>
                    <button
                      type="button"
                      disabled={query.offset + PAGE_SIZE >= page.total}
                      onClick={() => setQuery({ ...query, offset: query.offset + PAGE_SIZE })}
                    >
                      Next
                    </button>
                  </div>
                )}
              </>
            ) : (
              <p className="padded footnote">No filings match this form in the selected index.</p>
            )
          ) : (
            <p className="padded footnote">Load a ticker or CIK to browse its public filings.</p>
          )}
        </>
      )}
    </Panel>
  );
}
