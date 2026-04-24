"""
Admin API endpoints for librarian-facing operations (plan Op 1 + Op 2).

Four endpoint groups:

  /admin/reviews      -- list recent conversations scoped to the
                         librarian's subject / campus; accept verdicts
                         (correct / partial / wrong / should_refuse).
                         Data model: LibrarianReview.
  /admin/corrections  -- CRUD for ManualCorrection rows. The four
                         actions: suppress / replace / pin / blacklist.
  /admin/stats        -- aggregate health: per-subject %-correct,
                         per-source-URL %-correct, trend over time.
  /smoketest          -- synthetic monitoring endpoint hit by the
                         external pinger every 5 minutes.

Authentication: Miami SSO if available at deploy time, else a
librarian-email allowlist + magic-link login. Auth glue lives in the
existing FastAPI app; this module exposes routers, not a full FastAPI
instance.

Status: SCAFFOLD. FastAPI isn't importable in the test sandbox (the
lib isn't installed), and the data-store wiring goes through the
Prisma client (also not in the sandbox). Each router is built in a
try/except ImportError guard so this package imports cleanly in dev
and plugs into the FastAPI app in prod.
"""

from src.api.admin.corrections_router import build_corrections_router
from src.api.admin.reviews_router import build_reviews_router
from src.api.admin.smoketest_router import build_smoketest_router
from src.api.admin.stats_router import build_stats_router

__all__ = [
    "build_corrections_router",
    "build_reviews_router",
    "build_smoketest_router",
    "build_stats_router",
]
