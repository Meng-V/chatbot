"""ai-core package root.

Side effect on import: silence ONE specific, verified-harmless
third-party warning.

`prisma-client-py` 0.15.0 emits a `UserWarning` from `prisma._compat`
on import under Python 3.14+: "Core Pydantic V1 functionality isn't
compatible with Python 3.14 or greater." We pin prisma 0.15.0 (it is
the version compatible with our Prisma engine / JS toolchain) and run
on Python 3.14.5 deliberately. The warning fires because prisma keeps
a `pydantic.v1` shim it does not exercise on our code paths: this was
empirically verified — `connect()`, `count()`, and the
`UrlSeen`/`ChunkProvenance` CRUD the app actually uses all work at
runtime on 3.14.5 (UrlSeen round-trips 396 rows against the shared
Postgres). The warning is therefore cosmetic, but it prints on EVERY
process start (tests, eval, ETL, API) and that log noise is exactly
the alert-fatigue the observability plan (Op 3) warns against.

The filter is intentionally narrow — exact message prefix + category
+ originating module — so it cannot mask any other pydantic/prisma
warning. Installed here because `src/__init__` runs before any
`src.*` submodule executes its top-level `from prisma import Prisma`.

Revisit when prisma-client-py ships a release that drops the
pydantic-v1 shim (or supports py3.14 cleanly) — then delete this.
"""

from __future__ import annotations

import warnings

warnings.filterwarnings(
    "ignore",
    message=r"Core Pydantic V1 functionality isn't compatible with Python 3\.14",
    category=UserWarning,
    module=r"prisma\._compat",
)
