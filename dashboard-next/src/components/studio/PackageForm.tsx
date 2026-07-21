import type { ReactNode } from 'react';

/**
 * The packaging *forms* a component can take — the vector line-drawings that let you
 * see what you're building. Form is presentation-only: the fee is charged on material +
 * weight, never on shape. So a component carries an optional `form`; when unset we infer
 * a sensible default from its material category (a paper component looks like a carton),
 * and the picker lets the designer override it (this PET is a tub, not a bottle).
 */
export type PackageForm =
  | 'bottle' | 'jar' | 'pouch' | 'carton' | 'can' | 'tub' | 'film' | 'cap' | 'box';

export const PACKAGE_FORMS: { id: PackageForm; label: string }[] = [
  { id: 'bottle', label: 'Bottle' },
  { id: 'jar', label: 'Jar' },
  { id: 'pouch', label: 'Pouch' },
  { id: 'carton', label: 'Carton' },
  { id: 'can', label: 'Can' },
  { id: 'tub', label: 'Tub' },
  { id: 'film', label: 'Film' },
  { id: 'cap', label: 'Cap' },
  { id: 'box', label: 'Box' },
];

/** Default form per canonical material category — the drawing you get before you pick one. */
const CATEGORY_FORM: Record<string, PackageForm> = {
  plastic_packaging: 'bottle',
  pet_bottle_packaging: 'bottle',
  plastic_film: 'pouch',
  paper_packaging: 'carton',
  glass_packaging: 'jar',
  aluminum_packaging: 'can',
  wood_packaging: 'box',
  other_packaging: 'box',
};

export function formForCategory(category: string | undefined): PackageForm {
  return (category && CATEGORY_FORM[category]) || 'box';
}

// Line-art per form, drawn in a 0 0 40 40 viewBox with stroke=currentColor so the caller
// controls size (via width/height) and color (via text-* — neutral, or a warn tint for a
// hard-to-recycle part). fill:none keeps them honest outlines, not filled icons.
const PATHS: Record<PackageForm, ReactNode> = {
  bottle: (
    <>
      <rect x="15" y="4" width="10" height="6" rx="1" />
      <path d="M15 10 C11 12 9 15 9 20 L9 33 C9 36 11 37 14 37 L26 37 C29 37 31 36 31 33 L31 20 C31 15 29 12 25 10 Z" />
    </>
  ),
  jar: (
    <>
      <path d="M9 15 C9 12 11 11 14 11 L26 11 C29 11 31 12 31 15 L31 33 C31 36 29 37 26 37 L14 37 C11 37 9 36 9 33 Z" />
      <path d="M13 11 L13 6 L27 6 L27 11" />
    </>
  ),
  pouch: (
    <>
      <path d="M11 9 L29 9 L31 33 C31 36 29 37 26 37 L14 37 C11 37 9 36 9 33 Z" />
      <path d="M13 9 L13 5 L27 5 L27 9" />
    </>
  ),
  carton: (
    <>
      <path d="M12 15 L20 7 L28 15 L28 34 L12 34 Z" />
      <path d="M20 7 L20 15" />
      <path d="M12 15 L28 15" />
    </>
  ),
  can: (
    <>
      <path d="M11 10 C11 8 15 7 20 7 C25 7 29 8 29 10 L29 32 C29 34 25 35 20 35 C15 35 11 34 11 32 Z" />
      <path d="M11 10 C11 12 15 13 20 13 C25 13 29 12 29 10" />
    </>
  ),
  tub: (
    <>
      <path d="M12 11 L28 11 L26 35 C26 36 25 37 24 37 L16 37 C15 37 14 36 14 35 Z" />
      <line x1="10" y1="11" x2="30" y2="11" />
    </>
  ),
  film: (
    <>
      <path d="M10 13 L26 13 C30 13 32 16 32 20 C32 24 30 27 26 27 L10 27 Z" />
      <path d="M26 13 C22 13 20 16 20 20 C20 24 22 27 26 27" />
      <line x1="10" y1="13" x2="10" y2="27" />
    </>
  ),
  cap: (
    <>
      <rect x="12" y="13" width="16" height="14" rx="2" />
      <line x1="16" y1="16" x2="16" y2="24" />
      <line x1="20" y1="16" x2="20" y2="24" />
      <line x1="24" y1="16" x2="24" y2="24" />
    </>
  ),
  box: (
    <>
      <path d="M8 14 L20 8 L32 14 L32 32 L20 38 L8 32 Z" />
      <path d="M8 14 L20 20 L32 14" />
      <path d="M20 20 L20 38" />
    </>
  ),
};

/** A single packaging-form line drawing. Size it with width/height utility classes on
 *  `className`; color it by setting a text color there (neutral, or a warn tint). */
export function PackageGlyph({ form, className }: { form: string; className?: string }) {
  const f = (form in PATHS ? form : 'box') as PackageForm;
  return (
    <svg
      viewBox="0 0 40 40"
      fill="none"
      stroke="currentColor"
      strokeWidth={3.2}
      strokeLinejoin="round"
      strokeLinecap="round"
      className={className}
      aria-hidden
    >
      {PATHS[f]}
    </svg>
  );
}
