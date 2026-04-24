"""
Canonical campus / library IDs and the alias table that maps every
user-facing name to its canonical (campus, library) tuple.

This is the single source of truth for scope vocabulary. New aliases
are added as a one-line edit here -- no retraining, no model changes.

See plan: Data preparation playbook §8 -- Campus and library scope resolution.

================================================================================
DESIGN NOTES
================================================================================

- IDs are short snake_case ASCII so they're safe to use as Weaviate filter
  values, Postgres column literals, and URL slugs.
- Aliases are matched by lowercased substring (longest-match-wins) in
  `resolver.py`. Be specific: "Art and Architecture Library" must come BEFORE
  "Art" so the longer phrase wins.
- A `null` library means "campus matched but no specific building" -- the
  retriever returns campus-wide content and ranking surfaces the right place.
"""

from typing import Literal


# --- Canonical IDs -----------------------------------------------------------

Campus = Literal["oxford", "hamilton", "middletown"]
Library = Literal[
    "king",
    "wertz",
    "special",
    "rentschler",
    "gardner_harvey",
    "sword",
]

CAMPUSES: tuple[Campus, ...] = ("oxford", "hamilton", "middletown")
LIBRARIES: tuple[Library, ...] = (
    "king",
    "wertz",
    "special",
    "rentschler",
    "gardner_harvey",
    "sword",
)

# Which library belongs to which campus. Used by retrieval to enforce the
# cross-campus refusal: a chunk's `library` and `campus` must agree.
LIBRARY_TO_CAMPUS: dict[Library, Campus] = {
    "king": "oxford",
    "wertz": "oxford",
    "special": "oxford",
    "rentschler": "hamilton",
    "gardner_harvey": "middletown",
    "sword": "middletown",
}

# --- Display names (for refusal messages, UI chips, log output) -------------

CAMPUS_DISPLAY: dict[Campus, str] = {
    "oxford": "Oxford",
    "hamilton": "Hamilton",
    "middletown": "Middletown",
}

LIBRARY_DISPLAY: dict[Library, str] = {
    "king": "King Library",
    "wertz": "Wertz Art & Architecture Library",
    "special": "Special Collections and University Archives",
    "rentschler": "Rentschler Library",
    "gardner_harvey": "Gardner-Harvey Library",
    "sword": "Southwest Ohio Regional Depository (SWORD)",
}

# --- Aliases -----------------------------------------------------------------
#
# Order matters: in `resolver.py` we iterate the alias table and pick the
# LONGEST matching substring, so listing more-specific phrases first is a
# safety net (defensive against future refactors that might do prefix-match).
#
# All keys are lowercased ASCII. The matcher lowercases the user input.

LIBRARY_ALIASES: dict[str, Library] = {
    # King Library (Oxford main building) -- the default if "the library"
    # is mentioned without context.
    "edward king library": "king",
    "edward w king library": "king",
    "edward w. king library": "king",
    "ew king": "king",
    "e.w. king": "king",
    "king library": "king",
    "king": "king",
    "main library": "king",

    # Wertz / Art & Architecture (Oxford second building)
    "wertz art and architecture library": "wertz",
    "wertz art & architecture library": "wertz",
    "art and architecture library": "wertz",
    "art & architecture library": "wertz",
    "a&a library": "wertz",
    "a & a library": "wertz",
    "art library": "wertz",
    "wertz library": "wertz",
    "wertz": "wertz",

    # Special Collections (Oxford, housed in King)
    "special collections and university archives": "special",
    "special collections & university archives": "special",
    "special collections": "special",
    "university archives": "special",
    "the archives": "special",
    "scua": "special",

    # Rentschler (Hamilton)
    "rentschler library": "rentschler",
    "rentschler": "rentschler",
    "hamilton library": "rentschler",
    "hamilton campus library": "rentschler",
    "library at hamilton": "rentschler",
    "the library at hamilton": "rentschler",

    # Gardner-Harvey (Middletown)
    "gardner-harvey library": "gardner_harvey",
    "gardner harvey library": "gardner_harvey",
    "gardner-harvey": "gardner_harvey",
    "gardner harvey": "gardner_harvey",
    "middletown library": "gardner_harvey",
    "middletown campus library": "gardner_harvey",
    "library at middletown": "gardner_harvey",
    "the library at middletown": "gardner_harvey",

    # SWORD (Middletown)
    "southwest ohio regional depository": "sword",
    "regional depository": "sword",
    "the depository": "sword",
    "sword": "sword",
}

CAMPUS_ALIASES: dict[str, Campus] = {
    "oxford campus": "oxford",
    "oxford": "oxford",
    "main campus": "oxford",
    "flagship campus": "oxford",
    "miami main": "oxford",

    "hamilton campus": "hamilton",
    "hamilton": "hamilton",
    "miami hamilton": "hamilton",
    "muh": "hamilton",
    "muham": "hamilton",

    "middletown campus": "middletown",
    "middletown": "middletown",
    "miami middletown": "middletown",
    "mum": "middletown",
    "mumid": "middletown",
}

# --- Domain → campus mapping (for session-origin detection) ------------------
#
# The chat widget passes through the originating page's domain at connect
# time so a regional-campus user gets the right default. See playbook §8.

DOMAIN_TO_CAMPUS: dict[str, Campus] = {
    "lib.miamioh.edu": "oxford",
    "www.lib.miamioh.edu": "oxford",
    "ham.miamioh.edu": "hamilton",
    "www.ham.miamioh.edu": "hamilton",
    "mid.miamioh.edu": "middletown",
    "www.mid.miamioh.edu": "middletown",
}


# --- Validation helpers ------------------------------------------------------

def is_valid_campus(value: str) -> bool:
    return value in CAMPUSES


def is_valid_library(value: str) -> bool:
    return value in LIBRARIES


def library_belongs_to_campus(library: Library, campus: Campus) -> bool:
    """True iff the given library is on the given campus.

    Used by the synthesizer post-processor to detect cross-campus citation
    leaks: if a cited chunk's library doesn't match the resolved scope's
    campus, the answer is downgraded to a refusal.
    """
    return LIBRARY_TO_CAMPUS.get(library) == campus
