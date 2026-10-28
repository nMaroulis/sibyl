import {
  Activity,
  ArrowUpRight,
  BarChart3,
  CircleHelp,
  Download,
  Layers,
  Shield,
  TrendingUp,
} from 'lucide-react';
import { exportCSV, number } from '../../lib/api';
import type { Analysis, MarketStatistics as Statistics } from '../../lib/types';
import { Badge, DataNote, Panel, PanelTitle } from '../ui';

type Metric = [
  key: string,
  label: string,
  unit: 'price' | '%' | 'ratio' | 'multiple' | 'volume' | 'number',
  description: string,
];
type Group = {
  key: 'returns' | 'trend' | 'momentum' | 'volatility' | 'risk' | 'volume' | 'levels';
  title: string;
  icon: typeof Activity;
  metrics: Metric[];
};
const groups: Group[] = [
  {
    key: 'returns',
    title: 'Returns & distribution',
    icon: ArrowUpRight,
    metrics: [
      [
        'sample_pct',
        'Sample return',
        '%',
        'First to last close in the consecutive analysis sample. Excludes fees.',
      ],
      ['bar1_pct', 'Last candle', '%', 'Close-to-close return over one interval.'],
      [
        'bar5_pct',
        '5-candle return',
        '%',
        'Close-to-close return across five intervals, not five calendar days.',
      ],
      ['bar20_pct', '20-candle return', '%', 'Close-to-close return across twenty intervals.'],
      ['bar60_pct', '60-candle return', '%', 'Requires at least 61 consecutive closes.'],
      [
        'positive_pct',
        'Positive candles',
        '%',
        'Share of close-to-close returns strictly greater than zero.',
      ],
      ['mean_pct', 'Mean candle return', '%', 'Arithmetic mean of simple close returns.'],
      ['median_pct', 'Median candle return', '%', 'Median of simple close returns.'],
      ['best_pct', 'Best candle', '%', 'Largest observed close-to-close return.'],
      ['worst_pct', 'Worst candle', '%', 'Smallest observed close-to-close return.'],
    ],
  },
  {
    key: 'trend',
    title: 'Trend',
    icon: TrendingUp,
    metrics: [
      [
        'ema9',
        'EMA · 9',
        'price',
        'Exponential close mean, span 9; adjust=False, initialized at the first close.',
      ],
      ['ema21', 'EMA · 21', 'price', 'Exponential close mean, span 21.'],
      ['sma20', 'SMA · 20', 'price', 'Mean of the last 20 closes.'],
      ['sma50', 'SMA · 50', 'price', 'Mean of the last 50 closes.'],
      [
        'sma200',
        'SMA · 200',
        'price',
        'Mean of the last 200 closes; load more observations if blank.',
      ],
      [
        'distance_sma50_pct',
        'Distance to SMA 50',
        '%',
        'Current close / SMA 50 minus one. Positive means above the average.',
      ],
      [
        'adx14',
        'ADX · 14',
        'number',
        'Wilder-style directional strength, shown after 28 candles. Above 25 often indicates a stronger trend; it does not indicate direction.',
      ],
    ],
  },
  {
    key: 'momentum',
    title: 'Momentum',
    icon: Activity,
    metrics: [
      [
        'rsi14',
        'RSI · 14',
        'number',
        'Wilder-style RSI. Above 70 is conventionally overbought, below 30 oversold; either can persist. Flat closes give 50.',
      ],
      ['macd', 'MACD · 12 / 26', 'price', 'EMA 12 minus EMA 26; displayed after 35 candles.'],
      ['macd_signal', 'MACD signal · 9', 'price', 'EMA 9 of the MACD line.'],
      [
        'macd_histogram',
        'MACD histogram',
        'price',
        'MACD minus its signal. Positive means above the signal.',
      ],
      ['roc10_pct', 'Rate of change · 10', '%', 'Close-to-close return across ten intervals.'],
      [
        'stochastic_k14',
        'Stochastic %K · 14',
        'number',
        'Close position within the last 14 candles’ high-low range, from 0 to 100. Undefined for a zero range.',
      ],
      ['stochastic_d3', 'Stochastic %D · 3', 'number', 'Three-candle mean of stochastic %K.'],
    ],
  },
  {
    key: 'volatility',
    title: 'Volatility',
    icon: BarChart3,
    metrics: [
      [
        'annualized_pct',
        'Annualized volatility',
        '%',
        'Sample standard deviation of simple candle returns × √(365 × 86400 / interval seconds). Short intraday samples can annualize to extreme values.',
      ],
      [
        'period_pct',
        'Candle volatility',
        '%',
        'Sample standard deviation of close-to-close returns; no annualization.',
      ],
      [
        'atr14',
        'ATR · 14',
        'price',
        'Wilder-style smoothed true range over 14 intervals; a size measure, not direction.',
      ],
      ['atr_pct', 'ATR / price', '%', 'ATR 14 as a percentage of the latest close.'],
      [
        'bollinger_width_pct',
        'Bollinger width',
        '%',
        'Upper minus lower band / SMA 20 × 100. Bands are SMA 20 ± two sample standard deviations.',
      ],
      [
        'bollinger_percent_b',
        'Bollinger %B',
        'ratio',
        '0 at the lower band, 1 at the upper. Can be outside this range. Undefined for zero-width bands.',
      ],
      [
        'downside_annualized_pct',
        'Downside deviation · ann.',
        '%',
        'Root mean square of min(return, 0) over all sample returns, annualized. Zero target return.',
      ],
    ],
  },
  {
    key: 'risk',
    title: 'Historical risk',
    icon: Shield,
    metrics: [
      [
        'max_drawdown_pct',
        'Maximum drawdown',
        '%',
        'Largest peak-to-trough decline of observed closes within this sample, shown as a positive loss. Not an all-time drawdown.',
      ],
      [
        'current_drawdown_pct',
        'Drawdown from sample peak',
        '%',
        'Current close below the highest closing price in this sample, shown as a positive loss.',
      ],
      [
        'sharpe',
        'Sharpe · zero rate',
        'ratio',
        'Mean simple return / sample standard deviation × √periods per year. Undefined when volatility is zero. No fees or risk-free return.',
      ],
      [
        'sortino',
        'Sortino · zero target',
        'ratio',
        'Mean simple return / root mean square downside return × √periods per year. Undefined without downside.',
      ],
      [
        'var95_pct',
        'Historical VaR · 95%',
        '%',
        'Nonnegative loss at the empirical 5th percentile of simple returns (linear interpolation). One-candle horizon; at least 20 returns. Not a maximum possible loss.',
      ],
      [
        'expected_shortfall95_pct',
        'Expected shortfall · 95%',
        '%',
        'Nonnegative mean loss among returns at or below the 5th percentile. One-candle horizon, descriptive rather than predictive.',
      ],
    ],
  },
  {
    key: 'volume',
    title: 'Volume & flow',
    icon: Layers,
    metrics: [
      [
        'last',
        'Latest base volume',
        'volume',
        'Provider-reported base-asset volume for the latest closed candle; not quote turnover or order-book liquidity.',
      ],
      ['mean20', 'Mean volume · 20', 'volume', 'Mean of the latest 20 candles’ base volumes.'],
      [
        'relative20',
        'Relative volume',
        'multiple',
        'Latest volume / mean of the preceding 20 candles, excluding the latest. Undefined if that mean is zero.',
      ],
      [
        'cmf20',
        'Chaikin money flow · 20',
        'ratio',
        'Sum of [(2 × close − high − low) / (high − low)] × volume / total volume over 20 candles. Zero-range candles contribute zero.',
      ],
      [
        'vwap20',
        'Rolling VWAP · 20',
        'price',
        'Volume-weighted typical price (high + low + close) / 3 over 20 candles. This is a candle approximation, not tick or session VWAP.',
      ],
      [
        'distance_vwap20_pct',
        'Distance to VWAP',
        '%',
        'Latest close / rolling 20-candle VWAP minus one.',
      ],
      [
        'obv_change20',
        'OBV change · 20',
        'volume',
        'Sum of signed base volume over the last 20 close changes. Unchanged closes contribute zero. Not lifetime OBV.',
      ],
    ],
  },
  {
    key: 'levels',
    title: 'Price references',
    icon: Layers,
    metrics: [
      [
        'sample_high',
        'Sample high',
        'price',
        'Highest candle high in the consecutive analysis sample.',
      ],
      [
        'sample_low',
        'Sample low',
        'price',
        'Lowest candle low in the consecutive analysis sample.',
      ],
      [
        'prior_high20',
        'Prior 20-candle high',
        'price',
        'Highest high of the preceding 20 candles, excluding the latest. A reference, not a confirmed resistance level.',
      ],
      [
        'prior_low20',
        'Prior 20-candle low',
        'price',
        'Lowest low of the preceding 20 candles, excluding the latest. A reference, not a confirmed support level.',
      ],
      [
        'range_position_pct',
        'Position in sample range',
        '%',
        'Latest close’s position from sample low (0%) to sample high (100%).',
      ],
      [
        'distance_high_pct',
        'Distance from sample high',
        '%',
        'Latest close / highest sample high minus one.',
      ],
      [
        'distance_low_pct',
        'Distance from sample low',
        '%',
        'Latest close / lowest sample low minus one.',
      ],
      [
        'pivot',
        'Previous-candle pivot',
        'price',
        'P = (previous high + low + close) / 3. Based on the selected candle interval, not necessarily a daily session.',
      ],
      [
        'r1',
        'Pivot R1',
        'price',
        '2 × P − previous low. Mechanical reference, not a predicted turning point.',
      ],
      ['s1', 'Pivot S1', 'price', '2 × P − previous high.'],
      ['r2', 'Pivot R2', 'price', 'P + previous high − previous low.'],
      ['s2', 'Pivot S2', 'price', 'P − previous high + previous low.'],
    ],
  },
];

