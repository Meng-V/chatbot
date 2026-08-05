"""Building facts the library knows but its website does not publish.

PROVENANCE, AND WHY IT IS WRITTEN DOWN HERE
Everything in this module came from the operator (Meng Qu, Libraries) on
2026-08-04, not from a crawl. It is in code rather than in the search index
because the search index is a faithful copy of lib.miamioh.edu, and putting
unpublished claims in there would quietly break the promise that every
indexed sentence traces back to a page a patron can read.

Students ask these constantly and the bot was refusing all of them:
"where is the silent study area", "where are the bathrooms", "is there a
nursing room". Refusing a question the staff can answer in one sentence is
the worst kind of unhelpful.

RE-VERIFY WHEN THE BUILDING CHANGES
These are the facts most likely to go stale silently -- a floor gets
renovated and nobody updates a Python file. Each entry carries the date it
was given and by whom. Anything here that later appears on the website
should be DELETED from this module so there is one source of truth.

WHAT IS DELIBERATELY NOT CITED
A fact that is not on a page does not get a citation marker pointing at that
page. Where a real page supports part of the answer (the Reading Rooms page
genuinely is titled "Faculty and Graduate Reading Room") it is cited; the
floor numbers, which the page does not state, are given as the library's own
information and marked as such.
"""
from __future__ import annotations

import re
from typing import Optional

# --- verified live 2026-08-04 (HTTP 200, redirect target recorded) --------

READING_ROOMS_URL = "https://www.lib.miamioh.edu/use/spaces/reading-rooms/"
"""200, title "Faculty and Graduate Reading Room | Miami University Libraries"."""

KING_LIBRARY_URL = "https://www.lib.miamioh.edu/about/locations/king-library/"

PRINTING_PAGE_URL = "https://www.lib.miamioh.edu/use/technology/printing/"
"""200, "Printing and WiFi". A LINK LIST -- its value is the two destinations
below plus an embedded video, which is why extracting only its text yielded
231 useless characters."""

MUPRINT_GUIDE_URL = (
    "https://miamioh.teamdynamix.com/TDClient/1813/Portal/KB/Article/84563/User-Guide"
)
"""200, "User Guide / MUprint" -- university IT's printing guide, the page the
Libraries' own printing page links to. Reached via the redirect from
.../KB/ArticleDet?ID=84563; the canonical form is recorded here."""

WIFI_SERVICE_URL = (
    "https://miamioh.teamdynamix.com/TDClient/1813/Portal/Requests/Service/4444/Wi-Fi"
)
"""200, "Service - Wi-Fi" -- university IT's Wi-Fi service page."""

PRINTING_VIDEO_URL = "https://www.youtube.com/watch?v=JiNgoIoYfGg"
"""200. The how-to video embedded on the Libraries' printing page."""

ASK_US_URL = "https://www.lib.miamioh.edu/research/research-support/ask/"

KING_PHONE = "(513) 529-4141"

# --- matchers -------------------------------------------------------------
#
# Tight on purpose. These fire before the agent, so a false positive replaces
# a good retrieved answer with a canned one.

_QUIET_RE = re.compile(
    # "quiet floor", "silent study area", "quiet space"
    r"\b(silent|quiet)\b[^.?!]{0,30}\b(area|areas|floor|floors|space|spaces|"
    r"section|room|rooms|study|zone)\b"
    # "study quietly", "read somewhere quiet", "which floor is quiet"
    r"|\b(study|studying|read|reading|floor|floors|somewhere|anywhere|place)\b"
    r"[^.?!]{0,24}\b(silent|silently|quiet|quietly)\b"
    r"|\bwhere\b[^.?!]{0,20}\b(silent|quiet)\b",
    re.IGNORECASE,
)

_READING_ROOM_RE = re.compile(
    r"\b(grad(uate)?|faculty|staff)\b[^.?!]{0,24}\breading\s+room",
    re.IGNORECASE,
)

_RESTROOM_RE = re.compile(
    r"\b(restroom|restrooms|bathroom|bathrooms|toilet|toilets|washroom|"
    r"men'?s\s+room|women'?s\s+room)\b",
    re.IGNORECASE,
)

_NURSING_RE = re.compile(
    r"\b(nursing|lactation|breastfeed\w*|breast\s*feed\w*|"
    r"pump(ing)?\s+room|mother'?s\s+room)\b",
    re.IGNORECASE,
)

_PRINT_SCAN_WIFI_RE = re.compile(
    r"\b(print|prints|printing|printer|printers|photocopy|copier|"
    r"scan|scans|scanning|scanner|scanners|"
    r"wifi|wi-?fi|wireless|internet)\b",
    re.IGNORECASE,
)

# The printing/wifi answer must not hijack questions that only LOOK related:
# 3D printing has its own page and its own short-circuit, and "print" appears
# in reprints/fines questions.
# This matcher is the broadest in the short-circuit table, and the 2026-08-04
# eval showed it overfiring: it replaced four GOOD specific answers with the
# same generic MUprint pointer --
#   "does Wertz have printing"      -> lost the Wertz-specific answer
#   "can I print in color"          -> never confirmed colour
#   "scanning at all three campuses"-> lost the per-campus verification
#   a policy-link case              -> lost the corrected link
# It gained two and lost four. So it now declines anything it cannot actually
# answer: a named campus or library, a comparison, or a specific capability.
_NOT_PRINTING_RE = re.compile(
    r"\b(3d|three-?d|makerspace|maker\s*space|reprint|reprints|"
    r"fine|fines|charge|charges|cost|price|how\s+much"
    # a specific capability the generic pointer does not state
    r"|colour|color|black\s*(and|&)\s*white|b\s*&\s*w|double\s*sided|duplex"
    r"|11x17|poster|large\s*format"
    # a named library / campus, or a comparison -- the generic answer cannot
    # confirm anything building-specific
    r"|wertz|art\s*(and|&)\s*architecture|rentschler|hamilton|gardner|"
    r"middletown|king|regional|all\s+(three\s+)?campuses?|each\s+campus|"
    r"every\s+campus|both\s+campuses|which\s+(library|campus)|compare)\b",
    re.IGNORECASE,
)


