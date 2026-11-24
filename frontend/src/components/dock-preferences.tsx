import { Check, LockKeyhole, Plus } from 'lucide-react';
import { useInterfacePreferences } from '../lib/interface-preferences';
import { destinations, dockStyles } from '../lib/navigation-options';
import type { DestinationPath } from '../lib/navigation-options';

export function DockPreferences() {
  const { dockStyle, pinnedPaths, update } = useInterfacePreferences();

  const setPinned = (path: DestinationPath, pinned: boolean) => {
    update({
      pinnedPaths: pinned ? [...pinnedPaths, path] : pinnedPaths.filter((item) => item !== path),
    });
  };

  return (
    <>
      <fieldset className="interface-group dock-settings-group">
        <legend>Dock style</legend>
        <div className="dock-style-options">
          {dockStyles.map(({ id, label }) => (
            <label className="interface-option dock-style-option" key={id}>
              <input
                type="radio"
                name="interface-dock-style"
                checked={dockStyle === id}
                onChange={() => update({ dockStyle: id })}
              />
              <span className="dock-style-preview" aria-hidden="true">
                <span className="dock-style-sample" data-dock-style={id}>
                  {destinations.slice(0, 3).map(({ path, icon: Icon }) => (
                    <span key={path}>
                      <Icon size={12} />
                    </span>
                  ))}
                </span>
              </span>
              <span>{label}</span>
              <Check size={15} className="interface-check" aria-hidden="true" />
            </label>
          ))}
        </div>
      </fieldset>
      <fieldset className="interface-group dock-settings-group">
        <legend>Dock shortcuts</legend>
        <p className="footnote dock-shortcuts-note">
          Account is always pinned. Unpinned shortcuts go to More.
        </p>
        <div className="dock-shortcut-options">
          {destinations.map(({ path, name, icon: Icon }) => {
            const pinned = pinnedPaths.includes(path);
            const locked = path === '/account';
            const Status = locked ? LockKeyhole : pinned ? Check : Plus;
            return (
              <label className="interface-option dock-shortcut-option" key={path}>
                <input
                  type="checkbox"
                  checked={pinned}
                  disabled={locked}
                  onChange={(event) => setPinned(path, event.currentTarget.checked)}
                />
                <Icon size={16} aria-hidden="true" />
                <span>{name}</span>
                <Status size={13} className="dock-shortcut-status" aria-hidden="true" />
              </label>
            );
          })}
        </div>
      </fieldset>
    </>
  );
}
