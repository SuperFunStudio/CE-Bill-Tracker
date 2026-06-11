import { SubscribeForm } from './SubscribeForm';

/**
 * "Get free updates" block — heading, blurb, and the subscribe form. Shared by the
 * About page and the home page so the two never drift.
 */
export function SubscribeSection({ className = '' }: { className?: string }) {
  return (
    <section id="get-updates" className={`scroll-mt-6 ${className}`}>
      <h2 className="font-serif text-text-primary text-2xl mb-2">
        Get the deadlines before they&apos;re emergencies.
      </h2>
      <p className="text-text-secondary leading-relaxed mb-5 max-w-2xl">
        Follow the materials and states you care about — we&apos;ll email you when matching
        legislation is introduced, advances, or hits a deadline. Free, and it stays free.
      </p>
      <SubscribeForm />
    </section>
  );
}
