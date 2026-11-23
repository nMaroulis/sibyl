import { Check } from 'lucide-react';
import { useInterfacePreferences } from '../lib/interface-preferences';

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
  const { theme, navigation, showLabels, update } = useInterfacePreferences();
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
      </fieldset>
      <p className="footnote">Your choices apply immediately and are saved in this browser.</p>
    </div>
  );
}

function InterfacePreview({
  theme,
  navigation,
}: Pick<ReturnType<typeof useInterfacePreferences>, 'theme' | 'navigation'>) {
  return (
    <span
      className="interface-preview"
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
