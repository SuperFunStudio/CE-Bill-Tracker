'use client';
import { useState } from 'react';
import { useAuth } from './AuthContext';

/** Global sign-in / create-account modal, opened via useAuth().openAuth(). Email + Google. */
export function AuthModal() {
  const { authModalOpen, closeAuth, signInEmail, signUpEmail, signInGoogle, signInMicrosoft, resendVerification, resetPassword } = useAuth();
  const [mode, setMode] = useState<'signin' | 'signup'>('signin');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [verifySent, setVerifySent] = useState(false);
  const [resent, setResent] = useState(false);
  const [resetSent, setResetSent] = useState(false);

  if (!authModalOpen) return null;

  function dismiss() {
    setVerifySent(false);
    setResent(false);
    setResetSent(false);
    setError('');
    closeAuth();
  }

  async function forgotPassword() {
    setError('');
    const addr = email.trim();
    if (!addr) {
      setError('Enter your email above, then tap “Forgot password?”.');
      return;
    }
    setBusy(true);
    try {
      await resetPassword(addr);
    } catch (err) {
      // Surface a malformed address, but stay neutral on user-not-found so the form can't be used to
      // probe which emails have accounts.
      if ((err as { code?: string })?.code === 'auth/invalid-email') {
        setError('That doesn’t look like a valid email.');
        setBusy(false);
        return;
      }
    }
    setResetSent(true);
    setBusy(false);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      if (mode === 'signin') {
        await signInEmail(email.trim(), password);
        closeAuth();
      } else {
        // Email/password signup sends a verification link; the 7-day trial + any referral land once
        // it's verified (H-2). Keep the modal open with a "check your email" notice instead of closing.
        await signUpEmail(email.trim(), password);
        setVerifySent(true);
      }
    } catch (err) {
      setError(friendlyError(err));
    } finally {
      setBusy(false);
    }
  }

  async function google() {
    setBusy(true);
    setError('');
    try {
      await signInGoogle();
      closeAuth();
    } catch (err) {
      setError(friendlyError(err));
    } finally {
      setBusy(false);
    }
  }

  async function microsoft() {
    setBusy(true);
    setError('');
    try {
      await signInMicrosoft();
      closeAuth();
    } catch (err) {
      setError(friendlyError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      onClick={dismiss}
    >
      <div
        className="w-full max-w-md rounded-xl bg-bg-secondary border border-border-default shadow-2xl p-6 space-y-4"
        onClick={e => e.stopPropagation()}
      >
        {verifySent ? (
          <div className="space-y-4 text-center">
            <h2 className="font-serif text-xl text-text-primary">Check your email</h2>
            <p className="text-text-secondary text-sm leading-relaxed">
              We sent a verification link to <span className="text-text-primary font-medium">{email}</span>.
              Click it to confirm your address — your free 7-day Pro trial unlocks automatically the
              moment you do.
            </p>
            <button
              onClick={async () => { try { await resendVerification(); setResent(true); } catch { /* ignore */ } }}
              className="text-green-accent text-sm hover:underline"
            >
              {resent ? 'Verification email resent ✓' : 'Resend the email'}
            </button>
            <button
              onClick={dismiss}
              className="w-full bg-green-accent text-bg-primary font-semibold px-5 py-2 rounded-lg text-sm hover:opacity-90 transition-opacity"
            >
              Got it
            </button>
          </div>
        ) : (
        <>
        <div>
          <h2 className="font-serif text-xl text-text-primary">
            {mode === 'signin' ? 'Sign in' : 'Create your account'}
          </h2>
          <p className="text-text-muted text-sm mt-1">
            {mode === 'signin'
              ? 'Access your Pro features and the full Design Guide.'
              : 'Create a free account — upgrade to Pro when you need the full guide.'}
          </p>
        </div>

        <button
          onClick={google}
          disabled={busy}
          className="w-full flex items-center justify-center gap-2 rounded-lg border border-border-default bg-bg-primary px-4 py-2 text-sm font-medium text-text-primary hover:border-green-accent transition-colors disabled:opacity-60"
        >
          <GoogleGlyph />
          Continue with Google
        </button>

        <button
          onClick={microsoft}
          disabled={busy}
          className="w-full flex items-center justify-center gap-2 rounded-lg border border-border-default bg-bg-primary px-4 py-2 text-sm font-medium text-text-primary hover:border-green-accent transition-colors disabled:opacity-60"
        >
          <MicrosoftGlyph />
          Continue with Microsoft
        </button>

        <div className="flex items-center gap-3 text-text-muted text-xs">
          <span className="h-px flex-1 bg-border-default" /> or <span className="h-px flex-1 bg-border-default" />
        </div>

        <form onSubmit={submit} className="space-y-3">
          <div className="flex flex-col gap-1">
            <label className="text-text-muted text-xs uppercase">Email</label>
            <input
              type="email"
              required
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="you@company.com"
              className="bg-bg-primary border border-border-default rounded px-3 py-2 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-green-accent"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-text-muted text-xs uppercase">Password</label>
            <input
              type="password"
              required
              minLength={6}
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="At least 6 characters"
              className="bg-bg-primary border border-border-default rounded px-3 py-2 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-green-accent"
            />
          </div>
          {error && <p className="text-urgency-high text-sm">{error}</p>}
          {resetSent && (
            <p className="text-green-accent text-sm">
              If an account exists for that email, we’ve sent a password-reset link. Check your inbox.
            </p>
          )}
          <button
            type="submit"
            disabled={busy}
            className="w-full bg-green-accent text-bg-primary font-semibold px-5 py-2 rounded-lg text-sm hover:opacity-90 transition-opacity disabled:opacity-60"
          >
            {busy ? 'Please wait…' : mode === 'signin' ? 'Sign in' : 'Create account'}
          </button>
          {mode === 'signin' && (
            <button
              type="button"
              onClick={forgotPassword}
              disabled={busy}
              className="text-text-muted text-xs hover:text-green-accent transition-colors disabled:opacity-60"
            >
              Forgot password?
            </button>
          )}
        </form>

        <div className="flex items-center justify-between text-xs">
          <button
            onClick={() => { setMode(mode === 'signin' ? 'signup' : 'signin'); setError(''); setResetSent(false); }}
            className="text-green-accent hover:underline"
          >
            {mode === 'signin' ? 'Need an account? Sign up' : 'Have an account? Sign in'}
          </button>
          <button onClick={dismiss} className="text-text-muted hover:text-text-secondary">
            Cancel
          </button>
        </div>
        </>
        )}
      </div>
    </div>
  );
}

function GoogleGlyph() {
  return (
    <svg width="16" height="16" viewBox="0 0 48 48" aria-hidden>
      <path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9.1 3.6l6.8-6.8C35.6 2.4 30.2 0 24 0 14.6 0 6.4 5.4 2.6 13.2l7.9 6.1C12.3 13.2 17.7 9.5 24 9.5Z" />
      <path fill="#4285F4" d="M46.5 24.5c0-1.6-.1-3.1-.4-4.5H24v9h12.7c-.5 3-2.2 5.5-4.7 7.2l7.3 5.7C43.7 37.7 46.5 31.7 46.5 24.5Z" />
      <path fill="#FBBC05" d="M10.5 28.3a14.5 14.5 0 0 1 0-8.6l-7.9-6.1a24 24 0 0 0 0 20.8l7.9-6.1Z" />
      <path fill="#34A853" d="M24 48c6.5 0 11.9-2.1 15.9-5.8l-7.3-5.7c-2 1.4-4.7 2.3-8.6 2.3-6.3 0-11.7-3.7-13.5-9.1l-7.9 6.1C6.4 42.6 14.6 48 24 48Z" />
    </svg>
  );
}

function MicrosoftGlyph() {
  return (
    <svg width="16" height="16" viewBox="0 0 23 23" aria-hidden>
      <path fill="#F25022" d="M0 0h11v11H0z" />
      <path fill="#7FBA00" d="M12 0h11v11H12z" />
      <path fill="#00A4EF" d="M0 12h11v11H0z" />
      <path fill="#FFB900" d="M12 12h11v11H12z" />
    </svg>
  );
}

function friendlyError(err: unknown): string {
  const code = (err as { code?: string })?.code ?? '';
  switch (code) {
    case 'auth/invalid-credential':
    case 'auth/wrong-password':
    case 'auth/user-not-found':
      return 'Email or password is incorrect.';
    case 'auth/email-already-in-use':
      return 'That email already has an account — try signing in.';
    case 'auth/weak-password':
      return 'Password should be at least 6 characters.';
    case 'auth/popup-closed-by-user':
      return 'Sign-in was cancelled.';
    case 'auth/operation-not-allowed':
      return 'This sign-in method isn’t enabled yet.';
    default:
      return err instanceof Error ? err.message : 'Something went wrong.';
  }
}
