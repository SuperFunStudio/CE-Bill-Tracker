'use client';
import { createContext, useContext, useEffect, useState } from 'react';

type Theme = 'light' | 'dark';

const ThemeContext = createContext<{ theme: Theme; toggle: () => void }>({
  theme: 'light',
  toggle: () => {},
});

// Apply a theme to the DOM: the .dark class AND the <meta name="theme-color"> (so the mobile browser
// chrome tracks the toggle, not just the OS setting). Kept in sync with the pre-paint script in layout.
function applyTheme(t: Theme) {
  document.documentElement.classList.toggle('dark', t === 'dark');
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute('content', t === 'dark' ? '#111827' : '#ffffff');
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setTheme] = useState<Theme>('light');

  // The pre-paint script in layout.tsx already resolved + applied the theme (localStorage, else OS
  // preference) before hydration. Read what it applied so React state matches the DOM — no default
  // that would flip the toggle icon or re-trigger a flash.
  useEffect(() => {
    setTheme(document.documentElement.classList.contains('dark') ? 'dark' : 'light');
  }, []);

  const toggle = () => {
    setTheme(prev => {
      const next = prev === 'light' ? 'dark' : 'light';
      localStorage.setItem('theme', next);
      applyTheme(next);
      return next;
    });
  };

  return (
    <ThemeContext.Provider value={{ theme, toggle }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  return useContext(ThemeContext);
}
