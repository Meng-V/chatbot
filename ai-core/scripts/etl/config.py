"""
ETL configuration -- the knobs librarians and operators tune without
touching pipeline code.

Most of these are dictionaries with comments explaining each entry. They're
loaded once at run_etl.py startup; changing a value requires re-running ETL
to take effect. (Run-time configuration belongs in env vars; this is
content-shape configuration.)

See plan: Data preparation playbook §4 (pipeline) and §7 (featured services).
"""

from __future__ import annotations

from pathlib import Path
from typing import Final, Optional


# --- Path anchor ------------------------------------------------------------
#
# Resolved once at import time. All output path constants below are absolute
# so the ETL produces files in the right place regardless of where the
# operator invokes it from. Previously the path strings were relative
# ("ai-core/data/...") and the runbook required `cd ai-core` first; the
# combo produced `ai-core/ai-core/data/...` when the cwd was already inside
# ai-core. Anchoring to the module's location eliminates the cwd dependency.

_AI_CORE_ROOT: Final[Path] = Path(__file__).resolve().parents[2]


# --- Source domains ---------------------------------------------------------

SITEMAPS: Final[dict[str, str]] = {
    # campus -> sitemap URL. discover.py iterates this dict.
    "oxford": "https://www.lib.miamioh.edu/sitemap.xml",
    "hamilton": "https://www.ham.miamioh.edu/sitemap.xml",
    "middletown": "https://www.mid.miamioh.edu/sitemap.xml",
}

# Fallback seed URL lists if a sitemap is unavailable. discover.py uses
# these when SITEMAPS[campus] returns 404 / unparseable. Keep small and
# librarian-curated rather than crawling recursively (better signal/noise).
SEED_URLS: Final[dict[str, list[str]]] = {
    "hamilton": [
        "https://www.ham.miamioh.edu/library/",
        "https://www.ham.miamioh.edu/library/about/",
        "https://www.ham.miamioh.edu/library/services/",
        "https://www.ham.miamioh.edu/library/research/",
        # Add more as the librarian liaisons identify priority pages.
    ],
    "middletown": [
        # Real Middletown library URLs use `.htm` extensions (the
        # `/library/about/` slash form 404s; confirmed by HEAD-checking
        # the landing page's `<a href>` tags). Add more as the librarian
        # liaisons identify priority pages.
        "https://www.mid.miamioh.edu/library/",
        "https://www.mid.miamioh.edu/library/index.htm",
        "https://www.mid.miamioh.edu/library/aboutus.htm",
        "https://www.mid.miamioh.edu/library/services.htm",
        "https://www.mid.miamioh.edu/library/research.htm",
        "https://www.mid.miamioh.edu/library/libraryresearch.html",
        "https://www.mid.miamioh.edu/library/printing.htm",
        "https://www.mid.miamioh.edu/library/reference.htm",
        "https://www.mid.miamioh.edu/library/reserves.htm",
        "https://www.mid.miamioh.edu/library/textbookreserves.htm",
        "https://www.mid.miamioh.edu/library/researchconsultations.htm",
        "https://www.mid.miamioh.edu/library/citingsources.htm",
        "https://www.mid.miamioh.edu/library/accessibility.htm",
    ],
}

# Hosts allowed to be fetched with TLS verification disabled. STRICTLY
# temporary -- every entry here logs a WARN on use and emits a metric so
# we notice when the cert is finally renewed (then remove from list).
TLS_SKIP_ALLOWLIST: Final[set[str]] = {
    "mid.miamioh.edu",       # cert expired as of plan-write time, file IT ticket
    "www.mid.miamioh.edu",
}


# --- URL filtering ----------------------------------------------------------

# Path prefixes that are ALWAYS excluded -- never enter the index.
# News/events are the prime suspects for "fake service" hallucinations
# (defunct programs, expired hours, old exhibits). The bot is not a news
# platform; users wanting current events go to the news page directly.
#
# `/_` catches Miami's internal-template-path convention (`/_about/`,
# `/_strategic/`, `/_carousel/`). These paths return 404 in the wild;
# they're internal CMS scaffolding leaked into the sitemap. First ETL
# run produced 7 such 404s -- the prefix drops them at discover time.
EXCLUDE_URL_PREFIXES: Final[tuple[str, ...]] = (
    "/about/news-events/",
    "/news/",
    "/events/",
    "/exhibits/",
    "/blog/",
    "/test/",
    "/staging/",
    "/dev/",
    "/_",
)

# Specific path patterns to drop in addition to the prefixes above.
EXCLUDE_URL_SUBSTRINGS: Final[tuple[str, ...]] = (
    "readme",
    "/404",
    "/test-page",
)


