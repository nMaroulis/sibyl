import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

/** Format agent text without executing HTML or fetching model-supplied images. */
export function ChatMarkdown({ children }: { children: string }) {
  return (
    <div className="chat-markdown">
      <Markdown
        skipHtml
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) =>
            !href ? (
              <span>{children}</span>
            ) : (
              <a
                href={href}
                {...(/^(https?:)?\/\//i.test(href)
                  ? { target: '_blank', rel: 'noopener noreferrer' }
                  : {})}
              >
                {children}
              </a>
            ),
          img: ({ alt }) => (
            <span className="chat-image-description">{alt || 'Image omitted'}</span>
          ),
          table: ({ children }) => (
            <div className="chat-table-scroll">
              <table>{children}</table>
            </div>
          ),
        }}
      >
        {children}
      </Markdown>
    </div>
  );
}
