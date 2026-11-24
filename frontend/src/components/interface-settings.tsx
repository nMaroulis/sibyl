import { Check, Play } from 'lucide-react';
import { useEffect, useRef } from 'react';
import type { Ref } from 'react';
import { DockPreferences } from './dock-preferences';
import { useInterfacePreferences } from '../lib/interface-preferences';
import { pageTransitions, playPageTransition } from '../lib/page-transition';
import type { PageTransition } from '../lib/page-transition';

const themes = [
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' },
] as const;
const placements = [
  { value: 'left', label: 'Left' },
  { value: 'bottom', label: 'Bottom' },
] as const;

/** Live previews and controls for appearance and navigation preferences. */
export function InterfaceSettings() {
  const { theme, navigation, showLabels, pageTransition, update } = useInterfacePreferences();
  const preview = useRef<HTMLSpanElement>(null);
  const previewAnimation = useRef<Animation | undefined>(undefined);
  useEffect(() => () => previewAnimation.current?.cancel(), []);

  const playPreview = (style: PageTransition) => {
    const content = preview.current?.querySelector<HTMLElement>('.interface-preview-content');
    if (!content) return;
    previewAnimation.current?.cancel();
    const anchor = preview.current?.querySelector('.interface-preview-dock i:first-child');
    previewAnimation.current = playPageTransition(content, style, navigation, anchor);
  };

  return (
    <div className="interface-settings">
      <fieldset className="interface-group">
        <legend>Appearance</legend>
        <div className="interface-options">
          {themes.map(({ value, label }) => (
            <label className="interface-option" key={value}>
              <input
                type="radio"
                name="interface-theme"
                value={value}
                checked={theme === value}
                onChange={() => update({ theme: value })}
              />
              <InterfacePreview theme={value} navigation={navigation} />
              <span>{label}</span>
              <Check size={15} className="interface-check" aria-hidden="true" />
            </label>
          ))}
        </div>
      </fieldset>
      <fieldset className="interface-group">
        <legend>Navigation</legend>
        <div className="interface-options">
          {placements.map(({ value, label }) => (
            <label className="interface-option" key={value}>
              <input
                type="radio"
                name="interface-navigation"
                value={value}
                checked={navigation === value}
                onChange={() => update({ navigation: value })}
              />
              <InterfacePreview theme={theme} navigation={value} />
              <span>{label}</span>
              <Check size={15} className="interface-check" aria-hidden="true" />
            </label>
          ))}
        </div>
        <label className="interface-label-switch">
          <span>Show labels</span>
          <input
            type="checkbox"
            role="switch"
            checked={showLabels}
            onChange={(event) => update({ showLabels: event.currentTarget.checked })}
          />
        </label>
        <DockPreferences />
      </fieldset>
      <fieldset className="interface-group">
        <legend>Page transition</legend>
        <div className="interface-transition">
          <div className="interface-options">
            {pageTransitions.map(({ id, label, description }) => (
              <label className="interface-option interface-transition-option" key={id}>
                <input
                  type="radio"
                  name="interface-page-transition"
                  value={id}
                  checked={pageTransition === id}
                  onChange={() => {
                    update({ pageTransition: id });
                    playPreview(id);
                  }}
                />
                <span>
                  <strong>{label}</strong>
                  <small>{description}</small>
                </span>
                <Check size={15} className="interface-check" aria-hidden="true" />
              </label>
            ))}
          </div>
          <div className="interface-motion-sample">
            <InterfacePreview theme={theme} navigation={navigation} previewRef={preview} />
            <button
              type="button"
              className="button secondary tiny interface-motion-play"
              onClick={() => playPreview(pageTransition)}
            >
              <Play size={13} aria-hidden="true" /> Preview
            </button>
            <p className="footnote interface-motion-reduced">
              Your device has reduced motion enabled.
            </p>
          </div>
        </div>
      </fieldset>
      <p className="footnote">Your choices apply immediately and are saved in this browser.</p>
    </div>
  );
}

function InterfacePreview({
  theme,
  navigation,
  previewRef,
}: Pick<ReturnType<typeof useInterfacePreferences>, 'theme' | 'navigation'> & {
  previewRef?: Ref<HTMLSpanElement>;
}) {
  return (
    <span
      className="interface-preview"
      ref={previewRef}
      data-preview-theme={theme}
      data-preview-dock={navigation}
      aria-hidden="true"
    >
      <span className="interface-preview-content">
        <i />
        <i />
        <i />
      </span>
      <span className="interface-preview-dock">
        <i />
        <i />
        <i />
      </span>
    </span>
  );
}
