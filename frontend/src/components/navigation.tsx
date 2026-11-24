import { useEffect, useEffectEvent, useId, useLayoutEffect, useRef, useState } from 'react';
import type { CSSProperties, ReactNode } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { NavigationIcon } from './navigation-icon';
import { useInterfacePreferences } from '../lib/interface-preferences';
import { playPageTransition } from '../lib/page-transition';
import { LayoutGrid } from 'lucide-react';
import { destinations } from '../lib/navigation-options';

/** A floating dock whose selection and page marker follow the actual button geometry. */
export function NavigationDock() {
  const location = useLocation();
  const { navigation, showLabels, dockStyle, pinnedPaths } = useInterfacePreferences();
  const items = destinations.filter(({ path }) => pinnedPaths.includes(path));
  const moreItems = destinations.filter(({ path }) => !pinnedPaths.includes(path));
  const hasMore = moreItems.length > 0;
  const dock = useRef<HTMLElement>(null);
  const moreButton = useRef<HTMLButtonElement>(null);
  const morePanel = useRef<HTMLDivElement>(null);
  const panelId = useId();
  const [expanded, setExpanded] = useState(false);
  const presses = useRef(new Map<HTMLElement, Animation>());

  /** A small press-and-release for the dock’s direct shortcuts. */
  const press = (button: HTMLElement) => {
    if (!button.animate || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const current = getComputedStyle(button);
    const start = {
      scale: current.scale === 'none' ? '1' : current.scale,
      translate: current.translate === 'none' ? '0 0' : current.translate,
    };
    presses.current.get(button)?.cancel();
    const animation = button.animate(
      [
        start,
        { scale: '.95', translate: '0 1px', offset: 0.36 },
        { scale: '1', translate: '0 0', offset: 1 },
      ],
      { duration: 280, easing: 'cubic-bezier(.2,.7,.2,1)' },
    );
    presses.current.set(button, animation);
    const clear = () => {
      if (presses.current.get(button) === animation) presses.current.delete(button);
    };
    animation.finished.then(clear, clear);
  };
  useEffect(() => {
    const animations = presses.current;
    return () => {
      animations.forEach((animation) => animation.cancel());
      animations.clear();
    };
  }, []);

  useEffect(() => {
    setExpanded(false);
  }, [location.pathname, location.search, navigation, pinnedPaths]);
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

  const openMore = (focusFirst: boolean) => {
    const panel = morePanel.current;
    if (!panel) return;
    panel.scrollTop = 0;
    setExpanded(true);
    if (focusFirst) {
      requestAnimationFrame(() => panel.querySelector('a')?.focus({ preventScroll: true }));
    }
  };

  useLayoutEffect(() => {
    const element = dock.current;
    if (!element || navigation === 'bottom') return;
    const surface = element.parentElement?.querySelector('.workspace-surface');
    const measure = () => {
      const active = element.querySelector<HTMLElement>(
        '[aria-current="page"], [data-current="true"]',
      );
      const { top, right } = element.getBoundingClientRect();
      element.style.setProperty('--more-space', `${Math.max(0, window.innerWidth - right - 16)}px`);
      const more = moreButton.current;
      if (more && morePanel.current) {
        const halfHeight = morePanel.current.offsetHeight / 2;
        const center = more.offsetTop + more.offsetHeight / 2;
        const inset = 12 + halfHeight;
        element.style.setProperty(
          '--more-center',
          `${Math.min(window.innerHeight - inset - top, Math.max(inset - top, center))}px`,
        );
      }
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
    if (morePanel.current) observer.observe(morePanel.current);
    if (surface) observer.observe(surface);
    window.addEventListener('resize', measure);
    return () => {
      observer.disconnect();
      window.removeEventListener('resize', measure);
    };
  }, [location.pathname, navigation, pinnedPaths]);

  return (
    <nav
      ref={dock}
      className="side-dock"
      aria-label="Main navigation"
      data-show-labels={showLabels}
      data-dock-style={dockStyle}
      style={{ '--dock-slots': items.length + Number(hasMore) } as CSSProperties}
    >
      <span className="dock-selection" aria-hidden="true">
        <span className="dock-connector">
          <span key={location.pathname} className="dock-page-marker" />
        </span>
      </span>
      {items.map((item) => (
        <NavLink
          key={item.path}
          to={item.path}
          onClick={(event) => {
            if (!event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey)
              press(event.currentTarget);
          }}
          aria-label={item.name}
          className={({ isActive }) =>
            `dock-item ${item.path === '/sibyl' ? 'dock-sibyl' : ''} ${isActive ? 'active' : ''}`
          }
        >
          <span className="dock-icon">
            <NavigationIcon path={item.path} icon={item.icon} />
          </span>
          <span className="dock-label" aria-hidden="true">
            {item.name}
          </span>
        </NavLink>
      ))}
      {hasMore && (
        <>
          <button
            className={`dock-item dock-more-trigger ${moreActive ? 'active' : ''}`}
            ref={moreButton}
            data-current={moreActive}
            aria-label="More tools"
            aria-expanded={expanded}
            aria-controls={panelId}
            onClick={(event) => {
              if (expanded) setExpanded(false);
              else openMore(event.detail === 0);
            }}
            onKeyDown={(event) => {
              if (event.key === (navigation === 'bottom' ? 'ArrowUp' : 'ArrowRight')) {
                event.preventDefault();
                openMore(true);
              }
            }}
          >
            <span className="dock-icon">
              <NavigationIcon path="more" icon={LayoutGrid} />
            </span>
            <span className="dock-label" aria-hidden="true">
              More
            </span>
          </button>
          <div
            ref={morePanel}
            id={panelId}
            className="dock-more-panel"
            style={{
              gridTemplateColumns: `repeat(${Math.max(1, Math.min(3, Math.ceil(Math.sqrt(moreItems.length))))}, minmax(0, 1fr))`,
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
              if (
                (navigation === 'left' && event.key === 'ArrowLeft' && index === 0) ||
                (navigation === 'bottom' && event.key === 'ArrowDown')
              ) {
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
                links[next]?.focus();
              }
            }}
          >
            {moreItems.map((item) => (
              <NavLink
                key={item.path}
                to={item.path}
                aria-label={item.name}
                onClick={() => {
                  setExpanded(false);
                  moreButton.current?.focus({ preventScroll: true });
                }}
                className={({ isActive }) => `dock-more-link ${isActive ? 'active' : ''}`}
              >
                <span className="dock-icon">
                  <NavigationIcon path={item.path} icon={item.icon} />
                </span>
                <span className="dock-label" aria-hidden="true">
                  {item.name}
                </span>
              </NavLink>
            ))}
          </div>
        </>
      )}
    </nav>
  );
}

/** Play the chosen entrance on route changes, using the current dock position. */
export function PageView({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  const { navigation, pageTransition } = useInterfacePreferences();
  const view = useRef<HTMLDivElement>(null);
  const enter = useEffectEvent((element: HTMLDivElement) => {
    const anchor = document.querySelector(
      '.side-dock > [aria-current="page"], .side-dock > [data-current="true"]',
    );
    return playPageTransition(element, pageTransition, navigation, anchor);
  });

  useLayoutEffect(() => {
    window.scrollTo({ top: 0, behavior: 'instant' });
    if (!view.current) return;
    const motion = enter(view.current);
    return () => motion?.cancel();
  }, [pathname]);

  return (
    <div ref={view} className="page-view">
      {children}
    </div>
  );
}
