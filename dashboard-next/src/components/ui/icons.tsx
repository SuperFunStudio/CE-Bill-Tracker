import type { SVGProps } from 'react';

/**
 * Minimal monochrome line icons used across the UI in place of color emoji, so
 * everything reads in the same editorial "Gazette" voice. All icons draw with
 * `currentColor` and inherit size from `className` (default 1em), so they pick
 * up the surrounding text color/weight automatically.
 */
type IconProps = SVGProps<SVGSVGElement>;

function Icon({ children, ...props }: IconProps & { children: React.ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      width="1em"
      height="1em"
      aria-hidden
      {...props}
    >
      {children}
    </svg>
  );
}

export function HomeIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M4 11.5 12 4l8 7.5" />
      <path d="M6 10v9h12v-9" />
      <path d="M10 19v-5h4v5" />
    </Icon>
  );
}

export function CalendarIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <rect x="4" y="5" width="16" height="16" rx="1.5" />
      <path d="M4 9h16M8 3v4M16 3v4" />
    </Icon>
  );
}

/** Classical pillared building — stands in for federal / capitol actions. */
export function CapitolIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M12 3 4 7h16L12 3Z" />
      <path d="M6 10v7M10 10v7M14 10v7M18 10v7" />
      <path d="M3 20h18M4 17h16" />
    </Icon>
  );
}

/** Industrial building — stands in for company / facility impact. */
export function FactoryIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M3 20V10l6 4V10l6 4V6h3v14" />
      <path d="M3 20h18" />
      <path d="M7 17h.01M11 17h.01M15 17h.01" />
    </Icon>
  );
}

export function InfoIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 11v5" />
      <path d="M12 8h.01" />
    </Icon>
  );
}

export function LockIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <rect x="5" y="11" width="14" height="9" rx="1.5" />
      <path d="M8 11V8a4 4 0 0 1 8 0v3" />
      <path d="M12 15v2" />
    </Icon>
  );
}

export function CheckIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M4 12.5 9 17.5 20 6.5" />
    </Icon>
  );
}

export function StarIcon(props: IconProps) {
  return (
    <Icon {...props} fill="currentColor" stroke="none">
      <path d="M12 3.5l2.47 5.36 5.86.62-4.37 3.94 1.22 5.76L12 16.9l-5.18 2.78 1.22-5.76-4.37-3.94 5.86-.62L12 3.5Z" />
    </Icon>
  );
}

export function AlertIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M10.3 3.9 1.9 18a2 2 0 0 0 1.7 3h16.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" />
      <path d="M12 9v4" />
      <path d="M12 17h.01" />
    </Icon>
  );
}

export function HeartIcon(props: IconProps) {
  return (
    <Icon {...props} fill="currentColor" stroke="none">
      <path d="M12 20s-7-4.35-9.5-8.5C1 8.5 2.5 5.5 5.5 5.5c1.8 0 3 .9 3.7 2 .7-1.1 1.9-2 3.7-2 3 0 4.5 3 2.6 6-2.5 4.15-9.5 8.5-9.5 8.5Z" transform="translate(0.3 0)" />
    </Icon>
  );
}

export function PlayIcon(props: IconProps) {
  return (
    <Icon {...props} fill="currentColor" stroke="none">
      <path d="M7 5.5v13l11-6.5-11-6.5Z" />
    </Icon>
  );
}

export function PauseIcon(props: IconProps) {
  return (
    <Icon {...props} fill="currentColor" stroke="none">
      <rect x="6.5" y="5" width="3.5" height="14" rx="0.5" />
      <rect x="14" y="5" width="3.5" height="14" rx="0.5" />
    </Icon>
  );
}

/** Price tag — stands in for pricing / plans. */
export function TagIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M3 12V4h8l9 9-8 8-9-9Z" />
      <circle cx="7.5" cy="7.5" r="1.4" fill="currentColor" stroke="none" />
    </Icon>
  );
}

export function SunIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </Icon>
  );
}

export function MoonIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M20 14.5A8 8 0 0 1 9.5 4a7 7 0 1 0 10.5 10.5Z" />
    </Icon>
  );
}
