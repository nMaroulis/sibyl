import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import type { CSSProperties, ReactNode } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { LayoutGrid } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

type Destination = { path: string; name: string; icon: LucideIcon };

/** A floating dock whose selection and page marker follow the actual button geometry. */
export function NavigationDock({
  items,
  moreItems,
}: {
  items: Destination[];
  moreItems: Destination[];
}) {
  const location = useLocation();
  const dock = useRef<HTMLElement>(null);
  const moreButton = useRef<HTMLButtonElement>(null);
  const morePanel = useRef<HTMLDivElement>(null);
  const panelId = useId();
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    setExpanded(false);
  }, [location.pathname, location.search]);
  useEffect(() => {
    if (!expanded) return;
    const outside = (event: PointerEvent) => {
      if (event.target instanceof Node && !dock.current?.contains(event.target)) setExpanded(false);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        setExpanded(false);
        moreButton.current?.focus({ preventScroll: true });
      }
    };
    const focusOutside = (event: FocusEvent) => {
      if (event.target instanceof Node && !dock.current?.contains(event.target)) setExpanded(false);
    };
    document.addEventListener('pointerdown', outside);
    document.addEventListener('keydown', escape);
    document.addEventListener('focusin', focusOutside);
    return () => {
      document.removeEventListener('pointerdown', outside);
      document.removeEventListener('keydown', escape);
      document.removeEventListener('focusin', focusOutside);
    };
  }, [expanded]);
  const moreActive = !items.some((item) => item.path === location.pathname);

  useLayoutEffect(() => {
    const element = dock.current;
    if (!element) return;
    const surface = element.parentElement?.querySelector('.workspace-surface');
    const measure = () => {
      const active = element.querySelector<HTMLElement>(
        '[aria-current="page"], [data-current="true"]',
      );
      const more = moreButton.current;
      if (more)
        element.style.setProperty('--more-center', `${more.offsetTop + more.offsetHeight / 2}px`);
      element.style.setProperty(
        '--more-space',
        `${Math.max(0, window.innerWidth - element.getBoundingClientRect().right - 16)}px`,
      );
      if (!active) return;
      element.style.setProperty('--selection-y', `${active.offsetTop}px`);
      element.style.setProperty('--selection-x', `${active.offsetLeft}px`);
      element.style.setProperty('--selection-width', `${active.offsetWidth}px`);
      element.style.setProperty('--selection-height', `${active.offsetHeight}px`);
      if (surface) {
        const gap = surface.getBoundingClientRect().left - active.getBoundingClientRect().right;
        element.style.setProperty('--connector-width', `${Math.max(0, gap) + 3}px`);
      }
      element.dataset.ready = 'true';
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    if (surface) observer.observe(surface);
    window.addEventListener('resize', measure);
    return () => {
      observer.disconnect();
      window.removeEventListener('resize', measure);
    };
  }, [location.pathname]);

  return (
    <nav ref={dock} className="side-dock" aria-label="Main navigation">
      <span className="dock-selection" aria-hidden="true">
        <span className="dock-connector" />
      </span>
      {items.map((item) => (
        <NavLink
          end={item.path === '/'}
          key={item.path}
          to={item.path}
          aria-label={item.name}
          className={({ isActive }) => `dock-item ${isActive ? 'active' : ''}`}
        >
          <span className="dock-icon">
            <item.icon size={21} />
          </span>
          <span>{item.name}</span>
        </NavLink>
      ))}
      <button
        className={`dock-item dock-more-trigger ${moreActive ? 'active' : ''}`}
        ref={moreButton}
        data-current={moreActive}
        aria-label="More tools"
        aria-expanded={expanded}
        aria-controls={panelId}
        onClick={(event) => {
          const opening = !expanded;
          setExpanded(opening);
          if (opening && event.detail === 0) {
            requestAnimationFrame(() =>
              morePanel.current
                ?.querySelector<HTMLAnchorElement>('a')
                ?.focus({ preventScroll: true }),
            );
          }
        }}
        onKeyDown={(event) => {
          if (event.key === 'ArrowRight') {
            event.preventDefault();
            setExpanded(true);
            requestAnimationFrame(() =>
              morePanel.current
                ?.querySelector<HTMLAnchorElement>('a')
                ?.focus({ preventScroll: true }),
            );
          }
        }}
      >
        <span className="dock-icon">
          <LayoutGrid size={21} />
        </span>
        <span>More</span>
      </button>
      <div
        ref={morePanel}
        id={panelId}
        className="dock-more-panel"
        style={{
          gridTemplateColumns: `repeat(${Math.max(1, Math.min(3, moreItems.length))}, minmax(0, 1fr))`,
        }}
        data-open={expanded}
        role="group"
        aria-label="More destinations"
        aria-hidden={!expanded}
        inert={!expanded}
        onKeyDown={(event) => {
          const links = Array.from(
            morePanel.current?.querySelectorAll<HTMLAnchorElement>('a') ?? [],
          );
          const index = links.indexOf(document.activeElement as HTMLAnchorElement);
          if (event.key === 'ArrowLeft' && index === 0) {
            event.preventDefault();
            moreButton.current?.focus({ preventScroll: true });
            return;
          }
          const next =
            event.key === 'ArrowRight'
              ? (index + 1) % links.length
              : event.key === 'ArrowLeft'
                ? (index - 1 + links.length) % links.length
                : event.key === 'Home'
                  ? 0
                  : event.key === 'End'
                    ? links.length - 1
                    : null;
          if (next !== null) {
            event.preventDefault();
            links[next]?.focus({ preventScroll: true });
          }
        }}
      >
        {moreItems.map((item, index) => (
          <NavLink
            key={item.path}
            to={item.path}
            style={{ '--more-index': index } as CSSProperties}
            onClick={() => {
              setExpanded(false);
              moreButton.current?.focus({ preventScroll: true });
            }}
            className={({ isActive }) => `dock-more-link ${isActive ? 'active' : ''}`}
          >
            <span>
              <item.icon size={21} />
            </span>
            <span>{item.name}</span>
          </NavLink>
        ))}
      </div>
    </nav>
  );
}

/** Unfold the route from its dock connection, keeping text at its natural scale. */
export function PageView({ children }: { children: ReactNode }) {
  const location = useLocation();
  const view = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    window.scrollTo({ top: 0, behavior: 'instant' });
    const element = view.current;
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    if (!element?.animate || reducedMotion.matches) return;
    const button = document.querySelector(
      '.side-dock [aria-current="page"], .side-dock [data-current="true"]',
    );
    if (!button) return;
    const origin = button.getBoundingClientRect();
    const bounds = element.getBoundingClientRect();
    const y = Math.max(0, Math.min(bounds.height, origin.top + origin.height / 2 - bounds.top));
    const top = Math.max(0, y - 30);
    const bottom = Math.max(0, bounds.height - y - 30);
    const right = Math.max(0, bounds.width - 24);
    const reveal = element.animate(
      [
        {
          clipPath: `inset(${top}px ${right}px ${bottom}px 0px round 18px)`,
          opacity: 0.3,
          transform: 'translateX(-12px)',
        },
        { clipPath: 'inset(0px 0px 0px 0px round 0px)', opacity: 1, transform: 'translateX(0)' },
      ],
      { duration: 580, easing: 'cubic-bezier(.16,1,.3,1)' },
    );
    const stop = () => reveal.cancel();
    reducedMotion.addEventListener('change', stop);
    return () => {
      stop();
      reducedMotion.removeEventListener('change', stop);
    };
  }, [location.pathname]);
  return (
    <div ref={view} className="page-view">
      {children}
    </div>
  );
}
