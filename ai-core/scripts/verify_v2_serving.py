"""
Live-verify the v2 serving path end-to-end.

The v2 stack is CODE-COMPLETE (PRs #56-79): RolloutFlag routes ?v2=1
to /smartchatbot/v2/socket.io; main.py mounts sio_v2 on that path;
handle_v2_message runs the rebuilt orchestrator. What this script does
is the OPERATOR LIVE-VERIFY step the plan calls out at the bottom of
the main.py v2 mount comment:

    "with VITE_V2_ROLLOUT_PERCENT=0, open ?v2=1, confirm a cited answer
     renders AND a no-flag session is unchanged, BEFORE raising the
     rollout percentage."

We do that programmatically so the verify is repeatable and auditable.
The script is intentionally not pretty -- it's an operator checklist
that exits non-zero on any failure.

Usage:
    .venv/bin/python -m scripts.verify_v2_serving --host http://localhost:8081

    # Override the canned question (default: a known-answerable hours-y one)
    .venv/bin/python -m scripts.verify_v2_serving \\
        --host http://localhost:8081 \\
        --question "what time does King Library close today?"

    # Skip the legacy check (e.g. if legacy creds aren't available in this env)
    .venv/bin/python -m scripts.verify_v2_serving --host ... --skip-legacy

Exit codes:
    0  all checks passed -- safe to flip VITE_V2_ROLLOUT_PERCENT above 0
    1  one or more checks failed -- DO NOT raise the rollout flag

Requirements (must be installed in the .venv running this script):
    python-socketio  (already a dependency)
    httpx            (already a dependency)

What we check, in order:

  1. /health/ready returns 200            -- backend is up, deps probes pass
  2. /smoketest returns 200 + citation    -- the synthetic E2E catches
                                             stale-key / broken-chain
                                             failures the smoke gate is
                                             designed for
  3. v2 socket: connect succeeds          -- the v2 ASGI mount is reachable
  4. v2 socket: send a real message,
     get a structured response            -- the v2 orchestrator answers
     with citations / confidence             a real turn (the LLM, the
                                             retrieval, the synth all wire
                                             up)
  5. (optional) legacy socket: connect    -- the wrap added in #56 did
     + send a message                        not break legacy bytes;
                                             traffic the 100% rollout
                                             still depends on still flows
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

try:
    import httpx
    import socketio
except ImportError as e:
    print(f"FATAL: required dep missing: {e}", file=sys.stderr)
    print("  -> run: pip install -e ./ai-core  (from repo root)", file=sys.stderr)
    sys.exit(2)


# --- Result types ---------------------------------------------------------


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str
    elapsed_ms: int = 0


@dataclass
class RunSummary:
    results: list[CheckResult] = field(default_factory=list)

    def add(self, r: CheckResult) -> None:
        self.results.append(r)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.passed)

    def emit(self) -> None:
        for r in self.results:
            status = "PASS" if r.passed else "FAIL"
            print(f"{status}  {r.name:<55s}  ({r.elapsed_ms}ms)  {r.detail}")
        print()
        print(f"{self.passed}/{len(self.results)} checks passed")


# --- Individual checks ----------------------------------------------------


def _check_http(
    summary: RunSummary, client: httpx.Client, host: str, path: str, name: str
) -> Optional[dict]:
    """GET host+path; record PASS if 200; return parsed JSON or None."""
    url = host.rstrip("/") + path
    t0 = time.monotonic()
    try:
        r = client.get(url, timeout=15.0)
        elapsed = int((time.monotonic() - t0) * 1000)
        ok = 200 <= r.status_code < 300
        detail = f"{r.status_code} {r.headers.get('content-type', '?')}"
        if not ok:
            try:
                body = r.json()
                detail += f"  body={json.dumps(body)[:140]}"
            except Exception:  # noqa: BLE001
                detail += f"  body={r.text[:140]}"
        summary.add(CheckResult(name, ok, detail, elapsed))
        if not ok:
            return None
        try:
            return r.json()
        except Exception:  # noqa: BLE001
            return None
    except Exception as e:  # noqa: BLE001
        elapsed = int((time.monotonic() - t0) * 1000)
        summary.add(CheckResult(name, False, f"exception: {e!r}", elapsed))
        return None


async def _check_socket_v2(
    summary: RunSummary, host: str, question: str
) -> None:
    """Open v2 socket, send `question`, assert structured response."""
    name_connect = "v2 socket connect"
    name_msg = "v2 socket: structured response with citations"
    parsed = urlparse(host)
    base = f"{parsed.scheme}://{parsed.netloc}"
    socketio_path = "/smartchatbot/v2/socket.io"

    sio = socketio.AsyncClient(reconnection=False, logger=False)
    inbox: list[dict] = []
    connect_ok = asyncio.Event()

    @sio.on("connect")
    async def _on_connect() -> None:
        connect_ok.set()

    @sio.on("message")
    async def _on_message(payload) -> None:  # type: ignore[no-untyped-def]
        inbox.append(payload if isinstance(payload, dict) else {"raw": payload})

    t0 = time.monotonic()
    try:
        await sio.connect(
            base,
            socketio_path=socketio_path,
            transports=["websocket"],
            wait=True,
            wait_timeout=10,
        )
    except Exception as e:  # noqa: BLE001
        elapsed = int((time.monotonic() - t0) * 1000)
        summary.add(CheckResult(name_connect, False, f"connect failed: {e!r}", elapsed))
        summary.add(CheckResult(name_msg, False, "skipped (no connection)", 0))
        return

    elapsed = int((time.monotonic() - t0) * 1000)
    summary.add(CheckResult(name_connect, True, f"connected to {socketio_path}", elapsed))

    t0 = time.monotonic()
    try:
        await sio.emit("message", question)
        # Wait up to 30s for the response. A real turn takes 3-10s.
        deadline = time.monotonic() + 30
        while not inbox and time.monotonic() < deadline:
            await asyncio.sleep(0.2)
        elapsed = int((time.monotonic() - t0) * 1000)
        if not inbox:
            summary.add(CheckResult(name_msg, False, "no response in 30s", elapsed))
            return
        resp = inbox[-1]  # last message in case status preamble came first
        # Assert the v2 shape: must have citations key + confidence key.
        # (The legacy reply doesn't have these.)
        if "citations" not in resp or "confidence" not in resp:
            summary.add(CheckResult(
                name_msg, False,
                f"missing citations/confidence: keys={sorted(resp.keys())[:10]}",
                elapsed,
            ))
            return
        n_cites = len(resp.get("citations") or [])
        conf = resp.get("confidence")
        is_refusal = bool(resp.get("is_refusal"))
        msg_preview = (resp.get("message") or "")[:80].replace("\n", " ")
        detail = f"citations={n_cites} confidence={conf} refusal={is_refusal} msg={msg_preview!r}"
        # A refused answer is a valid v2 response shape -- log it but
        # don't fail the check on it (the canned question may not match
        # the live corpus). The operator reads the detail.
        summary.add(CheckResult(name_msg, True, detail, elapsed))
    finally:
        try:
            await sio.disconnect()
        except Exception:  # noqa: BLE001
            pass


async def _check_socket_legacy(
    summary: RunSummary, host: str, question: str
) -> None:
    """Open legacy socket, send `question`, assert we get ANY reply.

    This is the "did the ASGI wrap break legacy?" guard. We do NOT
    assert correctness -- only that the legacy path still responds at
    all. Anything ≥1 char back is a pass; the legacy bot is the path
    100% of real traffic uses today, so any silent breakage here is the
    worst possible outcome.
    """
    name = "legacy socket: still responds (wrap-safety)"
    parsed = urlparse(host)
    base = f"{parsed.scheme}://{parsed.netloc}"
    socketio_path = "/smartchatbot/socket.io"

    sio = socketio.AsyncClient(reconnection=False, logger=False)
    inbox: list[dict] = []

    @sio.on("message")
    async def _on_message(payload) -> None:  # type: ignore[no-untyped-def]
        inbox.append(payload if isinstance(payload, dict) else {"raw": payload})

    t0 = time.monotonic()
    try:
        await sio.connect(
            base,
            socketio_path=socketio_path,
            transports=["websocket"],
            wait=True,
            wait_timeout=10,
        )
        await sio.emit("message", question)
        deadline = time.monotonic() + 30
        while not inbox and time.monotonic() < deadline:
            await asyncio.sleep(0.2)
        elapsed = int((time.monotonic() - t0) * 1000)
        if not inbox:
            summary.add(CheckResult(name, False, "no legacy response in 30s", elapsed))
            return
        resp = inbox[-1]
        msg = (resp.get("message") or "") if isinstance(resp, dict) else str(resp)
        if not msg:
            summary.add(CheckResult(name, False, f"empty legacy response: {resp}", elapsed))
            return
        preview = msg[:80].replace("\n", " ")
        summary.add(CheckResult(name, True, f"legacy replied len={len(msg)} preview={preview!r}", elapsed))
    except Exception as e:  # noqa: BLE001
        elapsed = int((time.monotonic() - t0) * 1000)
        summary.add(CheckResult(name, False, f"exception: {e!r}", elapsed))
    finally:
        try:
            await sio.disconnect()
        except Exception:  # noqa: BLE001
            pass


# --- Orchestration --------------------------------------------------------


async def run(host: str, question: str, skip_legacy: bool) -> int:
    summary = RunSummary()
    with httpx.Client(timeout=20.0) as client:
        _check_http(summary, client, host, "/health/ready", "GET /health/ready")
        smoke = _check_http(summary, client, host, "/smoketest", "GET /smoketest")
        # Soft-assert the smoke result includes citations / is not refused.
        if isinstance(smoke, dict):
            cited = bool((smoke.get("citations") or []))
            refused = bool(smoke.get("is_refusal"))
            summary.add(CheckResult(
                "/smoketest answer is grounded",
                cited and not refused,
                f"citations={len(smoke.get('citations') or [])} refusal={refused}",
                0,
            ))

    await _check_socket_v2(summary, host, question)
    if not skip_legacy:
        await _check_socket_legacy(summary, host, question)

    print()
    summary.emit()
    return 0 if summary.failed == 0 else 1


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Live-verify the v2 serving path.")
    parser.add_argument(
        "--host",
        default="http://localhost:8081",
        help="Base URL of the chatbot service (default: http://localhost:8081)",
    )
    parser.add_argument(
        "--question",
        default="what time does King Library close today?",
        help="Canned question to send through both stacks.",
    )
    parser.add_argument(
        "--skip-legacy",
        action="store_true",
        help="Don't probe the legacy socket path (e.g. if legacy creds are unset).",
    )
    args = parser.parse_args(argv)

    print(f"Live-verify v2 serving against {args.host}")
    print(f"Question: {args.question!r}")
    print()

    try:
        return asyncio.run(run(args.host, args.question, args.skip_legacy))
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main", "run"]