function format(value: number | null | undefined, unit: Metric[2], quote: string) {
  if (value == null || !Number.isFinite(value)) return '—';
  const digits =
    unit === 'price' && value !== 0
      ? Math.min(12, Math.max(2, 3 - Math.floor(Math.log10(Math.abs(value)))))
      : unit === 'ratio'
        ? 3
        : 2;
  return `${number(Math.abs(value) < 0.5 * 10 ** -digits ? 0 : value, digits)}${unit === '%' ? '%' : unit === 'price' || unit === 'volume' ? ` ${quote}` : unit === 'multiple' ? '×' : ''}`;
}

/** An explainable directional score with risk kept separate from bullishness. */
export function TechnicalAssessment({ data }: { data: Analysis }) {
  const s = data.statistics,
    a = s.assessment;
  const tone = a.label === 'Bullish' ? 'lime' : a.label === 'Bearish' ? 'rose' : 'neutral';
  const rsi = s.momentum.rsi14;
  return (
    <Panel className="technical-assessment">
      <PanelTitle
        title="Technical bias"
        subtitle={`${data.timeframe} candles · not a trade signal`}
      />
      <div className="market-score">
        <div className={`market-score-value ${a.label.toLowerCase()}`}>
          <strong>{a.score ?? '—'}</strong>
          <span>/ 100</span>
        </div>
        <Badge tone={tone}>{a.label}</Badge>
        <div className="market-score-track" aria-hidden="true">
          <span style={{ left: `${a.score ?? 50}%`, opacity: a.score == null ? 0 : 1 }} />
        </div>
        <div className="market-score-scale">
          <span>Bearish</span>
          <span>Mixed</span>
          <span>Bullish</span>
        </div>
        <p>
          {a.reason ||
            'How the current trend, momentum and volume readings align. Higher means more bullish, not less risky.'}
        </p>
        {rsi != null && (rsi >= 70 || rsi <= 30) && (
          <p className="market-score-caution">
            RSI is{' '}
            {rsi >= 70
              ? 'above 70: momentum may be extended'
              : 'below 30: downside momentum is strong'}
            . This alone does not imply a reversal.
          </p>
        )}
        <details className="market-score-breakdown">
          <summary>What makes this score?</summary>
          {a.components.map((c) => (
            <div key={c.id}>
              <span title={c.rule}>
                {c.label}
                <small>
                  {c.weight}% weight ·{' '}
                  {c.value == null
                    ? 'unavailable'
                    : c.value === 100
                      ? 'bullish'
                      : c.value === 0
                        ? 'bearish'
                        : 'neutral'}
                </small>
              </span>
              <strong>{c.value ?? '—'}</strong>
            </div>
          ))}
          <p>
            {a.available_weight}% of the original weight is available. Available votes are
            normalized. These related indicators are not independent evidence.
          </p>
        </details>
      </div>
      <div className="stat-list market-risk-glance">
        <div>
          <span>Sample return</span>
          <strong>{format(s.returns.sample_pct, '%', '')}</strong>
        </div>
        <div>
          <span>Max. drawdown</span>
          <strong>{format(s.risk.max_drawdown_pct, '%', '')}</strong>
        </div>
        <div>
          <span>RSI · 14</span>
          <strong>{format(rsi, 'number', '')}</strong>
        </div>
        <div>
          <span>Volatility · annualized</span>
          <strong>{format(s.volatility.annualized_pct, '%', '')}</strong>
        </div>
      </div>
      <a className="text-button market-statistics-jump" href="#market-statistics">
        Explore all statistics <ArrowUpRight size={13} />
      </a>
    </Panel>
  );
}