# --- Positive library-content allowlist -------------------------------------
#
# The Middletown sitemap (`mid.miamioh.edu/sitemap.xml`) 308-redirects to
# `miamioh.edu/regionals/sitemap.xml`, which contains 2,487 URLs of which
# **zero** are library content (it's ECCOE, marketing-comms, athletics,
# news archives, etc.). Without a positive library filter, the ETL would
# happily crawl all 2,487 and produce ~265 TooManyRedirects fetch failures
# on the regional marketing-comms pages.
#
# A URL counts as library content if EITHER:
#   - its host starts with "lib." (e.g. lib.miamioh.edu), OR
#   - its path contains "/library/" (e.g. ham.miamioh.edu/library/about/)
#
# Anything else is rejected at discover time with reason="not_library_url".
# To allow a new domain or path shape, add to one of the patterns below.

LIBRARY_HOST_PREFIXES: Final[tuple[str, ...]] = (
    "lib.",        # lib.miamioh.edu
    "www.lib.",    # www.lib.miamioh.edu
    "libguides.",  # libguides.lib.miamioh.edu -- curated LIBGUIDE_SEED
                   # only; discover never bulk-crawls this host.
)

LIBRARY_PATH_SUBSTRINGS: Final[tuple[str, ...]] = (
    "/library/",  # ham.miamioh.edu/library/*, mid.miamioh.edu/library/*
)


# --- Topic classification (rule-based, runs in classify.py) -----------------

# Prefix -> topic. First match wins. Order from most-specific to least.
TOPIC_BY_URL_PREFIX: Final[tuple[tuple[str, str], ...]] = (
    ("/use/borrow/", "borrow"),
    ("/use/spaces/", "spaces"),
    ("/use/technology/", "technology"),
    ("/use/", "service"),
    ("/research/", "research"),
    ("/about/locations/", "about"),
    ("/about/organization/", "about"),
    ("/about/policies/", "policy"),
    ("/about/", "about"),
    ("/digital-collections/", "collections"),
    ("/library/", "about"),  # regional library landing pages
)


# --- Vanity short-URL -> real indexable page --------------------------------
#
# Some Miami vanity short-URLs (/adobe/, ...) are <meta refresh> /
# canonical-only shims whose destination is OFF-HOST and not
# indexable as prose (e.g. /adobe/ -> muohio.libcal.com LibCal
# equipment item, a JS app on a different host). extract.find_redirect
# _target detects the shim; run_etl, when the target fails the
# library-content filter, looks here for the real same-host page that
# answers the same question and indexes THAT instead (dedup handles
# overlap if the page is also in the sitemap).
#
# Operator-verified 2026-05-17: /software/ extracts clean (2048 chars,
# "Software Checkout") and is the page their gold (fs_indesign_faculty)
# cites for Adobe. Keep tiny + librarian-curated.
VANITY_CANONICAL: Final[dict[str, str]] = {
    "https://www.lib.miamioh.edu/adobe/":
        "https://www.lib.miamioh.edu/software/",
}


# --- Featured services (plan §7) --------------------------------------------
#
# Map URL substrings -> featured_service tag. classify.py applies this to
# every crawled URL; matched chunks get a boost in retrieval ranking and
# their URLs are marked priority="high" in UrlSeen so a transient sitemap
# glitch doesn't blackhole them. Add new featured services with one line.

FEATURED_SERVICE_PATTERNS: Final[tuple[tuple[str, str], ...]] = (
    # (url_substring, featured_service_tag)
    ("/use/technology/software/adobe", "adobe_checkout"),
    ("/software/adobe", "adobe_checkout"),
    ("/use/borrow/ill", "ill"),
    ("/library/services/ill", "ill"),
    ("/interlibrary-loan", "ill"),
    ("/use/spaces/makerspace", "makerspace"),
    ("/create/makerspace", "makerspace"),
    ("/digital-collections/", "digital_collections"),
    ("/about/locations/special-collections", "special_collections"),
    ("/research/databases/newspapers", "newspapers"),
    ("/databases/nyt", "newspapers"),
    ("/databases/wsj", "newspapers"),
)


# --- Curated LibGuide registry (plan §1/§7) ---------------------------------
#
# libguides.lib.miamioh.edu is NOT in any campus sitemap, and the eval
# proved this is a MEASURED blocker: fs_makerspace_middletown_refusal
# can't answer ("couldn't verify my sources") because the Middletown
# TEC Lab guide isn't in the index.
#
# We seed a SMALL, canonical-doc/operator-confirmed set rather than
# bulk-crawl the libguides sitemap, for TWO reasons:
#   1. The plan prefers curated > bulk (signal/noise; pollution is the
#      exact failure this whole project fights).
#   2. classify._infer_campus host-defaults libguides -> 'oxford', so a
#      bulk crawl would tag the Middletown TEC Lab guide as Oxford and
#      the load-bearing cross-campus guard would then BLOCK it for
#      Middletown queries. Each entry below carries EXPLICIT campus /
#      library / featured_service; classify.py honors these verbatim
#      (does NOT re-infer from host).
#
# Every URL HEAD-verified 200, no redirect, 2026-05-17. campus/library
# "all" = university-wide (cross-campus guard passes "all").
#
# (url, campus, library, featured_service|None)
LIBGUIDE_SEED: Final[tuple[tuple[str, str, str, Optional[str]], ...]] = (
    ("https://libguides.lib.miamioh.edu/middletown_tec_lab/home",
     "middletown", "gardner_harvey", "makerspace"),
    ("https://libguides.lib.miamioh.edu/create/makerspace",
     "oxford", "king", "makerspace"),
    ("https://libguides.lib.miamioh.edu/newspapers",
     "all", "all", "newspapers"),
    ("https://libguides.lib.miamioh.edu/citation",
     "all", "all", None),
    ("https://libguides.lib.miamioh.edu/mul-circulation-policies",
     "all", "all", None),
    ("https://libguides.lib.miamioh.edu/reserves-textbooks/",
     "all", "all", None),
)


