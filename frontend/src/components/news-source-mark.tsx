import { FlaskConical } from 'lucide-react';

const icons: Record<string, string> = {
  coindesk: '/news/coindesk.png',
  cointelegraph: '/news/cointelegraph.png',
  decrypt: '/news/decrypt.png',
  theblock: '/news/theblock.ico',
  cryptoslate: '/news/cryptoslate.png',
  newsapi: '/news/newsapi.png',
};

/** Local publisher marks; selecting a source never loads a third-party image. */
export function NewsSourceMark({ source }: { source: string }) {
  return (
    <span
      className={`news-source-mark ${source === 'demo' ? 'news-source-mark-demo' : ''}`}
      aria-hidden="true"
    >
      {source === 'demo' ? (
        <FlaskConical size={21} />
      ) : (
        <img src={icons[source]} alt="" width={32} height={32} />
      )}
    </span>
  );
}
