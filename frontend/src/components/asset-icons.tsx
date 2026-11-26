import sprite from '../assets/crypto-assets.svg?url';

/** Background colors match the marks in the local SVG sprite. */
const assetBackgrounds: Partial<Record<string, string>> = {
  AAVE: '#9391f7',
  ADA: '#246dd3',
  ALGO: '#000',
  APT: 'linear-gradient(145deg, #c65cff, #33ffcc)',
  ARB: '#000',
  ATOM: '#a3a9d0',
  AVAX: '#e84142',
  BCH: '#58be92',
  BNB: '#000',
  BTC: '#f7931a',
  CRO: '#2e4b9f',
  DAI: '#fdc134',
  DASH: '#008de4',
  DOGE: '#c3a634',
  DOT: '#e6007a',
  ETC: '#01c853',
  ETH: '#000',
  FIL: '#0090ff',
  HBAR: '#000',
  HYPE: '#072723',
  ICP: '#46abe3',
  INJ: '#4d3dff',
  KAS: '#71c9bb',
  LINK: '#2e61de',
  LTC: '#345d9d',
  NEAR: '#00ec97',
  OP: '#fe0420',
  PAXG: '#cca727',
  PEPE: '#4f9843',
  POL: 'linear-gradient(145deg, #8f34c2, #7442db)',
  PYTH: '#110f24',
  RENDER: 'linear-gradient(145deg, #e92121, #9c0403)',
  SEI: 'linear-gradient(145deg, #90305c, #df3c41)',
  SHIB: '#fff',
  SOL: 'linear-gradient(145deg, #599db0, #47f8c3)',
  STX: '#7023eb',
  SUI: '#4ba2ff',
  TAO: '#ea302a',
  TIA: '#7a2bf9',
  TON: '#0098ea',
  TRX: '#c4342b',
  UNI: '#ff0a6f',
  USDC: '#0b53bf',
  USDT: '#009393',
  WBTC: '#000',
  XAUT: '#000',
  XLM: '#000',
  XMR: '#f60',
  XRP: '#000',
  ZEC: '#ecb244',
};

const aliases: Record<string, string> = { XBT: 'BTC', MATIC: 'POL', RNDR: 'RENDER' };
const currencyMarks: Record<string, string> = { USD: '$', EUR: '€', GBP: '£', JPY: '¥' };

/** Show a cached vector mark, or a legible currency or ticker fallback. */
export function AssetIcon({ asset, color = '#b47b37' }: { asset: string; color?: string }) {
  const ticker = asset.toUpperCase();
  const mark = aliases[ticker] ?? ticker;
  if (assetBackgrounds[mark]) {
    return (
      <span className="asset-icon asset-icon-branded" aria-hidden="true">
        <svg className="asset-icon-svg" viewBox="0 0 24 24" focusable="false">
          <use href={sprite + '#asset-' + mark.toLowerCase()} width="24" height="24" />
        </svg>
      </span>
    );
  }
  return (
    <span className="asset-icon asset-icon-fallback" aria-hidden="true" style={{ color }}>
      {currencyMarks[ticker] ?? ticker[0] ?? '·'}
    </span>
  );
}

function pairBackground(asset: string, color?: string) {
  const ticker = asset.toUpperCase();
  return (
    assetBackgrounds[aliases[ticker] ?? ticker] ??
    (color ? `color-mix(in srgb, ${color} 18%, var(--surface))` : 'var(--surface-soft)')
  );
}

/** Center each logo in its own half of the trading-pair mark. */
export function AssetPairIcon({
  base,
  quote,
  color,
}: {
  base: string;
  quote: string;
  color?: string;
}) {
  return (
    <span className="asset-pair-icon" aria-hidden="true">
      <span className="asset-pair-base" style={{ background: pairBackground(base, color) }}>
        <AssetIcon asset={base} color={color} />
      </span>
      <span className="asset-pair-quote" style={{ background: pairBackground(quote) }}>
        <AssetIcon asset={quote} />
      </span>
    </span>
  );
}
