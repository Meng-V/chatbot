import os
import re
import json
import time
import logging
from decimal import Decimal
from datetime import datetime, date
import socketio
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from pathlib import Path
from src.utils.logging_config import setup_logging, UVICORN_LOG_CONFIG
from contextlib import asynccontextmanager

from src.state import AgentState
from src.utils.logger import AgentLogger
from src.memory.conversation_store import (
    create_conversation,
    add_message,
    get_conversation_history,
    update_conversation_tools,
    update_message_rating,
    save_conversation_feedback,
    log_token_usage,
    log_tool_execution
)
from src.database.prisma_client import connect_database, disconnect_database
from src.utils.weaviate_client import get_weaviate_client, close_weaviate_client, get_weaviate_url
from src.api.health import router as health_router
from src.api.summarize import router as summarize_router
from src.api.ticket import router as ticket_router
from src.api.askus_hours import router as askus_router
from src.api.route import router as route_router
from src.api.readiness_router import (
    build_readiness_router,
    make_postgres_probe,
    make_weaviate_probe,
    make_openai_probe,
    make_libcal_probe,
    make_libguides_probe,
)
from src.api.admin.smoketest_router import build_smoketest_router
from src.observability.request_id_middleware import RequestIdMiddleware
from src.api.metrics_router import build_metrics_router
from src.observability.metrics_middleware import MetricsMiddleware
from src.observability.sentry import init_sentry
from src.api.rate_limit import (
    MessageRejected,
    check_rate,
    client_ip_from_request,
    validate_message,
)

# ---------------------------------------------------------------------------
# .env loading — MUST NOT follow symlinks on production
# ---------------------------------------------------------------------------
# On production the deploy layout is:
#   /opt/chatbot/current  →  /opt/chatbot/releases/<timestamp>  (symlink)
#   /opt/chatbot/shared/.env                                      (canonical)
#   /opt/chatbot/releases/<timestamp>/.env → shared/.env          (symlink)
#
# Path(__file__).resolve() follows ALL symlinks, locking us to a stale
# release directory.  os.path.abspath() makes the path absolute WITHOUT
# resolving symlinks, so we always read through the 'current' symlink.
# ---------------------------------------------------------------------------
_this_file = os.path.abspath(__file__)          # …/current/ai-core/src/main.py
root_dir = Path(os.path.dirname(os.path.dirname(os.path.dirname(_this_file))))

# Prefer the canonical shared .env on production; fall back to project root
_shared_env = Path("/opt/chatbot/shared/.env")
if _shared_env.exists():
    env_path = _shared_env
else:
    env_path = root_dir / ".env"

load_dotenv(dotenv_path=env_path, override=True)
print(f"Loading .env from: {env_path}")

# Initialize logging EARLY (module level) so it takes effect before uvicorn
# configures its own loggers. This prevents INFO spam in systemd journal.
setup_logging()
logging.info(f"📂 .env loaded from: {env_path}  (root_dir={root_dir})")
logging.info(f"📂 __file__ resolved WITHOUT symlinks: {_this_file}")

# Op 3 (non-negotiable launch floor): wire Sentry BEFORE the FastAPI
# app is created so sentry-sdk's auto-enabled FastAPI/Starlette
# integration instruments the whole request path. No-op unless
# SENTRY_DSN is set AND sentry-sdk is installed -- merging this is a
# zero-behavior-change until an operator configures the DSN.
init_sentry()


