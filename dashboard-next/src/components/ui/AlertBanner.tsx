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

export function AlertBanner({ message, variant = 'amber', className = '' }: AlertBannerProps) {
  return (
    <div className={`border rounded-lg p-3 text-sm ${VARIANTS[variant]} ${className}`}>
      {message}
    </div>
  );
}
