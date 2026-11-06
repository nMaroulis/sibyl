import { number } from '../lib/api';

export type Diversification = {
  status: string;
  assets: number;
  hhi: number | null;
  effective_assets: number | null;
  largest_pct: number | null;
  largest_asset: string | null;
  top_three_pct: number | null;
  note: string;
};

/** No whole-portfolio score is shown for incomplete valuation coverage. */
export function PortfolioDiversification({ data }: { data?: Diversification }) {
  if (!data) return null;
  return (
    <details className="portfolio-diversification">
      <summary>
        Diversification{' '}
        <span>
          {data.status === 'observed'
            ? `${number(data.effective_assets!, 1)} effective assets`
            : 'Unavailable'}
        </span>
      </summary>
      {data.status === 'observed' ? (
        <div className="diversification-grid">
          <div>
            <small>HHI · 0–100</small>
            <strong>{number(data.hhi!, 1)}</strong>
          </div>
          <div>
            <small>Largest · {data.largest_asset}</small>
            <strong>{number(data.largest_pct!, 1)}%</strong>
          </div>
          <div>
            <small>Top three assets</small>
            <strong>{number(data.top_three_pct!, 1)}%</strong>
          </div>
        </div>
      ) : (
        <p className="footnote">
          A complete positive portfolio valuation is needed. Missing accounts or prices prevent a
          whole-portfolio concentration score.
        </p>
      )}
      <p className="footnote">
        {data.note} HHI is the sum of squared value weights × 100; effective assets = 100 / HHI.
        Lower HHI means more evenly spread value, without implying lower investment risk.
      </p>
    </details>
  );
}