/** Server-computed metrics retain their exact source, interval and sample scope. */
export function MarketStatistics({ data }: { data: Analysis }) {
  const s: Statistics = data.statistics,
    quote = data.symbol.split('/')[1];
  return (
    <section
      className="market-statistics"
      id="market-statistics"
      aria-labelledby="market-statistics-title"
    >
      <div className="market-statistics-heading">
        <div>
          <span className="eyebrow">Beyond the chart</span>
          <h2 id="market-statistics-title">Market statistics</h2>
          <p>
            {data.symbol} · {data.timeframe} · {s.sample.observations} consecutive candles ·{' '}
            {s.sample.return_observations} returns
          </p>
        </div>
        <button
          className="button secondary small"
          onClick={() =>
            exportCSV('sibyl-market-statistics.csv', [
              [
                'Symbol',
                'Source',
                'Timeframe',
                'From',
                'To',
                'Group',
                'Metric',
                'Value',
                'Unit',
                'Definition',
              ],
              ...groups.flatMap((g) =>
                g.metrics.map(([key, label, unit, description]) => [
                  data.symbol,
                  data.source,
                  data.timeframe,
                  s.sample.start,
                  s.sample.end,
                  g.title,
                  label,
                  s[g.key][key] ?? '',
                  unit === 'price' ? quote : unit === 'volume' ? data.symbol.split('/')[0] : unit,
                  description,
                ]),
              ),
              ...s.assessment.components.map((c) => [
                data.symbol,
                data.source,
                data.timeframe,
                s.sample.start,
                s.sample.end,
                'Technical bias',
                c.label,
                c.value ?? '',
                `vote; ${c.weight}% weight`,
                c.rule,
              ]),
              [
                data.symbol,
                data.source,
                data.timeframe,
                s.sample.start,
                s.sample.end,
                'Technical bias',
                s.assessment.label,
                s.assessment.score ?? '',
                '/ 100',
                s.assessment.note,
              ],
            ])
          }
        >
          <Download size={14} /> Export statistics
        </button>
      </div>
      <div className="market-statistics-scope">
        <DataNote source={data.source} label={data.source_label} />
        <span>
          {new Date(s.sample.start).toLocaleString()} → {new Date(s.sample.end).toLocaleString()}
        </span>
        <span>Full analysis sample · chart zoom is visual only</span>
        {s.sample.stale && <Badge tone="peach">Historical / stale</Badge>}
      </div>
      {s.sample.warnings.length > 0 && (
        <div className="market-statistics-notices" role="status">
          {s.sample.warnings.map((w) => (
            <p key={w}>{w}</p>
          ))}
        </div>
      )}
      <div className="market-statistics-grid">
        {groups.map((g) => (
          <Panel className="market-statistic-card" key={g.key}>
            <div className="market-statistic-card-title">
              <g.icon size={17} />
              <h3>{g.title}</h3>
            </div>
            <dl>
              {g.metrics.slice(0, 5).map(([key, label, unit, description]) => (
                <MetricRow
                  key={key}
                  label={label}
                  value={format(
                    s[g.key][key],
                    unit,
                    unit === 'volume' ? data.symbol.split('/')[0] : quote,
                  )}
                  description={description}
                />
              ))}
            </dl>
            <details>
              <summary>
                More readings & definitions <CircleHelp size={12} />
              </summary>
              <dl>
                {g.metrics.slice(5).map(([key, label, unit, description]) => (
                  <MetricRow
                    key={key}
                    label={label}
                    value={format(
                      s[g.key][key],
                      unit,
                      unit === 'volume' ? data.symbol.split('/')[0] : quote,
                    )}
                    description={description}
                  />
                ))}
              </dl>
              <div className="market-metric-definitions">
                {g.metrics.map(([key, label, , description]) => (
                  <p key={key}>
                    <b>{label}.</b> {description}
                  </p>
                ))}
              </div>
            </details>
          </Panel>
        ))}
      </div>
      <p className="market-statistics-method">
        <CircleHelp size={14} /> All periods refer to {data.timeframe} candles. Returns and risk
        describe this sample, with zero risk-free rate and no fees. Volume is from this source, not
        the whole market. Blank readings need more history or a nonzero denominator. The technical
        score is an uncalibrated heuristic, not investment advice.
      </p>
      <details className="market-methodology">
        <summary>Score rules & calculation notes</summary>
        <p>
          {s.assessment.note} An overall score needs 50 consecutive candles, fresh history and at
          least 80% available weight. Scores ≥65 are Bullish; ≤35 are Bearish; otherwise Mixed.
        </p>
        <ul>
          {s.assessment.components.map((c) => (
            <li key={c.id}>
              {c.label} ({c.weight}%): {c.rule}
            </li>
          ))}
        </ul>
        <p>
          Moving averages and Wilder-style smoothers initialize at the start of the consecutive
          sample and can differ from a provider with more retained history. Return volatility uses
          sample deviation. VaR uses linear-interpolated empirical quantiles with at least 20
          returns; expected shortfall averages returns in that observed tail. Intraday annualization
          can be unstable. None of these statistics includes order-book depth, fundamentals or
          transaction costs.
        </p>
      </details>
    </section>
  );
}

function MetricRow({
  label,
  value,
  description,
}: {
  label: string;
  value: string;
  description: string;
}) {
  return (
    <div title={description}>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}