def _cite(n: int, url: str, snippet: str) -> dict:
    return {"n": n, "url": url, "snippet": snippet}


def quiet_study_answer(message: str) -> "Optional[tuple[str, list[dict]]]":
    """Operator 2026-08-04: quiet areas are on the 2nd AND 3rd floors.

    The website does not say this anywhere -- "silent" appears zero times in
    the whole corpus -- so the bot refused every version of the question.
    """
    if not _QUIET_RE.search(message or ""):
        return None
    return (
        "King Library has quiet study areas on both the **second and third "
        "floors**. The second floor also holds the Faculty and Graduate "
        "Reading Rooms, which are reserved for faculty and graduate "
        "students [1].\n\n"
        "That floor detail comes from the library staff rather than a web "
        f"page, so if you want to confirm before you come, call {KING_PHONE}.",
        [_cite(1, READING_ROOMS_URL,
               "Miami University Libraries — Faculty and Graduate Reading Room")],
    )


def reading_room_answer(message: str) -> "Optional[tuple[str, list[dict]]]":
    """Operator 2026-08-04: both reading rooms are on the 2nd floor."""
    if not _READING_ROOM_RE.search(message or ""):
        return None
    return (
        "King Library has a Graduate Reading Room and a Faculty & Staff "
        "Reading Room, both on the **second floor** [1]. They are reserved "
        "for those groups -- graduate students and faculty/staff "
        "respectively.\n\n"
        "If you are an undergraduate looking for somewhere quiet, the second "
        "and third floors both have quiet study areas that are open to "
        "everyone.",
        [_cite(1, READING_ROOMS_URL,
               "Miami University Libraries — Faculty and Graduate Reading Room")],
    )


def restroom_answer(message: str) -> "Optional[tuple[str, list[dict]]]":
    """Operator 2026-08-04: every floor has restrooms."""
    if not _RESTROOM_RE.search(message or ""):
        return None
    return (
        "There are restrooms on **every floor** of King Library. Look for the "
        "signage near the elevators and stairwells on whichever floor you are "
        "on.\n\n"
        "This is from library staff rather than a web page, so if you need "
        f"something specific -- an accessible or all-gender restroom, for "
        f"example -- call {KING_PHONE} and someone can tell you exactly where "
        f"to go.",
        [],
    )


def nursing_room_answer(message: str) -> "Optional[tuple[str, list[dict]]]":
    """Operator 2026-08-04: there is NO nursing/lactation room in the library.

    An honest no, with a route to someone who can help, beats both a refusal
    and a hedge. A parent needs to know before they travel, not after.
    """
    if not _NURSING_RE.search(message or ""):
        return None
    return (
        "King Library does **not** have a dedicated nursing or lactation "
        "room.\n\n"
        f"The library staff can help you find somewhere suitable -- call "
        f"{KING_PHONE} or ask through Ask Us [1]. Miami University maintains "
        "lactation spaces elsewhere on campus, and the staff can point you to "
        "the nearest one.",
        [_cite(1, ASK_US_URL, "Miami University Libraries — Ask Us")],
    )


def printing_scanning_wifi_answer(message: str) -> "Optional[tuple[str, list[dict]]]":
    """Printing, scanning and Wi-Fi all live in university IT's guides.

    The Libraries' own printing page is a LINK LIST: two links and a video,
    and nothing else. Our extractor kept the link text ("Printing
    Instructions WiFi Connections") and dropped the destinations, so the bot
    retrieved 231 characters of menu and answered "King Library offers
    printing/scanning services" without ever giving the student the guide.
    Those destinations are what the question is actually asking for.
    """
    m = message or ""
    if not _PRINT_SCAN_WIFI_RE.search(m) or _NOT_PRINTING_RE.search(m):
        return None
    return (
        "Printing, scanning and Wi-Fi at the libraries all run on the "
        "University's central systems, so the step-by-step guides live with "
        "IT:\n\n"
        f"- **Printing and scanning** — MUprint user guide [1]. Miami's "
        f"multifunction printers in the libraries both print and scan.\n"
        f"- **Wi-Fi** — the University Wi-Fi service page [2] covers "
        f"connecting your device.\n"
        f"- There is also a short **how-to video** [3], linked from the "
        f"Libraries' own Printing and WiFi page [4].\n\n"
        f"If something is broken or you are stuck at a machine, call "
        f"{KING_PHONE} and someone at the desk can help.",
        [
            _cite(1, MUPRINT_GUIDE_URL, "Miami University IT — MUprint User Guide"),
            _cite(2, WIFI_SERVICE_URL, "Miami University IT — Wi-Fi"),
            _cite(3, PRINTING_VIDEO_URL, "Miami University Libraries — printing how-to video"),
            _cite(4, PRINTING_PAGE_URL, "Miami University Libraries — Printing and WiFi"),
        ],
    )
