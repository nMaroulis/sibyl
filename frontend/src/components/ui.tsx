import { createContext, useContext, useEffect, useId, useState } from 'react';
import type { ReactNode } from 'react';
import {
  AlertCircle,
  ArrowDownRight,
  ArrowUpRight,
  Check,
  LoaderCircle,
  RefreshCw,
  X,
} from 'lucide-react';
import { percent } from '../lib/api';

export function Badge({ children, tone = 'neutral' }: { children: ReactNode; tone?: string }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}
export function Change({ value }: { value: number | null | undefined }) {
  if (value == null || !Number.isFinite(value)) return <span className="muted">—</span>;
  const Icon = value >= 0 ? ArrowUpRight : ArrowDownRight;
  return (
    <span className={`change ${value >= 0 ? 'positive' : 'negative'}`}>
      <Icon size={13} />
      {percent(value)}
    </span>
  );
}
export function AssetIcon({ asset, color }: { asset: string; color?: string }) {
  return (
    <span
      className={`asset-icon asset-${asset}`}
      style={{
        background: `${color || '#f6a94d'}18`,
        color: color || '#f6a94d',
      }}
    >
      {(
        {
          BTC: '₿',
          ETH: 'Ξ',
          SOL: '≋',
          USDT: '₮',
          LINK: '⬡',
          AVAX: '▲',
          DOT: '●',
        } as Record<string, string>
      )[asset] ?? asset[0]}
    </span>
  );
}
export function PageTitle({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow?: string;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="page-title">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      <div className="title-actions">{action}</div>
    </div>
  );
}
export function Panel({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <section className={`panel ${className}`}>{children}</section>;
}
export function PanelTitle({
  title,
  subtitle,
  action,
}: {
  title: string;
  subtitle?: string;
  action?: ReactNode;
}) {
  return (
    <div className="panel-title">
      <div>
        <h2>{title}</h2>
        {subtitle && <p>{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}
export function Loading() {
  return (
    <div className="loading-state" role="status">
      <LoaderCircle className="spin" size={24} />
      <span>Loading workspace…</span>
    </div>
  );
}
export function ErrorState({ message, retry }: { message: string; retry?: () => void }) {
  return (
    <div className="error-state" role="alert">
      <AlertCircle size={20} />
      <p>{message}</p>
      {retry && (
        <button className="button secondary" onClick={retry}>
          <RefreshCw size={14} />
          Try again
        </button>
      )}
    </div>
  );
}
export function Empty({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="empty-state">
      <div className="empty-orbit">✳</div>
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}
export function DataNote({ source, label }: { source?: string; label?: string }) {
  return (
    <span className="data-note">
      <span className="status-dot" />
      {source === 'demo'
        ? 'Illustrative demo data'
        : source
          ? `Source: ${label || (source.startsWith('connection:') ? 'Connected exchange account' : source)}`
          : 'Local workspace'}
    </span>
  );
}

export function Modal({
  title,
  children,
  onClose,
  className = '',
  backdropClassName = '',
  initialFocus = 'input, button',
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  className?: string;
  backdropClassName?: string;
  initialFocus?: string;
}) {
  const id = useId();
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const key = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
      if (event.key === 'Tab') {
        const dialog = document.getElementById(id);
        const elements = dialog?.querySelectorAll<HTMLElement>(
          'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href], [tabindex="0"]',
        );
        if (!elements?.length) return;
        const first = elements[0],
          last = elements[elements.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        }
        if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener('keydown', key);
    document.getElementById(id)?.querySelector<HTMLElement>(initialFocus)?.focus();
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', key);
      document.body.style.overflow = overflow;
      previous?.focus();
    };
  }, [id, onClose, initialFocus]);
  return (
    <div
      className={`modal-backdrop ${backdropClassName}`}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        id={id}
        className={`modal ${className}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={`${id}-title`}
      >
        <div className="modal-header">
          <h2 id={`${id}-title`}>{title}</h2>
          <button className="icon-button" aria-label="Close dialog" onClick={onClose}>
            <X size={20} />
          </button>
        </div>
        {children}
      </section>
    </div>
  );
}

const ToastContext = createContext<(message: string, error?: boolean) => void>(() => {});
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<{
    message: string;
    error: boolean;
    id: number;
  }>();
  useEffect(() => {
    if (toast) {
      const timer = setTimeout(() => setToast(undefined), 5000);
      return () => clearTimeout(timer);
    }
  }, [toast]);
  return (
    <ToastContext.Provider
      value={(message, error = false) => setToast({ message, error, id: Date.now() })}
    >
      {children}
      {toast && (
        <div className={`toast ${toast.error ? 'toast-error' : ''}`} role="status">
          {toast.error ? <AlertCircle size={18} /> : <Check size={18} />}
          <span>{toast.message}</span>
          <button onClick={() => setToast(undefined)} aria-label="Dismiss notification">
            <X size={14} />
          </button>
        </div>
      )}
    </ToastContext.Provider>
  );
}
export const useToast = () => useContext(ToastContext);
