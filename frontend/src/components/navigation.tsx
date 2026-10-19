import { useLayoutEffect, useRef } from 'react';
import type { ReactNode } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { LayoutGrid } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

type Destination = { path: string; name: string; icon: LucideIcon };

/** A floating dock whose selection and page marker follow the actual button geometry. */
export function NavigationDock({
  items,
  expanded,
  onMore,
}: {
  items: Destination[];
  expanded: boolean;
  onMore: () => void;
}) {
  const location = useLocation();
  const dock = useRef<HTMLElement>(null);
  const moreActive = !items.some((item) => item.path === location.pathname);

  useLayoutEffect(() => {
    const element = dock.current;
    if (!element) return;
    const surface = element.parentElement?.querySelector('.workspace-surface');
    const measure = () => {
      const active = element.querySelector<HTMLElement>(
        '[aria-current="page"], [data-current="true"]',
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
        className={`dock-item ${moreActive ? 'active' : ''}`}
        data-current={moreActive}
        aria-label="More tools"
        aria-expanded={expanded}
        onClick={onMore}
      >
        <span className="dock-icon">
          <LayoutGrid size={21} />
        </span>
        <span>More</span>
      </button>
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
