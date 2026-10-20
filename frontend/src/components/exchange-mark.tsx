import { FlaskConical, Landmark } from 'lucide-react';
import { exchangeIcons } from '../lib/exchange-icons';

/** Self-hosted exchange marks avoid remote image requests on account screens. */
export function ExchangeMark({ exchange, size = 26 }: { exchange: string; size?: number }) {
  if (exchange === 'demo') return <FlaskConical size={size} aria-hidden="true" />;
  const brand =
    { 'binance-testnet': 'binance', 'coinbase-sandbox': 'coinbase' }[exchange] ?? exchange;
  const icon = exchangeIcons[brand];
  return icon ? (
    <img src={icon} width={size} height={size} alt="" className="exchange-mark" />
  ) : (
    <Landmark size={size} aria-hidden="true" />
  );
}
