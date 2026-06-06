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
      colors: {
        'bg-primary':     'var(--bg-primary)',
        'bg-secondary':   'var(--bg-secondary)',
        'bg-tertiary':    'var(--bg-tertiary)',
        'border-default': 'var(--border-default)',
        'text-primary':   'var(--text-primary)',
        'text-secondary': 'var(--text-secondary)',
        'text-muted':     'var(--text-muted)',
        'green-accent':   'var(--green-accent)',
        'green-light':    'var(--green-light)',
        'green-dark':     'var(--green-dark)',
        'green-hero':     'var(--green-hero)',
        'urgency-high':   '#ef4444',
        'urgency-medium': '#f59e0b',
        'urgency-low':    '#6b7280',
        'risk-high':      '#ef4444',
        'risk-medium':    '#f59e0b',
        'risk-low':       '#22c55e',
      },
    },
  },
  plugins: [],
};
export default config;
