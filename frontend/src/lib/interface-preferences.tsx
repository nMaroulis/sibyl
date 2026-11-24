import { createContext, useContext, useState } from 'react';
import type { ReactNode } from 'react';
import { isPageTransition } from './page-transition';
import type { DockPlacement, PageTransition } from './page-transition';

type Preferences = {
  theme: 'light' | 'dark';
  navigation: DockPlacement;
  pageTransition: PageTransition;
  showLabels: boolean;
};
type InterfaceState = Preferences & { update: (preferences: Partial<Preferences>) => void };
const defaults: Preferences = {
  theme: 'light',
  navigation: 'left',
  pageTransition: 'dock',
  showLabels: true,
};
const storageKey = 'sibyl.interface';
const InterfaceContext = createContext<InterfaceState | null>(null);

function readPreferences(): Preferences {
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey) ?? 'null');
    return {
      theme: saved?.theme === 'dark' ? 'dark' : defaults.theme,
      navigation: saved?.navigation === 'bottom' ? 'bottom' : defaults.navigation,
      pageTransition: isPageTransition(saved?.pageTransition)
        ? saved.pageTransition
        : defaults.pageTransition,
      showLabels: typeof saved?.showLabels === 'boolean' ? saved.showLabels : defaults.showLabels,
    };
  } catch {
    return defaults;
  }
}

function applyPreferences({ theme, navigation }: Preferences) {
  document.documentElement.dataset.theme = theme;
  document.documentElement.dataset.navigation = navigation;
  document
    .querySelector('meta[name="theme-color"]')
    ?.setAttribute('content', theme === 'dark' ? '#101622' : '#eef1f6');
}

// Set the saved appearance before React mounts the workspace.
const initialPreferences = readPreferences();
applyPreferences(initialPreferences);

/** Browser-local presentation settings shared by Settings and the app shell. */
export function InterfaceProvider({ children }: { children: ReactNode }) {
  const [preferences, setPreferences] = useState(initialPreferences);
  const update = (changes: Partial<Preferences>) => {
    const next = { ...preferences, ...changes };
    applyPreferences(next);
    setPreferences(next);
    try {
      localStorage.setItem(storageKey, JSON.stringify(next));
    } catch {
      // Apply the choices for the current visit even when persistence is blocked.
    }
  };
  return (
    <InterfaceContext.Provider value={{ ...preferences, update }}>
      {children}
    </InterfaceContext.Provider>
  );
}

export function useInterfacePreferences() {
  const preferences = useContext(InterfaceContext);
  if (!preferences) throw new Error('InterfaceProvider is missing');
  return preferences;
}
