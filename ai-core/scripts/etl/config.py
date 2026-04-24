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

from typing import Final


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
        "https://www.mid.miamioh.edu/library/",
        "https://www.mid.miamioh.edu/library/about/",
        "https://www.mid.miamioh.edu/library/services/",
        "https://www.mid.miamioh.edu/library/research/",
        # Add more as the librarian liaisons identify priority pages.
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
EXCLUDE_URL_PREFIXES: Final[tuple[str, ...]] = (
    "/about/news-events/",
    "/news/",
    "/events/",
    "/exhibits/",
    "/blog/",
    "/test/",
    "/staging/",
    "/dev/",
)

# Specific path patterns to drop in addition to the prefixes above.
EXCLUDE_URL_SUBSTRINGS: Final[tuple[str, ...]] = (
    "readme",
    "/404",
    "/test-page",
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

# Path-substring -> library canonical ID. Inside Oxford domain, this
# disambiguates between King, Wertz, Special Collections. Regional domains
# default to their primary library unless overridden here.
LIBRARY_BY_URL_SUBSTRING: Final[tuple[tuple[str, str], ...]] = (
    # Oxford
    ("/about/locations/king-library", "king"),
    ("/about/locations/art-arch", "wertz"),
    ("/about/locations/special-collections", "special"),
    ("wertz", "wertz"),
    # Regional defaults baked in; overrides below.
    ("ham.miamioh.edu", "rentschler"),
    ("mid.miamioh.edu", "gardner_harvey"),
    ("/sword/", "sword"),
    ("/depository/", "sword"),
)


# --- Chunking ---------------------------------------------------------------

CHUNK_TARGET_TOKENS: Final[int] = 400
CHUNK_OVERLAP_TOKENS: Final[int] = 50
CHUNK_MIN_TOKENS: Final[int] = 50  # drop chunks shorter than this (boilerplate)


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
RAW_CACHE_DIR: Final[str] = "ai-core/data/raw"
# Diff reports for librarian review.
DIFF_REPORT_DIR: Final[str] = "ai-core/data/diffs"
# Pipeline checkpoint files (per-step state).
CHECKPOINT_DIR: Final[str] = "ai-core/data/checkpoints"
