import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        sans: ['var(--font-sans)', 'system-ui', 'sans-serif'],
        serif: ['var(--font-serif)', 'Georgia', 'Cambria', 'serif'],
      },
      colors: {
        'bg-primary':     'var(--bg-primary)',
        'bg-secondary':   'var(--bg-secondary)',
        'bg-tertiary':    'var(--bg-tertiary)',
        'border-default': 'var(--border-default)',
        'text-primary':   'var(--text-primary)',
        'text-secondary': 'var(--text-secondary)',
        'text-muted':     'var(--text-muted)',
        // Brand accent (blue in light mode, pink in dark — see globals.css).
        // Defined with the <alpha-value> placeholder so opacity modifiers work.
        'green-accent':   'rgb(var(--green-accent) / <alpha-value>)',
        'green-light':    'rgb(var(--green-light) / <alpha-value>)',
        'green-dark':     'rgb(var(--green-dark) / <alpha-value>)',
        'green-hero':     'rgb(var(--green-hero) / <alpha-value>)',
        'urgency-high':   '#ef4444',
        'urgency-medium': '#f59e0b',
        'urgency-low':    '#6b7280',
        'risk-high':      '#ef4444',
        'risk-medium':    '#f59e0b',
        'risk-low':       '#22c55e',
        // Canonical legislative-stage palette (see theme.css). Use these instead
        // of ad-hoc sky/amber/green so a status reads as one color everywhere.
        'status-introduced': 'var(--status-introduced)',
        'status-committee':  'var(--status-committee)',
        'status-advancing':  'var(--status-advancing)',
        'status-enacted':    'var(--status-enacted)',
        'status-weakens':    'var(--status-weakens)',
        'status-dormant':    'var(--status-dormant)',
      },
      borderRadius: {
        card:  'var(--radius-card)',
        panel: 'var(--radius-panel)',
      },
      boxShadow: {
        card:  'var(--shadow-card)',
        panel: 'var(--shadow-panel)',
      },
    },
  },
  plugins: [],
};
export default config;
