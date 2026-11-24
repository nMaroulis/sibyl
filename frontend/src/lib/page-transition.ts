export const pageTransitions = [
  { id: 'dock', label: 'Dock reveal', description: 'Spreads outward from the selected button.' },
  { id: 'slide', label: 'Slide', description: 'Glides in from the dock edge.' },
  { id: 'zoom', label: 'Soft zoom', description: 'Gently grows into place.' },
  { id: 'fade', label: 'Fade', description: 'Dissolves in place.' },
] as const;

export type PageTransition = (typeof pageTransitions)[number]['id'];
export type DockPlacement = 'left' | 'bottom';

export function isPageTransition(value: unknown): value is PageTransition {
  return pageTransitions.some(({ id }) => id === value);
}

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
  let easing = 'cubic-bezier(.16,1,.3,1)';

  switch (style) {
    case 'dock': {
      duration = 520;
      easing = 'cubic-bezier(.35,0,.2,1)';
      // Size the circle to the visible workspace so long pages reveal at the same pace.
      const height = within(window.innerHeight - bounds.top, bounds.height);
      const centerX = bottomDock ? x : 0;
      const centerY = within(bottomDock ? (origin?.top ?? bounds.bottom) - bounds.top : y, height);
      const radius = Math.hypot(
        Math.max(centerX, bounds.width - centerX),
        Math.max(centerY, height - centerY),
      );
      const center = `${centerX}px ${centerY}px`;
      frames = [
        { clipPath: `circle(0px at ${center})` },
        { clipPath: `circle(${Math.ceil(radius) + 2}px at ${center})` },
      ];
      break;
    }
    case 'slide': {
      duration = 380;
      easing = 'cubic-bezier(.2,.78,.26,1)';
      const distance = Math.min(104, Math.round((bottomDock ? bounds.height : bounds.width) * 0.3));
      frames = [
        { transform: bottomDock ? `translateY(${distance}px)` : `translateX(-${distance}px)` },
        { transform: 'none' },
      ];
      break;
    }
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
      duration = 470;
      easing = 'ease-in-out';
      frames = [{ opacity: 0 }, { opacity: 1 }];
      break;
  }

  const animation = element.animate(frames, { duration, easing });
  const cancel = () => animation.cancel();
  const clear = () => reducedMotion.removeEventListener('change', cancel);
  reducedMotion.addEventListener('change', cancel);
  animation.finished.then(clear, clear);
  return animation;
}
