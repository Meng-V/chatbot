"""Add morphological variants to the keyword half of a hybrid query.

WHY THIS EXISTS
Weaviate 1.28.6 offers WORD, WHITESPACE, LOWERCASE, FIELD, TRIGRAM and the
CJK tokenizers. **None of them stems English.** WORD lowercases and splits
on non-alphanumerics, so "charger" and "Chargers" are different terms and
BM25 scores one of them zero. There is no tokenization setting that fixes
this and no reindex that would help.

Measured on the live index 2026-08-04, against a page that literally reads
"Chargers (Mac, PC, assorted phones)":

    "Chargers"       -> 1 hit, the right page
    "charger"        -> 0 hits
    "phone charger"  -> 3 hits, none of them the right page

Two eval cases failed exactly there: the bot answered "the equipment list
provided does not specify charger cables" while the chunk in the index
listed them. Students type the singular, so the keyword leg of hybrid was
dead for a whole class of question.

WHAT THIS DOES, AND WHAT IT DELIBERATELY DOES NOT
Expands only the BM25 string, by appending plural/singular variants of
content words. The vector leg keeps the ORIGINAL query, so semantic search
is untouched -- appending noise to the embedded text would blur it.

Rules are deliberately narrow English morphology, no stemming library:
a real stemmer would also collapse "printing"->"print" and
"borrowing"->"borrow", which changes what BM25 ranks rather than just
widening it. Widening is safe here because BM25 is a scoring function, not
a filter -- an extra term that matches nothing costs nothing.
"""
from __future__ import annotations

import re

# Words we never expand: too short to be meaningful, or function words whose
# variants would add noise to every query.
_STOP = frozenset("""
a an the and or but if of in on at to for from by with without about into
is are was were be been being do does did doing have has had having
i you he she it we they me him her us them my your his its our their this
that these those there here what which who whom whose when where why how
can could may might must shall should will would not no nor so than then
too very just also as any some each all both few more most other own same
""".split())

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]*")

# Irregulars worth having: these appear in library questions and no suffix
# rule would produce them.
_IRREGULAR = {
    "shelves": "shelf", "shelf": "shelves",
    "children": "child", "child": "children",
    "people": "person", "person": "people",
    "theses": "thesis", "thesis": "theses",
    "indices": "index", "index": "indices",
    "appendices": "appendix", "appendix": "appendices",
    "media": "medium", "medium": "media",
    "criteria": "criterion", "criterion": "criteria",
    "analyses": "analysis", "analysis": "analyses",
}

# Suffix pairs that need no special casing beyond a plain "s".
_ES_ENDINGS = ("s", "x", "z", "ch", "sh")


def _variants(word: str) -> "set[str]":
    """Plural<->singular variants of one lowercase word."""
    out: set[str] = set()
    if word in _IRREGULAR:
        out.add(_IRREGULAR[word])
        return out
    if word.endswith("ies") and len(word) > 4:
        out.add(word[:-3] + "y")            # policies -> policy
    elif word.endswith("es") and len(word) > 3:
        out.add(word[:-2])                  # boxes -> box
        out.add(word[:-1])                  # printers... (printere) is junk,
        # but harmless: an unmatched BM25 term scores nothing. Kept because
        # "cases"->"case" needs the -1 form and "boxes"->"box" needs -2, and
        # guessing wrong in the safe direction beats missing the right one.
    elif word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        out.add(word[:-1])                  # chargers -> charger
    else:
        if word.endswith("y") and len(word) > 2 and word[-2] not in "aeiou":
            out.add(word[:-1] + "ies")      # policy -> policies
        elif word.endswith(_ES_ENDINGS):
            out.add(word + "es")            # box -> boxes
        else:
            out.add(word + "s")             # charger -> chargers
    out.discard(word)
    return {v for v in out if len(v) > 2}


def expand_for_bm25(query: str, *, max_terms: int = 24) -> str:
    """The query plus morphological variants, for the BM25 leg only.

    Returns the original string unchanged when there is nothing useful to
    add, so the common case costs nothing and the logs stay readable.

    `max_terms` bounds the result: a long pasted paragraph should not turn
    into a hundred-term BM25 query, which would flatten the scoring it is
    supposed to sharpen.
    """
    text = (query or "").strip()
    if not text:
        return text
    seen: set[str] = set()
    extra: list[str] = []
    for m in _WORD_RE.finditer(text):
        word = m.group(0).lower()
        if len(word) < 4 or word in _STOP or word in seen:
            continue
        seen.add(word)
        for v in sorted(_variants(word)):
            if v not in seen and len(extra) < max_terms:
                seen.add(v)
                extra.append(v)
    if not extra:
        return text
    return f"{text} {' '.join(extra)}"
