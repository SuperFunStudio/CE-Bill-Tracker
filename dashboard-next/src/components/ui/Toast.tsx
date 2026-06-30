'use client';
import { useAuth } from '@/components/auth/AuthContext';

/** Global ephemeral confirmation toast, driven by useAuth().showToast. Fixed bottom-center, auto-
 *  dismisses (timer lives in AuthContext); click to dismiss early. Rendered once, near the app root. */
export function Toast() {
  const { toast, dismissToast } = useAuth();
  if (!toast) return null;
  return (
    <div className="fixed inset-x-0 bottom-6 z-[60] flex justify-center px-4 pointer-events-none">
      <div
        role="status"
        aria-live="polite"
        onClick={dismissToast}
        className="pointer-events-auto max-w-md cursor-pointer rounded-lg border border-green-accent/40 bg-bg-secondary px-4 py-3 text-sm text-text-primary shadow-2xl"
      >
        {toast}
      </div>
    </div>
  );
}
