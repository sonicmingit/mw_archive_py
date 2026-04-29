export const THEME_STORAGE_KEY = 'mw_theme';

export type ThemeMode = 'light' | 'dark';

export function getStoredTheme(): ThemeMode {
  if (typeof window === 'undefined') {
    return 'light';
  }
  const value = window.localStorage.getItem(THEME_STORAGE_KEY);
  return value === 'dark' ? 'dark' : 'light';
}

export function applyTheme(mode: ThemeMode) {
  if (typeof document === 'undefined') {
    return;
  }
  const root = document.documentElement;
  if (mode === 'dark') {
    root.classList.add('dark');
  } else {
    root.classList.remove('dark');
  }
}

export function setStoredTheme(mode: ThemeMode) {
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(THEME_STORAGE_KEY, mode);
  }
  applyTheme(mode);
}

export function initTheme() {
  applyTheme(getStoredTheme());
}
