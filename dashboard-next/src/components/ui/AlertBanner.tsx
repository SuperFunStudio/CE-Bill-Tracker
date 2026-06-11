import { AlertIcon } from './icons';

interface AlertBannerProps {
  message: string;
  variant?: 'red' | 'amber' | 'green' | 'blue';
  className?: string;
}

const VARIANTS = {
  red:   'bg-red-100   border-red-400   text-red-800   dark:bg-red-900/50   dark:border-red-700   dark:text-red-200',
  amber: 'bg-amber-100 border-amber-400 text-amber-800 dark:bg-amber-900/50 dark:border-amber-700 dark:text-amber-200',
  green: 'bg-green-dark border-green-accent/30 text-green-accent dark:bg-green-dark dark:border-green-accent/30 dark:text-green-light',
  blue:  'bg-blue-100  border-blue-400  text-blue-800  dark:bg-blue-900/50  dark:border-blue-700  dark:text-blue-200',
};

// Warning variants lead with the line alert icon; green/blue read as success/info, so no icon.
const WARNS = new Set(['red', 'amber']);

export function AlertBanner({ message, variant = 'amber', className = '' }: AlertBannerProps) {
  return (
    <div className={`flex items-start gap-2 border rounded-lg p-3 text-sm ${VARIANTS[variant]} ${className}`}>
      {WARNS.has(variant) && <AlertIcon className="text-base shrink-0 mt-0.5" />}
      <span>{message}</span>
    </div>
  );
}
