export const pageTransitions = [
  { id: 'dock', label: 'Dock reveal', description: 'Unfolds from the selected dock button.' },
  { id: 'slide', label: 'Slide', description: 'Moves in from the dock edge.' },
  { id: 'zoom', label: 'Soft zoom', description: 'Gently grows into place.' },
  { id: 'fade', label: 'Fade', description: 'Appears with no movement.' },
] as const;

export type PageTransition = (typeof pageTransitions)[number]['id'];
export type DockPlacement = 'left' | 'bottom';

export function isPageTransition(value: unknown): value is PageTransition {
  return pageTransitions.some(({ id }) => id === value);
}

const fullPage = 'inset(0px 0px 0px 0px round 0px)';
const easing = 'cubic-bezier(.16,1,.3,1)';
const within = (value: number, length: number) => Math.max(0, Math.min(length, value));

/** Play the same transition on the workspace or on a miniature in Settings. */
export function playPageTransition(
  element: HTMLElement,
  style: PageTransition,
  placement: DockPlacement,
  anchor: Element | null = null,
) {
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  if (!element.animate || reducedMotion.matches) return;

  const bounds = element.getBoundingClientRect();
  const origin = anchor?.getBoundingClientRect();
  const bottomDock = placement === 'bottom';
  const x = origin
    ? within(origin.left + origin.width / 2 - bounds.left, bounds.width)
    : bounds.width / 2;
  const y = origin
    ? within(origin.top + origin.height / 2 - bounds.top, bounds.height)
    : bounds.height / 2;
  let frames: Keyframe[];
  let duration: number;

  switch (style) {
    case 'dock':
      duration = bottomDock ? 460 : 580;
      if (bottomDock) {
        // On a long page, begin at the visible dock edge rather than below the viewport.
        const edge = origin ? within(origin.top - bounds.top, bounds.height) : bounds.height;
        const radius = Math.min(48, bounds.width / 5);
        const left = Math.max(0, x - radius);
        const right = Math.max(0, bounds.width - x - radius);
        const top = Math.max(0, edge - Math.min(34, bounds.height / 3));
        frames = [
          {
            clipPath: `inset(${top}px ${right}px ${bounds.height - edge}px ${left}px round 20px)`,
            opacity: 0.35,
            transform: 'translateY(10px)',
          },
          {
            clipPath: `inset(${edge * 0.16}px 0px 0px 0px round 12px)`,
            opacity: 0.9,
            transform: 'translateY(2px)',
            offset: 0.45,
          },
          { clipPath: fullPage, opacity: 1, transform: 'translateY(0)' },
        ];
      } else {
        const top = Math.max(0, y - 30);
        const bottom = Math.max(0, bounds.height - y - 30);
        const right = Math.max(0, bounds.width - 24);
        frames = [
          {
            clipPath: `inset(${top}px ${right}px ${bottom}px 0px round 18px)`,
            opacity: 0.3,
            transform: 'translateX(-12px)',
          },
          { clipPath: fullPage, opacity: 1, transform: 'translateX(0)' },
        ];
      }
      break;
    case 'slide':
      duration = 300;
      frames = [
        { opacity: 0.55, transform: bottomDock ? 'translateY(24px)' : 'translateX(-24px)' },
        { opacity: 1, transform: 'none' },
      ];
      break;
    case 'zoom': {
      duration = 330;
      const transformOrigin = bottomDock ? `${x}px bottom` : `left ${y}px`;
      frames = [
        { opacity: 0.45, transform: 'scale(.96)', transformOrigin },
        { opacity: 1, transform: 'scale(1)', transformOrigin },
      ];
      break;
    }
    case 'fade':
      duration = 230;
      frames = [{ opacity: 0.25 }, { opacity: 1 }];
      break;
  }

  const animation = element.animate(frames, { duration, easing });
  const cancel = () => animation.cancel();
  const clear = () => reducedMotion.removeEventListener('change', cancel);
  reducedMotion.addEventListener('change', cancel);
  animation.finished.then(clear, clear);
  return animation;
}