# --- Library inference from URL host + path ---------------------------------

# Host -> default campus (used when host appears in URL).
HOST_TO_CAMPUS: Final[dict[str, str]] = {
    "lib.miamioh.edu": "oxford",
    "www.lib.miamioh.edu": "oxford",
    "ham.miamioh.edu": "hamilton",
    "www.ham.miamioh.edu": "hamilton",
    "mid.miamioh.edu": "middletown",
    "www.mid.miamioh.edu": "middletown",
}

# Path-substring -> library canonical ID. Order matters: classify.py
# does first-match-wins. SPECIFIC overrides come BEFORE broad host
# defaults, so a `/sword/` URL on the Middletown host still resolves
# to SWORD instead of Gardner-Harvey.
LIBRARY_BY_URL_SUBSTRING: Final[tuple[tuple[str, str], ...]] = (
    # --- Specific path overrides (must come BEFORE host defaults) ---
    # Oxford-specific buildings
    ("/about/locations/king-library", "king"),
    ("/about/locations/art-arch", "wertz"),
    ("/about/locations/special-collections", "special"),
    ("wertz", "wertz"),
    # SWORD lives on the Middletown campus but is its own library;
    # the path-override beats the mid.miamioh.edu host default below.
    ("/sword/", "sword"),
    ("/depository/", "sword"),
    # --- Regional host defaults (broadest; checked last) ---
    ("ham.miamioh.edu", "rentschler"),
    ("mid.miamioh.edu", "gardner_harvey"),
)


# --- Chunking ---------------------------------------------------------------

CHUNK_TARGET_TOKENS: Final[int] = 400
CHUNK_OVERLAP_TOKENS: Final[int] = 50
CHUNK_MIN_TOKENS: Final[int] = 50  # drop chunks shorter than this (boilerplate)
# Hard upper bound on a single chunk's token count. Enforced by the chunker
# when a "sentence" (post sentence-splitter) is itself larger than the target:
# such sentences are hard-split into character windows of this size. The cap
# exists because OpenAI's text-embedding-3-large rejects inputs above 8192
# tokens with a 400, which causes the whole embed batch to fail silently
# (see scripts/etl/upsert.py::embed_chunks). 1000 leaves a 7x safety margin
# vs. the model limit and accommodates the ~50-token overlap prepend.
CHUNK_HARD_MAX_TOKENS: Final[int] = 1000


# --- Extraction quality gates -----------------------------------------------

EXTRACT_MIN_BODY_CHARS: Final[int] = 200  # reject pages with less text than this
EXTRACT_MAX_BOILERPLATE_RATIO: Final[float] = 0.80  # reject if 80%+ of text matches sitewide boilerplate


# --- Lifecycle / tombstoning ------------------------------------------------

# Days after which a tombstoned (deleted=true) Weaviate object is hard-deleted.
TOMBSTONE_GC_AGE_DAYS: Final[int] = 30


# --- Fetch policy ------------------------------------------------------------

REQUEST_TIMEOUT_SECONDS: Final[float] = 30.0
USER_AGENT: Final[str] = (
    "MiamiLibrariesChatbotETL/1.0 "
    "(+https://www.lib.miamioh.edu/about/contact/; "
    "operator: web dev team)"
)
MAX_REDIRECTS: Final[int] = 5


# --- Embedding batching -----------------------------------------------------

EMBED_BATCH_SIZE: Final[int] = 100  # OpenAI text-embedding-3-large allows up to 2048


# --- Output paths -----------------------------------------------------------

# Cache crawled HTML so failures don't re-fetch.
RAW_CACHE_DIR: Final[str] = str(_AI_CORE_ROOT / "data" / "raw")
# Diff reports for librarian review.
DIFF_REPORT_DIR: Final[str] = str(_AI_CORE_ROOT / "data" / "diffs")
# Pipeline checkpoint files (per-step state).
CHECKPOINT_DIR: Final[str] = str(_AI_CORE_ROOT / "data" / "checkpoints")
