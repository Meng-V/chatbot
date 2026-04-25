/**
 * v2 rollout flag.
 *
 * Decides whether this browser session routes to the new (v2) chatbot stack
 * or the legacy one. The legacy endpoint stays live for instant rollback --
 * flipping the flag off everywhere reverts without a deploy.
 *
 * Decision order (first match wins):
 *   1. URL query param `?v2=1` / `?v2=0`  -- explicit opt-in/opt-out, persisted
 *      to localStorage so reloads stay on the same stack.
 *   2. localStorage `smartchatbot_v2` ("on" | "off") -- sticky assignment.
 *   3. Percentage bucket driven by env var VITE_V2_ROLLOUT_PERCENT
 *      (0..100, default 0). A random 0..99 is drawn once per browser and
 *      persisted so a user's experience is stable across reloads.
 *
 * Path mapping:
 *   off -> /smartchatbot            (legacy socket.io path)
 *   on  -> /smartchatbot/v2         (new orchestrator)
 *
 * See plan: Rollout -> "Behind a flag".
 */

const STORAGE_KEY = 'smartchatbot_v2';
const BUCKET_KEY = 'smartchatbot_v2_bucket';

function readQueryOverride() {
  try {
    const params = new URLSearchParams(window.location.search);
    if (!params.has('v2')) return null;
    const raw = params.get('v2');
    if (raw === '1' || raw === 'on' || raw === 'true') return 'on';
    if (raw === '0' || raw === 'off' || raw === 'false') return 'off';
    return null;
  } catch {
    return null;
  }
}

function readStoredAssignment() {
  try {
    const v = window.localStorage.getItem(STORAGE_KEY);
    return v === 'on' || v === 'off' ? v : null;
  } catch {
    return null;
  }
}

function writeStoredAssignment(value) {
  try {
    window.localStorage.setItem(STORAGE_KEY, value);
  } catch {
    /* private mode / quota -- fall back to per-pageview bucketing */
  }
}

function stableBucket() {
  // Draw once, persist. Keeps the user's rollout cohort stable across
  // reloads so we don't flip-flop a single user between stacks.
  try {
    let bucket = window.localStorage.getItem(BUCKET_KEY);
    if (bucket === null) {
      bucket = String(Math.floor(Math.random() * 100));
      window.localStorage.setItem(BUCKET_KEY, bucket);
    }
    const n = Number(bucket);
    return Number.isFinite(n) ? n : Math.floor(Math.random() * 100);
  } catch {
    return Math.floor(Math.random() * 100);
  }
}

function rolloutPercent() {
  const raw = import.meta.env.VITE_V2_ROLLOUT_PERCENT;
  const n = Number(raw);
  if (!Number.isFinite(n)) return 0;
  return Math.max(0, Math.min(100, n));
}

/**
 * @returns {"on" | "off"}
 */
export function resolveV2Flag() {
  const query = readQueryOverride();
  if (query) {
    writeStoredAssignment(query);
    return query;
  }
  const stored = readStoredAssignment();
  if (stored) return stored;

  const decided = stableBucket() < rolloutPercent() ? 'on' : 'off';
  writeStoredAssignment(decided);
  return decided;
}

/**
 * Socket.IO path for this session's assigned stack.
 * Legacy stays at `/smartchatbot/socket.io`; v2 users hit `/smartchatbot/v2/socket.io`.
 */
export function socketIoPathForFlag(flag) {
  return flag === 'on'
    ? '/smartchatbot/v2/socket.io'
    : '/smartchatbot/socket.io';
}
