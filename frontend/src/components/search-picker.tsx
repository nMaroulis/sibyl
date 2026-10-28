import {
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
  type CSSProperties,
} from 'react';
import { createPortal } from 'react-dom';
import { Check, ChevronDown, Search } from 'lucide-react';

export type PickerOption = {
  value: string;
  label: string;
  description?: string;
  keywords?: string;
  icon?: ReactNode;
  badge?: ReactNode;
  disabled?: boolean;
};
export type PickerGroup = { label: string; detail?: string; options: PickerOption[] };

const normalized = (value: string) => value.toLowerCase().replace(/[\s/_-]+/g, '');

/** Search every option, render a bounded result list, and keep selection keyboard accessible. */
export function SearchPicker({
  label,
  value,
  groups,
  onChange,
  placeholder = 'Search…',
  disabled = false,
  loading = false,
  hint,
  footer,
  className = '',
}: {
  label: string;
  value: string;
  groups: PickerGroup[];
  onChange: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  loading?: boolean;
  hint?: string;
  footer?: ReactNode;
  className?: string;
}) {
  const id = useId();
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const search = useRef<HTMLInputElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(0);
  const [position, setPosition] = useState<CSSProperties>({
    position: 'fixed',
    visibility: 'hidden',
  });
  const selected = groups
    .flatMap((group) => group.options)
    .find((option) => option.value === value);
  const terms = query.trim().split(/\s+/).map(normalized).filter(Boolean);
  const matches = groups.map((group) => ({
    ...group,
    options: group.options.filter((option) =>
      terms.every((term) =>
        normalized(`${option.label} ${option.description ?? ''} ${option.keywords ?? ''}`).includes(
          term,
        ),
      ),
    ),
  }));
  const count = matches.reduce((total, group) => total + group.options.length, 0);
  let remaining = 80;
  const visible = matches
    .map((group) => {
      const options = group.options.slice(0, remaining);
      remaining -= options.length;
      return { ...group, options };
    })
    .filter((group) => group.options.length);
  const options = visible.flatMap((group) => group.options);
  const close = (restoreFocus = false) => {
    setOpen(false);
    if (restoreFocus) trigger.current?.focus({ preventScroll: true });
  };
  const choose = (option: PickerOption) => {
    if (option.disabled) return;
    onChange(option.value);
    close(true);
  };
  const show = (last = false) => {
    setQuery('');
    const all = groups.flatMap((group) => group.options).slice(0, 80);
    const index = all.findIndex((option) => option.value === value && !option.disabled);
    setActive(
      index >= 0
        ? index
        : last
          ? Math.max(0, all.length - 1)
          : Math.max(
              0,
              all.findIndex((option) => !option.disabled),
            ),
    );
    setOpen(true);
  };

  useLayoutEffect(() => {
    if (!open) return;
    const measure = () => {
      if (!trigger.current) return;
      const rect = trigger.current.getBoundingClientRect();
      if (rect.bottom <= 0 || rect.top >= window.innerHeight) {
        setOpen(false);
        return;
      }
      const width = Math.min(Math.max(rect.width, 365), window.innerWidth - 24);
      const below = window.innerHeight - rect.bottom - 20;
      const above = rect.top - 20;
      const upwards = below < 280 && above > below;
      setPosition({
        position: 'fixed',
        width,
        left: Math.max(12, Math.min(rect.left, window.innerWidth - width - 12)),
        ...(upwards ? { bottom: window.innerHeight - rect.top + 8 } : { top: rect.bottom + 8 }),
        maxHeight: Math.max(150, Math.min(490, upwards ? above : below)),
      });
    };
    measure();
    search.current?.focus({ preventScroll: true });
    window.addEventListener('resize', measure);
    window.addEventListener('scroll', measure, true);
    return () => {
      window.removeEventListener('resize', measure);
      window.removeEventListener('scroll', measure, true);
    };
  }, [open]);
  useEffect(() => {
    if (!open) return;
    const outside = (event: Event) => {
      if (
        event.target instanceof Node &&
        !root.current?.contains(event.target) &&
        !menu.current?.contains(event.target)
      )
        setOpen(false);
    };
    document.addEventListener('pointerdown', outside);
    document.addEventListener('focusin', outside);
    return () => {
      document.removeEventListener('pointerdown', outside);
      document.removeEventListener('focusin', outside);
    };
  }, [open]);
  useEffect(() => {
    if (!open || !list.current) return;
    const option = document.getElementById(`${id}-option-${active}`);
    if (!option) return;
    const viewport = list.current.getBoundingClientRect();
    const row = option.getBoundingClientRect();
    // Only move the menu scroller; scrollIntoView can also move the document.
    if (row.top < viewport.top) list.current.scrollTop += row.top - viewport.top;
    else if (row.bottom > viewport.bottom) list.current.scrollTop += row.bottom - viewport.bottom;
  }, [open, active, query, id, position.maxHeight]);

  let index = -1;
  return (
    <div className={`search-picker ${className}`} ref={root}>
      <span id={`${id}-label`} className="search-picker-label">
        {label}
      </span>
      <button
        className="search-picker-trigger"
        type="button"
        ref={trigger}
        disabled={disabled || loading}
        aria-labelledby={`${id}-label ${id}-value`}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={open ? `${id}-menu` : undefined}
        onClick={() => (open ? close() : show())}
        onKeyDown={(event) => {
          if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            event.preventDefault();
            show(event.key === 'ArrowUp');
          }
        }}
      >
        {selected?.icon}
        <span className="search-picker-copy">
          <span className="search-picker-name" id={`${id}-value`}>
            {loading ? 'Loading markets…' : selected?.label || value || 'Choose a market'}{' '}
            {selected?.badge}
          </span>
          <small>{selected?.description || hint}</small>
        </span>
        <ChevronDown size={16} className="search-picker-chevron" />
      </button>
      {open &&
        createPortal(
          <div
            ref={menu}
            id={`${id}-menu`}
            role="dialog"
            aria-label={`${label} options`}
            className="search-picker-menu"
            style={position}
          >
            <div className="search-picker-search">
              <Search size={16} />
              <input
                ref={search}
                type="text"
                role="combobox"
                aria-label={`Search ${label.toLowerCase()}`}
                placeholder={placeholder}
                autoComplete="off"
                aria-controls={`${id}-list`}
                aria-expanded="true"
                aria-autocomplete="list"
                aria-activedescendant={options[active] ? `${id}-option-${active}` : undefined}
                value={query}
                onChange={(event) => {
                  setQuery(event.target.value);
                  setActive(0);
                }}
                onKeyDown={(event) => {
                  if (event.key === 'Escape') {
                    event.preventDefault();
                    event.stopPropagation();
                    close(true);
                  } else if (event.key === 'Tab') {
                    close(true);
                  } else if (event.key === 'Enter') {
                    event.preventDefault();
                    if (options[active]) choose(options[active]);
                  } else if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
                    event.preventDefault();
                    const step = event.key === 'ArrowUp' || event.key === 'End' ? -1 : 1;
                    let next =
                      event.key === 'Home'
                        ? 0
                        : event.key === 'End'
                          ? options.length - 1
                          : active + step;
                    while (next >= 0 && next < options.length && options[next].disabled)
                      next += step;
                    if (next >= 0 && next < options.length) setActive(next);
                  }
                }}
              />
            </div>
            <div
              className="search-picker-options"
              ref={list}
              id={`${id}-list`}
              role="listbox"
              aria-label={label}
            >
              {visible.map((group) => (
                <div
                  key={group.label}
                  role="group"
                  aria-label={group.label}
                  className="search-picker-group"
                >
                  <div className="search-picker-group-title">
                    <span>{group.label}</span>
                    {group.detail && <small>{group.detail}</small>}
                  </div>
                  {group.options.map((option) => {
                    const optionIndex = ++index;
                    return (
                      <button
                        type="button"
                        tabIndex={-1}
                        role="option"
                        id={`${id}-option-${optionIndex}`}
                        key={option.value}
                        disabled={option.disabled}
                        aria-selected={option.value === value}
                        data-active={optionIndex === active}
                        onMouseMove={() => !option.disabled && setActive(optionIndex)}
                        onClick={() => choose(option)}
                      >
                        {option.icon}
                        <span className="search-picker-copy">
                          <span className="search-picker-name">
                            {option.label} {option.badge}
                          </span>
                          <small>{option.description}</small>
                        </span>
                        {option.value === value && (
                          <Check size={15} className="search-picker-check" />
                        )}
                      </button>
                    );
                  })}
                </div>
              ))}
              {!count && (
                <div className="search-picker-empty">
                  No matching markets or sources. Try a ticker or another feed.
                </div>
              )}
            </div>
            <div className="search-picker-footer">
              <span role="status">
                {count > options.length
                  ? `Showing ${options.length} of ${count.toLocaleString()} · search to narrow`
                  : `${count.toLocaleString()} ${count === 1 ? 'option' : 'options'}`}
              </span>
              {footer}
            </div>
          </div>,
          document.body,
        )}
    </div>
  );
}
