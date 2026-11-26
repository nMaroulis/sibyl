import { CalendarRange, ChartNoAxesCombined, CircleAlert, History, Wallet } from 'lucide-react';
import type { ReactNode } from 'react';
import { number } from '../../lib/api';
import { frameSeconds, type Dataset } from '../../lib/market-history';
import type { StrategyParams, Timeframe } from '../../lib/types';
import { AssetIcon, AssetPairIcon } from '../asset-icons';
import { MarketSelector, type SpotCatalog } from '../market-controls';
import { SearchPicker } from '../search-picker';
import { StrategyTimeframePicker } from './strategy-timeframe-picker';
import { StrategyField, StrategyHelp } from './strategy-field';
import type { ParameterHelp } from './strategy-signal-settings';
import {
  initialBacktestDates,
  maximumLookback,
  StrategyBacktestDates,
  type BacktestDateRange,
} from './strategy-backtest-dates';

export const maximumStrategyAmount = 10_000_000;

const lookbacks = [90, 180, 365, maximumLookback];
const durationFormat = new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 });

function lookbackDuration(count: number, timeframe: Timeframe) {
  const hours = (count * frameSeconds[timeframe]) / 3600;
  const [size, unit] = hours >= 24 ? [hours / 24, 'days'] : [hours, 'hours'];
  return '≈ ' + durationFormat.format(size) + ' ' + unit;
}

function StrategyLookbackPicker({
  value,
  timeframe,
  onChange,
  chooseDates,
  datesSelected,
}: {
  value: number;
  timeframe: Timeframe;
  onChange: (count: number) => void;
  chooseDates?: () => void;
  datesSelected: boolean;
}) {
  return (
    <SearchPicker
      label="Indicator lookback"
      value={datesSelected ? 'dates' : String(value)}
      className="strategy-lookback-picker"
      menuClassName="strategy-timeframe-menu"
      placeholder="Find a candle count…"
      messages={{ empty: 'No matching lookbacks.' }}
      groups={[
        {
          label: 'Candle history',
          options: [...new Set([...lookbacks, value])]
            .sort((a, b) => a - b)
            .map((count) => ({
              value: String(count),
              label: count.toLocaleString() + ' candles',
              icon: (
                <span className="strategy-timeframe-icon">
                  <ChartNoAxesCombined size={16} aria-hidden="true" />
                </span>
              ),
              badge: (
                <span className="picker-default-badge">{lookbackDuration(count, timeframe)}</span>
              ),
            })),
        },
        ...(chooseDates
          ? [
              {
                label: 'Historical window',
                options: [
                  {
                    value: 'dates',
                    label: 'Custom dates',
                    keywords: 'date range start end from until historical',
                    icon: (
                      <span className="strategy-timeframe-icon">
                        <CalendarRange size={16} aria-hidden="true" />
                      </span>
                    ),
                  },
                ],
              },
            ]
          : []),
      ]}
      onChange={(selection) =>
        selection === 'dates' ? chooseDates?.() : onChange(Number(selection))
      }
    />
  );
}

function SavedMarket({
  dataset,
  amount,
  onUseLatest,
}: {
  dataset: Dataset;
  amount: ReactNode;
  onUseLatest: () => void;
}) {
  const [base, quote] = dataset.symbol.split('/');
  return (
    <div className="strategy-saved-market">
      <div className="strategy-saved-market-header">
        <p>
          <History size={15} aria-hidden="true" /> From saved dataset
        </p>
        <button className="text-button" type="button" onClick={onUseLatest}>
          Use latest candles
        </button>
      </div>
      <div className="strategy-market-inputs">
        <div>
          <span className="search-picker-label">Spot pair</span>
          <div className="strategy-saved-value">
            <AssetPairIcon base={base} quote={quote} />
            <strong>{dataset.symbol}</strong>
          </div>
        </div>
        {amount}
        <div>
          <span className="search-picker-label">Timeframe</span>
          <strong className="strategy-saved-value">{dataset.timeframe}</strong>
        </div>
        <div>
          <span className="search-picker-label">Indicator lookback</span>
          <strong className="strategy-saved-value">{dataset.count.toLocaleString()} candles</strong>
        </div>
      </div>
      <small className="strategy-saved-source">
        {dataset.source_label} · {new Date(dataset.start).toLocaleDateString()} to{' '}
        {new Date(dataset.end).toLocaleDateString()} (end excluded)
      </small>
    </div>
  );
}