def json_serializable(obj):
    """
    Convert non-JSON-serializable objects to serializable types.
    Handles Decimal, datetime, date, and other common types.
    """
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, (datetime, date)):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {k: json_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [json_serializable(item) for item in obj]
    else:
        return obj


def clean_response_for_frontend(text: str) -> str:
    """
    Remove internal metadata and source annotations from response before sending to frontend.
    These are useful for internal processing but awkward for end users to see.
    """
    if not text:
        return text
    
    # Patterns to remove (internal metadata that shouldn't be shown to users)
    patterns_to_remove = [
        # Source attribution lines - remove ALL source lines
        r'\n*Source:\s*[^\n]+\n*',
        # Standalone brackets with internal labels
        r'\s*\[VERIFIED API DATA\]',
        r'\s*\[CURATED KNOWLEDGE BASE[^\]]*\]',
        r'\s*\[WEBSITE SEARCH[^\]]*\]',
        r'\s*\[HIGH PRIORITY\]',
    ]
    
    cleaned = text
    for pattern in patterns_to_remove:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
    
    # Clean up extra whitespace/newlines that might result from removal
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    cleaned = cleaned.strip()
    
    return cleaned


# Lifecycle management for database connection
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and shutdown."""
    # Startup
    setup_logging()  # Re-apply logging config (overrides uvicorn's defaults)
    logging.info("🚀 Application starting...")

    # --- Database connection ---
    try:
        await connect_database()
        logging.info("✅ Database (Prisma) connected successfully")
    except Exception as e:
        logging.error(f"❌ Database connection FAILED: {e}", exc_info=True)

    # --- Weaviate connection check ---
    weaviate_url = get_weaviate_url()
    logging.info(f"🔗 [Weaviate] Attempting connection to {weaviate_url}")
    try:
        wv_client = get_weaviate_client()
        if wv_client is not None:
            is_ready = wv_client.is_ready()
            if is_ready:
                meta = wv_client.get_meta()
                version = meta.get("version", "unknown") if isinstance(meta, dict) else "unknown"
                collections = wv_client.collections.list_all()
                col_names = list(collections.keys()) if isinstance(collections, dict) else [str(c) for c in collections]
                logging.info(
                    f"✅ [Weaviate] Connected successfully | "
                    f"url={weaviate_url} | version={version} | "
                    f"collections={len(col_names)} ({', '.join(col_names[:10])})"
                )
            else:
                logging.warning(f"⚠️ [Weaviate] Client created but NOT READY at {weaviate_url}")
        else:
            logging.warning(
                f"⚠️ [Weaviate] Client is None — connection failed or disabled | url={weaviate_url} | "
                f"WEAVIATE_ENABLED={os.getenv('WEAVIATE_ENABLED', 'true')} | "
                f"WEAVIATE_HOST={os.getenv('WEAVIATE_HOST', '(not set)')}"
            )
    except Exception as e:
        logging.error(f"❌ [Weaviate] Connection FAILED at {weaviate_url}: {e}", exc_info=True)

    # --- Initialize RAG classifier vector store ---
    try:
        from src.classification.rag_classifier import RAGQuestionClassifier
        classifier = RAGQuestionClassifier()
        await classifier.initialize_vector_store(force_refresh=False)
        logging.info("✅ [RAG Classifier] Vector store initialized")
    except Exception as e:
        logging.error(f"⚠️ [RAG Classifier] Vector store init failed: {e}", exc_info=True)

    # --- Springshare (LibCal / LibGuides) pre-flight health check ---
    # Runs BEFORE the bot serves traffic so the operator sees, at boot,
    # whether the Springshare APIs are reachable. Never fatal -- live
    # data degrades gracefully -- but it logs a loud banner if a service
    # is down so flaky-API incidents are visible immediately.
    try:
        from src.observability.springshare import check_springshare_health
        await check_springshare_health()
    except Exception as e:
        logging.warning(f"⚠️ [Springshare] pre-flight health check errored: {e}")

    # --- Warm the v2 serving deps at BOOT (do NOT lazy-load per request) ---
    # build_v2_deps() loads ~5.5k kNN exemplars + a ~347MB embedding cache
    # and embeds any cache-misses -- ~10-16s of synchronous CPU/network.
    # Doing that lazily on the FIRST user message ran it on the asyncio
    # event loop (`deps = _get_v2_deps()` in the async _v2_message handler),
    # which blocked Uvicorn long enough to miss the Socket.IO heartbeat:
    # the browser assumed the server died, dropped the connection, and
    # showed "I encountered an error" -- with no Python traceback, because
    # the backend never crashed. Warming here, before any traffic, moves
    # that cost off the request path. `to_thread` keeps even boot's event
    # loop responsive while the heavy build runs on a worker thread.
    try:
        import asyncio as _asyncio
        await _asyncio.to_thread(_get_v2_deps)
        logging.info("✅ [v2] serving deps warmed (classifier + backends ready)")
    except Exception as e:  # noqa: BLE001
        logging.warning(
            f"⚠️ [v2] deps warm-up failed; first message will lazy-load: {e}"
        )

    # Background health watcher -- email the operator (ALERT_EMAIL_TO,
    # default qum@miamioh.edu) when a dependency goes down or recovers, so a
    # silent outage (e.g. Postgres down) is visible without waiting for a user
    # complaint. Best-effort; never blocks startup.
    try:
        import asyncio as _aio
        app.state.health_task = _aio.create_task(_health_alert_watcher())
    except Exception as e:  # noqa: BLE001
        logging.warning(f"[health-watch] failed to start: {e}")

    logging.info("🚀 Application startup complete")
    yield

    # Shutdown
    logging.info("🛑 Application shutting down...")
    _ht = getattr(app.state, "health_task", None)
    if _ht is not None:
        _ht.cancel()
    close_weaviate_client()
    logging.info("🔌 [Weaviate] Client closed")
    await disconnect_database()
    logging.info("✅ Database disconnected")


def _health_alert_body(results: list) -> str:
    """Plain-text dependency status block for an alert email."""
    lines = ["Smart Chatbot dependency health (app.lib.miamioh.edu):", ""]
    for r in results:
        lines.append(f"  [{'OK  ' if r.passed else 'DOWN'}] {r.name}: {r.status}")
    lines.append("")
    lines.append("Live status: curl http://localhost:8081/health/ready")
    return "\n".join(lines)


async def _health_alert_watcher() -> None:
    """Poll dependency health on an interval; email the operator ONLY on a
    state change (down / recovered) so there's no spam. Never raises -- a
    watcher failure only logs."""
    import asyncio
    from src.observability.alerting import send_alert_email, alert_enabled
    from src.api.readiness_router import run_probes

    if not alert_enabled():
        logging.info("[health-watch] disabled (ALERT_EMAIL_ENABLED=false)")
        return
    try:
        interval = int(os.getenv("ALERT_CHECK_INTERVAL_SEC", "300") or "300")
    except ValueError:
        interval = 300
    try:
        recheck_delay = int(os.getenv("ALERT_RECHECK_DELAY_SEC", "15") or "15")
    except ValueError:
        recheck_delay = 15
    probes = _build_readiness_probes()
    last_ok = None  # tri-state: None (no baseline yet) / True / False
    await asyncio.sleep(45)  # let boot + dep warm-up settle before first check
    logging.info(
        "[health-watch] started (every %ss, recheck %ss, alerts -> %s)",
        interval, recheck_delay, os.getenv("ALERT_EMAIL_TO", "qum@miamioh.edu"),
    )
    while True:
        try:
            results = await run_probes(probes)
            down = [r.name for r in results if not r.passed]
            if down:
                # Transient guard: a cold remote-SSL DB connect right after a
                # restart fails the probe's 2s timeout ONCE, then passes when
                # warm. Re-check after a short delay; only a SUSTAINED failure
                # alerts. (False "postgres DOWN" on 2026-06-25 redeploy.)
                await asyncio.sleep(recheck_delay)
                results = await run_probes(probes)
                down = [r.name for r in results if not r.passed]
            ok = not down
            if last_ok is None:
                last_ok = ok
                if not ok:
                    send_alert_email(
                        "🔴 Smart Chatbot: dependency DOWN at startup (" + ", ".join(down) + ")",
                        _health_alert_body(results),
                    )
            elif ok != last_ok:
                last_ok = ok
                if ok:
                    send_alert_email(
                        "✅ Smart Chatbot: recovered",
                        "All dependency checks pass again.\n\n" + _health_alert_body(results),
                    )
                else:
                    send_alert_email(
                        "🔴 Smart Chatbot: dependency DOWN (" + ", ".join(down) + ")",
                        _health_alert_body(results),
                    )
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 -- watcher must never crash the app
            logging.warning("[health-watch] cycle errored: %s", e)
        await asyncio.sleep(interval)

# Create FastAPI app with lifecycle
app = FastAPI(
    title="Miami Libraries AI-Core",
    description="LangGraph-powered chatbot with 6 specialized agents",
    version="1.0.0",
    lifespan=lifespan
)

# Environment-based CORS configuration
node_env = os.getenv("NODE_ENV", "development")
frontend_url = os.getenv("FRONTEND_URL", "https://new.lib.miamioh.edu")

cors_origins = [frontend_url]
if node_env == "development":
    cors_origins.extend([
        "http://localhost:5173",
        "http://localhost:3000"
    ])

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Op 3: bind one request_id per request so every structlog line in
# the request carries it. Added LAST -> Starlette makes it the
# OUTERMOST middleware, so the id is bound before anything else runs
# and echoed back as X-Request-ID for user-report <-> log correlation.
app.add_middleware(RequestIdMiddleware)
# Op 3 (Metrics): time every request -> chatbot_request_* metrics.
# No-ops invisibly until prometheus-client is installed; excludes the
# /metrics + /health/live infra polls so they don't skew the signal.
app.add_middleware(MetricsMiddleware)

# Include health/monitoring routers
app.include_router(health_router)
app.include_router(summarize_router)
app.include_router(ticket_router)
app.include_router(askus_router)
app.include_router(route_router)
# These are served at the ROOT path and reached via dedicated nginx
# `location` proxy blocks (/summarize-chat, /askus-hours/status, /health,
# and -- to be added -- /ticket/create), NOT via the /smartchatbot/
# static alias. See nginx app.lib.miamioh.edu server block.


# --- Op 3: /health/ready + /smoketest (rebuild observability) -------------
# Built as dependency-injected routers so test setup can stub probes.
# The legacy /health and /readiness stay live alongside these.
def _build_readiness_probes():
    import httpx
    from src.database.prisma_client import get_prisma_client
    from src.services.libcal_oauth import get_libcal_oauth_service

    async def pg_exec():
        client = get_prisma_client()
        if not client.is_connected():
            await client.connect()
        await client.execute_raw("SELECT 1")

    async def wv_meta():
        client = get_weaviate_client()
        if client is None:
            raise RuntimeError("weaviate client unavailable")
        return client.get_meta()

    async def openai_ping():
        # Cheap auth check: hit /v1/models. A tiny completion would be
        # more faithful to the plan but costs a token per probe call
        # (every readiness poll). /v1/models exercises the auth path
        # and is free.
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set")
        async with httpx.AsyncClient(timeout=5.0) as hc:
            r = await hc.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            r.raise_for_status()

    async def libcal_status():
        svc = get_libcal_oauth_service()
        token = await svc.get_token()
        if not token:
            raise RuntimeError("no token")

    async def libguides_status():
        from src.services.libapps_oauth import get_libapps_oauth_service
        token = await get_libapps_oauth_service().get_token()
        if not token:
            raise RuntimeError("no token")

    return [
        make_postgres_probe(pg_exec),
        make_weaviate_probe(wv_meta),
        make_openai_probe(openai_ping),
        make_libcal_probe(libcal_status),
        make_libguides_probe(libguides_status),
    ]


app.include_router(build_readiness_router({"probes": _build_readiness_probes()}))


def _smoketest_ask_v2_bot(question: str) -> dict:
    """Sync wrapper around the rebuilt orchestrator (run_turn) for
    /smoketest/v2. Used by the external pinger to keep the v2 path's
    health independently observable from the legacy /smoketest result.

    Mirrors the legacy _smoketest_ask_bot's run-on-dedicated-thread
    pattern (we're called from inside a running FastAPI event loop,
    but run_turn is sync, so we just call it directly here -- no
    nested asyncio.run needed). Returns the same shape the
    legacy `ask_bot` does: {answer, citations, is_refusal}.

    Deps are reused from the same lazy `_get_v2_deps()` singleton the
    socket handler uses -- one build per process, not per smoketest
    hit. A deps-build failure short-circuits to a clearly-labeled
    error dict so the smoketest reports `passed=False` rather than
    raising 500.
    """
    try:
        deps = _get_v2_deps()
    except Exception as e:  # noqa: BLE001
        return {"answer": "", "citations": [], "is_refusal": False, "error": f"deps_unavailable: {e}"}
    from src.graph.new_orchestrator import TurnRequest, run_turn  # noqa: WPS433
    req = TurnRequest(
        user_message=question,
        conversation_id="smoketest-v2",
    )
    resp = run_turn(req, deps)
    return {
        "answer": resp.answer or "",
        "citations": resp.citations or [],
        "is_refusal": bool(resp.is_refusal),
    }


# Legacy serving path removed 2026-07-17 -- v2 answers both probe URLs
# (/smoketest kept for existing monitors; /smoketest/v2 kept as alias).
app.include_router(build_smoketest_router({
    "ask_bot": _smoketest_ask_v2_bot,
    "ask_bot_v2": _smoketest_ask_v2_bot,
}))

# Op 3: Prometheus scrape target. Self-describes a 200 when
# prometheus-client isn't installed (never 500s a scrape).
app.include_router(build_metrics_router())

# Op 1: subject-librarian review surface (read-only). FAIL-CLOSED:
# mounted ONLY when ADMIN_API_TOKEN is set, so a misconfigured deploy
# can never expose raw conversation logs (user input + PII). The
# token gates both the JSON API and the HTML pages (header or ?key=).
_admin_token = os.getenv("ADMIN_API_TOKEN", "").strip()
if _admin_token:
    from src.api.admin.reviews_router import build_reviews_router
    from src.api.admin.review_view_router import (
        build_review_view_router,
        make_token_guard,
    )
    from src.database.prisma_client import get_prisma_client

    _guard = make_token_guard(_admin_token)
    _admin_deps = {
        "db": get_prisma_client(),
        "require_librarian": _guard,  # reviews_router's auth dep
        "guard": _guard,              # review_view_router's auth dep
    }
    from src.api.admin.corrections_router import build_corrections_router
    from src.api.admin.cost_view_router import build_cost_view_router

    app.include_router(build_reviews_router(_admin_deps))
    app.include_router(build_review_view_router(_admin_deps))
    app.include_router(build_corrections_router(_admin_deps))
    app.include_router(build_cost_view_router(_admin_deps))
    logging.info(
        "Op1/Op2/Op3 admin surfaces mounted (ADMIN_API_TOKEN set): "
        "/admin/review (HTML), /admin/reviews (JSON), "
        "/admin/corrections (CRUD) + /admin/corrections/view (form), "
        "/admin/cost (HTML) + /admin/cost.json."
    )

    # Librarian correction tickets ("this answer is wrong" reports).
    # The librarian form needs its own shared code (staff-distributable,
    # weaker than the admin token which exposes PII); the operator list
    # rides the admin guard. Mounted inside the admin block because the
    # list view requires the token guard either way.
    _ticket_code = os.getenv("LIBRARIAN_TICKET_CODE", "").strip()
    from src.api.admin.ticket_router import build_ticket_router
    app.include_router(build_ticket_router({
        **_admin_deps, "librarian_code": _ticket_code,
    }))

    # One-bookmark hubs: /admin/ (operator) + /librarian/ (staff).
    from src.api.admin.hub_router import build_hub_router
    app.include_router(build_hub_router({
        "admin_token": _admin_token,
        "librarian_code": _ticket_code,
    }))
    if _ticket_code:
        logging.info(
            "Correction-ticket surfaces mounted: /librarian/ticket "
            "(code-gated form) + /admin/tickets/view (token-gated queue)."
        )
    else:
        logging.info(
            "Correction-ticket form is mounted but CLOSED -- set "
            "LIBRARIAN_TICKET_CODE to open it (fail-closed guard 401s)."
        )
else:
    logging.info(
        "Op1 review surface NOT mounted -- ADMIN_API_TOKEN unset "
        "(fail-closed; conversation logs stay private)."
    )


# Socket.IO server for real-time communication
# Allow all origins in development for easier debugging
socketio_cors = "*" if node_env == "development" else cors_origins

# Store conversation mappings for Socket.IO clients
client_conversations = {}

# v2 handlers under distinct names (sio_v2.on(...)) so they cannot
# shadow the legacy module-level connect/message/disconnect. Legacy
# sessions are provably unaffected; uvicorn still serves
# `src.main:app_sio`.
#
# Deps are built LAZILY on first v2 message (NEVER at import) and
# cached. A build failure (no OpenAI credit / Weaviate down) degrades
# ONLY v2 sessions to a graceful error -- it cannot break app boot or
# the legacy path.
#
# OPERATOR LIVE-VERIFY (not offline-testable -- needs real OpenAI +
# Weaviate + Postgres): with VITE_V2_ROLLOUT_PERCENT=0, open `?v2=1`,
# confirm a cited answer renders AND a no-flag session is unchanged,
# BEFORE raising the rollout percentage.
from src.graph.v2_serving import handle_v2_message, build_v2_deps  # noqa: E402

sio_v2 = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=socketio_cors,
    logger=False,
    engineio_logger=False,
)
_v2_deps = None
_v2_deps_error: Exception | None = None


def _get_v2_deps():
    """Lazy singleton; built on first v2 message, never at import.
    A prior failure is sticky (don't hammer a down dependency)."""
    global _v2_deps, _v2_deps_error
    if _v2_deps is not None:
        return _v2_deps
    if _v2_deps_error is not None:
        raise _v2_deps_error
    try:
        _v2_deps = build_v2_deps()
        return _v2_deps
    except Exception as e:  # noqa: BLE001
        _v2_deps_error = e
        raise


async def _v2_connect(sid, environ):
    logging.info(f"🔌 [v2] Client connected: {sid}")
    conversation_id = await create_conversation()
    client_conversations[sid] = conversation_id
    await sio_v2.emit(
        "status",
        {"status": "connected", "conversationId": conversation_id},
        to=sid,
    )


async def _v2_disconnect(sid):
    logging.info(f"🔌 [v2] Client disconnected: {sid}")
    client_conversations.pop(sid, None)


async def _v2_message(sid, data):
    text_input = (
        data
        if isinstance(data, str)
        else (data.get("message", "") if isinstance(data, dict) else "")
    )
    conversation_id = client_conversations.get(sid)
    if not conversation_id:
        conversation_id = await create_conversation()
        client_conversations[sid] = conversation_id
    try:
        # Conversation logging + history are BEST-EFFORT: a DB blip must NOT
        # crash the turn. The bot can still classify and answer; we only lose
        # logging / prior-turn context for this message. (Same rule as the
        # token telemetry below and _safe_load_corrections.) prod 2026-06-25:
        # a Postgres outage made add_message throw at the very FIRST line of
        # this handler, so EVERY message -- including a cancel test during a
        # demo -- hit the generic "I encountered an error" before the bot ran.
        try:
            await add_message(conversation_id, "user", text_input)
        except Exception as le:  # noqa: BLE001
            logging.warning(f"⚠️ [v2] user-message log failed (continuing): {le}")
        try:
            history = await get_conversation_history(conversation_id, limit=10)
        except Exception as le:  # noqa: BLE001
            logging.warning(f"⚠️ [v2] history load failed (no context this turn): {le}")
            history = []
        try:
            deps = _get_v2_deps()
        except Exception as e:  # noqa: BLE001
            logging.error(f"❌ [v2] deps unavailable: {e}", exc_info=True)
            await sio_v2.emit(
                "message",
                json_serializable(
                    {
                        "messageId": None,
                        "message": (
                            "The v2 assistant is temporarily unavailable. "
                            "Please try again or contact a librarian."
                        ),
                        "conversationId": conversation_id,
                        "error": "v2_deps_unavailable",
                    }
                ),
                to=sid,
            )
            return
        wire = await handle_v2_message(
            data,
            deps,
            conversation_id=conversation_id,
            conversation_history=history,
        )
        # Log the assistant turn, but NEVER let a logging failure swallow a
        # successfully-generated reply -- the emit happens regardless.
        message_id = None
        try:
            message_id = await add_message(
                conversation_id, "assistant", wire.get("message", "") or ""
            )
        except Exception as le:  # noqa: BLE001
            logging.warning(f"⚠️ [v2] assistant-message log failed (reply still delivered): {le}")
        wire["messageId"] = message_id
        await sio_v2.emit("message", json_serializable(wire), to=sid)
        # --- Telemetry (backlog B1): persist per-turn token usage. ---
        # Done HERE (async context, main loop) rather than inside run_turn,
        # which executes on an executor thread where the Prisma client's
        # loop-affinity bites (same class of bug as the corrections loader).
        # The wire's `tokens` is the turn AGGREGATE (agent loop + synth),
        # so call_site="v2_turn" labels it as such for cost_rollup. Zero-
        # token turns (capability/limitation short-circuits, refusal
        # templates -- no LLM call) are skipped to avoid junk rows.
        # Telemetry must NEVER break a served turn: failures only log.
        try:
            _tok = wire.get("tokens") or {}
            _total = int(_tok.get("input", 0)) + int(_tok.get("output", 0))
            if _total > 0:
                from src.memory.conversation_store import log_token_usage_v2
                await log_token_usage_v2(
                    conversation_id,
                    model_name=str(wire.get("model_used") or "v2-unknown"),
                    prompt_tokens=int(_tok.get("input", 0)),
                    completion_tokens=int(_tok.get("output", 0)),
                    total_tokens=_total,
                    cached_input_tokens=int(_tok.get("cached_input", 0)),
                    call_site="v2_turn",
                )
        except Exception as te:  # noqa: BLE001
            logging.warning(f"⚠️ [v2] token-usage telemetry failed (turn was served): {te}")
    except Exception as e:  # noqa: BLE001
        logging.error(f"❌ [v2] Error: {e}", exc_info=True)
        await sio_v2.emit(
            "message",
            json_serializable(
                {
                    "messageId": None,
                    "message": (
                        "Sorry — I ran into a problem on my end and couldn't "
                        "answer that. Please try again in a moment. If it keeps "
                        "happening, a librarian can help right away through Ask "
                        "Us (https://www.lib.miamioh.edu/research/research-support/ask/) "
                        "or at (513) 529-4141."
                    ),
                    "error": str(e),
                }
            ),
            to=sid,
        )


async def _v2_message_rating(sid, data):
    """Thumbs up/down on one message. Ported from the legacy handler
    2026-07-17 -- the client kept emitting `messageRating` after the
    5-27 cutover but v2 had no listener, so ratings were silently
    dropped (found during the legacy-path removal)."""
    try:
        message_id = (data or {}).get("messageId")
        is_positive = (data or {}).get("isPositiveRated", True)
        if message_id:
            await update_message_rating(message_id, is_positive)
            logging.info(f"👍 [v2] message {message_id} rated "
                         f"{'positive' if is_positive else 'negative'}")
            await sio_v2.emit("ratingAck",
                              {"messageId": message_id, "success": True}, to=sid)
    except Exception as e:  # noqa: BLE001
        logging.error(f"❌ [v2] rating failed: {e}")
        await sio_v2.emit("ratingAck", {"success": False, "error": str(e)}, to=sid)


async def _v2_user_feedback(sid, data):
    """End-of-conversation rating + comment. Ported like _v2_message_rating."""
    try:
        conversation_id = (data or {}).get("conversationId") or             client_conversations.get(sid)
        if conversation_id:
            await save_conversation_feedback(
                conversation_id,
                (data or {}).get("userRating", 0),
                (data or {}).get("userComment", ""),
            )
            logging.info(f"💬 [v2] feedback saved for {conversation_id}")
            await sio_v2.emit("feedbackAck",
                              {"conversationId": conversation_id, "success": True},
                              to=sid)
    except Exception as e:  # noqa: BLE001
        logging.error(f"❌ [v2] feedback failed: {e}")
        await sio_v2.emit("feedbackAck", {"success": False, "error": str(e)}, to=sid)


sio_v2.on("connect", _v2_connect)
sio_v2.on("messageRating", _v2_message_rating)
sio_v2.on("userFeedback", _v2_user_feedback)
sio_v2.on("disconnect", _v2_disconnect)
sio_v2.on("message", _v2_message)

# 2026-07-17: legacy path REMOVED (operator decision: all-in on v2).
# sio_v2 is the only socket server; plain HTTP falls through to FastAPI.
# Rollback = git revert of the removal commit + ./build.sh.
app_sio = socketio.ASGIApp(
    sio_v2,
    other_asgi_app=app,
    socketio_path="/smartchatbot/socket.io",
)


# ---------------------------------------------------------------------------
# Programmatic uvicorn entry point  (preferred on production)
# Usage:  python -m src.main
# This passes UVICORN_LOG_CONFIG so every log line has a timestamp.
# Falls back to: uvicorn src.main:app_sio --host 0.0.0.0 --port 8000
#   but the CLI approach will NOT have timestamps unless you also pass
#   --log-config ai-core/uvicorn_log_config.json
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.main:app_sio",
        host="0.0.0.0",
        port=int(os.getenv("AI_CORE_PORT", "8000")),
        log_config=UVICORN_LOG_CONFIG,
    )
