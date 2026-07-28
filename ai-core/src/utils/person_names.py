"""
Person-name normalization -- the ONE place names get compared.

Operator rule 2026-07-28: middle names and middle initials are ignored
everywhere, as is punctuation (apostrophes, hyphens, periods). This
applies to BOTH sides of every comparison -- what a patron types and what
a system stores -- because the same human appears in three spellings
across our sources:

    Librarian table   "Roger A Justus"    "Alia Levar Wegner"
    LibGuides API     "Roger Justus"      "Alia Wegner"
    patron types      "roger justus"      "alia wegner"

Before this, matching was a `contains` on the whole string, so
"Roger Justus" simply missed "Roger A Justus" and the lookup fell back to
guessing -- which is how the bot came to hand out the wrong person's
email twice in one day.

Pure functions, no I/O: cheap enough to call per candidate row.
"""

from __future__ import annotations

import re
import unicodedata

# Titles and suffixes are not part of a name for matching purposes.
_STRIP_TOKENS = frozenset({
    "dr", "prof", "professor", "mr", "mrs", "ms", "mx",
    "jr", "sr", "ii", "iii", "iv", "phd", "mls", "mlis", "ma", "msc",
})


def normalize_words(name: object) -> tuple[str, ...]:
    """Split a name into comparable words.

    Lower-cased, accents folded, punctuation dropped entirely (so
    "O'Brien" -> "obrien" and "Jones-Scott" -> "jonesscott"), titles and
    suffixes removed, and single letters dropped so a middle INITIAL
    never participates in a match.

    >>> normalize_words("Roger A Justus")
    ('roger', 'justus')
    >>> normalize_words("Rob O'Brien Withers")
    ('rob', 'obrien', 'withers')
    """
    text = unicodedata.normalize("NFKD", str(name or ""))
    text = "".join(c for c in text if not unicodedata.combining(c))
    # Punctuation is removed rather than split on, so a hyphenated or
    # apostrophised surname stays ONE word instead of becoming two.
    text = re.sub(r"[^\w\s]", "", text.lower())
    words = [w for w in text.split() if len(w) > 1 and w not in _STRIP_TOKENS]
    return tuple(words)


def first_last(name: object) -> tuple[str, str]:
    """The (first, last) pair with everything in between discarded.

    This is the operator's rule in one function: a middle name is as
    ignorable as a middle initial. Returns ("", "") when there aren't two
    usable words.
    """
    words = normalize_words(name)
    if len(words) < 2:
        return ("", "")
    return (words[0], words[-1])


def names_match(query: object, stored: object) -> bool:
    """True when `query` and `stored` denote the same person.

    Two ways to match, because neither alone is enough:

      1. first + last agree, middles ignored -- handles
         "Roger Justus" vs "Roger A Justus" and
         "Alia Wegner" vs "Alia Levar Wegner".
      2. every word of the query appears in the stored name -- handles a
         partial ask like "Rob O'Brien" against "Rob O'Brien Withers",
         which rule 1 would miss because the last words differ.

    A single-word query ("Boehme") matches on rule 2 alone, which is why
    callers must still cap how many people they present.
    """
    q_words = normalize_words(query)
    s_words = normalize_words(stored)
    if not q_words or not s_words:
        return False
    qf, ql = first_last(query)
    sf, sl = first_last(stored)
    if qf and sf and qf == sf and ql == sl:
        return True
    return set(q_words) <= set(s_words)


def display_name(name: object) -> str:
    """The name as we should SAY it: first + last, middles dropped.

    Keeps the source's own capitalisation and punctuation for the words
    it keeps, so "Rob O'Brien Withers" reads "Rob Withers" rather than
    "rob withers".
    """
    raw = [w for w in re.split(r"\s+", str(name or "").strip()) if w]
    keep = [w for w in raw
            if len(re.sub(r"[^\w]", "", w)) > 1
            and re.sub(r"[^\w]", "", w).lower() not in _STRIP_TOKENS]
    if len(keep) < 2:
        return " ".join(keep) or str(name or "").strip()
    return f"{keep[0]} {keep[-1]}"


__all__ = ["display_name", "first_last", "names_match", "normalize_words"]
