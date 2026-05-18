// Frontend Sentry error tracking (plan Op 3 -> "Sentry browser SDK in
// client/ for JS exceptions and source-mapped stack traces").
// Counterpart to the backend src/observability/sentry.py; the plan
// flags Sentry on BOTH backend and frontend as non-negotiable on
// launch day -- without it, a broken deploy is reported by angry
// students, not by us.
//
// Safety contract (so this is mergeable before a DSN exists):
//   * No VITE_SENTRY_DSN          -> complete no-op.
//   * @sentry/react fails to load -> caught, app still renders.
//   * Idempotent (HMR / re-import safe).
// Merging this changes runtime behavior by exactly zero until an
// operator sets VITE_SENTRY_DSN.
//
// Privacy: sendDefaultPii:false -- this bot handles student questions;
// we do not ship message bodies / IPs to a third party. Tracing
// defaults to 0 (errors only); perf is opt-in via env.
//
// The @sentry/react import is dynamic so it's code-split OUT of the
// main bundle and only fetched when a DSN is actually configured.

let _initialized = false;

export async function initSentry() {
  if (_initialized) return true;

  const dsn = import.meta.env.VITE_SENTRY_DSN;
  if (!dsn) {
    // Quiet by design: dev/preview without a DSN is the normal case.
    return false;
  }

  try {
    const Sentry = await import('@sentry/react');
    let tracesSampleRate = Number(
      import.meta.env.VITE_SENTRY_TRACES_SAMPLE_RATE ?? 0,
    );
    if (!Number.isFinite(tracesSampleRate)) tracesSampleRate = 0;

    Sentry.init({
      dsn,
      environment: import.meta.env.MODE,
      release: import.meta.env.VITE_SENTRY_RELEASE || undefined,
      tracesSampleRate,
      // Never ship message bodies / headers / IPs.
      sendDefaultPii: false,
    });
    _initialized = true;
    return true;
  } catch (e) {
    // A missing dep or a bad init must NOT take the chat UI down.
    // eslint-disable-next-line no-console
    console.warn('Sentry init skipped:', e?.message || e);
    return false;
  }
}

export function isSentryInitialized() {
  return _initialized;
}
