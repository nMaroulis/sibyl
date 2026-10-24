/** Self-hosted provider symbols; provenance is recorded in public/exchanges/sources.json. */
export const exchangeIcons: Record<string, string> = {
  binance: '/exchanges/binance.jpg',
  binanceus: '/exchanges/binanceus.png',
  coinbase: '/exchanges/coinbase.png',
  kraken: '/exchanges/kraken.jpg',
  okx: '/exchanges/okx.png',
  bybit: '/exchanges/bybit.png',
  kucoin: '/exchanges/kucoin.png',
  gate: '/exchanges/gate.png',
  bitget: '/exchanges/bitget.jpg',
  mexc: '/exchanges/mexc.jpg',
  htx: '/exchanges/htx.png',
  cryptocom: '/exchanges/cryptocom.jpg',
  bitstamp: '/exchanges/bitstamp.jpg',
  gemini: '/exchanges/gemini.png',
  bitfinex: '/exchanges/bitfinex.png',
  phemex: '/exchanges/phemex.png',
  poloniex: '/exchanges/poloniex.png',
  upbit: '/exchanges/upbit.png',
  coinex: '/exchanges/coinex.svg',
  bitmart: '/exchanges/bitmart.ico',
};

/** Curated from the bundled marks; these decorative colours never encode support. */
export const exchangeBrandColors: Record<string, readonly [string, string]> = {
  binance: ['#f0b90b', '#f7d66c'],
  binanceus: ['#f0b90b', '#dbb752'],
  coinbase: ['#1652f0', '#86abff'],
  kraken: ['#713aff', '#ad8cff'],
  okx: ['#343b45', '#9ba3ad'],
  bybit: ['#f7a600', '#b9a581'],
  kucoin: ['#24ae8f', '#83d5b9'],
  gate: ['#0068ff', '#0ed9a7'],
  bitget: ['#00cbd3', '#6de7de'],
  mexc: ['#1463ff', '#79b7ff'],
  htx: ['#1224c5', '#7899f7'],
  cryptocom: ['#0b2c67', '#6a87c1'],
  bitstamp: ['#249653', '#a5c7b0'],
  gemini: ['#00c8e1', '#6bd9de'],
  bitfinex: ['#00b898', '#70c4af'],
  coinex: ['#0ead98', '#7cd0ba'],
  bitmart: ['#404650', '#aeb7c0'],
  phemex: ['#43b990', '#9ddc76'],
  poloniex: ['#269277', '#92ceb6'],
  upbit: ['#0045c6', '#7c9de3'],
};

export function exchangeBrand(exchange: string): string {
  return { 'binance-testnet': 'binance', 'coinbase-sandbox': 'coinbase' }[exchange] ?? exchange;
}