/** Collect shared market and sizing inputs before the user chooses a run mode. */
export function StrategyMarketSettings({
  catalog,
  dataset,
  onUseLatest,
  dates,
  onDatesChange,
  params,
  update,
  deploy,
  help,
  amountError,
  funding,
}: {
  catalog?: SpotCatalog;
  dataset?: Dataset;
  onUseLatest: () => void;
  dates?: BacktestDateRange;
  onDatesChange?: (dates: BacktestDateRange | undefined) => void;
  params: StrategyParams;
  update: (key: 'symbol' | 'capital' | 'timeframe' | 'candles', value: string | number) => void;
  deploy: boolean;
  help: ParameterHelp;
  amountError: string;
  funding?: { available?: number; loading: boolean; exceedsBalance: boolean };
}) {
  const frame = params.timeframe ?? '1d';
  const quote = (dataset?.symbol ?? params.symbol).split('/')[1];
  const overBalance = !!funding?.exceedsBalance && !amountError;
  const descriptions = [
    funding && 'strategy-amount-balance',
    overBalance && 'strategy-amount-warning',
    amountError && 'strategy-amount-error',
  ]
    .filter(Boolean)
    .join(' ');
  const amount = (
    <StrategyField label="Amount" caption={help.capital}>
      <span className="strategy-amount-entry" data-over-balance={overBalance || undefined}>
        <input
          type="number"
          min={deploy ? 0 : 100}
          max={maximumStrategyAmount}
          step="any"
          value={params.capital === 0 ? '' : params.capital}
          onChange={(event) => update('capital', Number(event.currentTarget.value))}
          aria-label={'Amount · ' + quote}
          aria-invalid={!!amountError || (deploy && overBalance)}
          aria-describedby={descriptions || undefined}
        />
        <span className="strategy-amount-unit" aria-hidden="true">
          <AssetIcon asset={quote} />
          {quote}
        </span>
      </span>
      {funding && (
        <small className="strategy-amount-balance" id="strategy-amount-balance" role="status">
          <Wallet size={13} aria-hidden="true" />
          {funding.available === undefined ? (
            <span>{funding.loading ? 'Checking free balance…' : 'Free balance unavailable'}</span>
          ) : (
            <span>
              Free in selected account{' '}
              <strong>
                {number(funding.available, 12)} {quote}
              </strong>
            </span>
          )}
        </small>
      )}
      {overBalance && (
        <small className="strategy-amount-warning" id="strategy-amount-warning" role="status">
          <CircleAlert size={13} aria-hidden="true" />
          <span>
            <strong>Amount exceeds available {quote} balance.</strong> This amount can only be used
            for a backtest or paper strategy.
          </span>
        </small>
      )}
      {amountError && (
        <small className="negative" id="strategy-amount-error">
          {amountError}
        </small>
      )}
    </StrategyField>
  );
  return (
    <>
      {dataset ? (
        <SavedMarket dataset={dataset} amount={amount} onUseLatest={onUseLatest} />
      ) : catalog ? (
        <div className="strategy-market-inputs">
          <div className="strategy-field">
            <MarketSelector
              catalog={catalog}
              label="Spot pair"
              value={
                catalog.items.some((item) => item.symbol === params.symbol) ? params.symbol : ''
              }
              onChange={(value) => update('symbol', value)}
            />
            <StrategyHelp label="Spot pair" caption={help.symbol} />
          </div>
          {amount}
          <div className="strategy-field">
            <StrategyTimeframePicker
              frames={catalog.timeframes}
              value={catalog.timeframes.includes(frame) ? frame : ''}
              onChange={(value: Timeframe) => update('timeframe', value)}
            />
            <StrategyHelp label="Timeframe" caption={help.timeframe} />
          </div>
          <div className="strategy-field">
            <StrategyLookbackPicker
              value={params.candles}
              timeframe={frame}
              onChange={(value) => {
                onDatesChange?.(undefined);
                update('candles', value);
              }}
              chooseDates={
                onDatesChange
                  ? () => onDatesChange(dates ?? initialBacktestDates(frame, params.candles))
                  : undefined
              }
              datesSelected={!!dates}
            />
            <StrategyHelp label="Indicator lookback" caption={help.candles} />
          </div>
        </div>
      ) : (
        amount
      )}
      {dates && onDatesChange && (
        <StrategyBacktestDates range={dates} timeframe={frame} onChange={onDatesChange} />
      )}
    </>
  );
}
