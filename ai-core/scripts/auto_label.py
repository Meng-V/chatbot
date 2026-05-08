"""
Comprehensive auto-labeler for exemplars_for_labeling.csv.

Goes beyond the basic keyword heuristic in clean_libchat_transcripts.py.
For each utterance, computes a confidence score per intent using:

  - STRONG phrases (decisive signals; score 5)
  - PHRASES (medium signals; score 3)
  - KEYWORDS (single word hints; score 1)
  - NEGATIVE phrases (subtract from score; rule out competing intents)
  - REGEX patterns for shape-based matching

Then applies intent-specific overrides (e.g., circulation hard-override
for "place a hold" / "did my request" / "get a confirmation" already
present from the cleaner -- replicated and tightened here).

Decision rule:
  - Top intent score >= STRONG_THRESHOLD (4.0) -> label
  - Top - runner_up >= MIN_MARGIN (2.0) -> label
  - Otherwise leave blank (ambiguous)

Caps per intent at ~80 (prefer diverse examples; skip near-duplicates
once a bucket fills).

Writes the labeled CSV back in place. Also prints per-intent counts
and 5 sample utterances per intent for the librarian to verify.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

# Allow `python -m scripts.auto_label` from ai-core/.
_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent
sys.path.insert(0, str(_AI_CORE))

from src.router.intent_knn import INTENTS  # noqa: E402


# ============================================================================
# PATTERN TABLE
# ============================================================================
#
# Each intent has up to 4 buckets:
#   strong:    decisive phrases (weight 5; near-certain signal)
#   phrases:   reasonable phrases (weight 3)
#   keywords:  single-word hints (weight 1)
#   negative:  phrases that PENALIZE this intent (-3 each)
#
# Carefully curated by reading the MU library website (lib.miamioh.edu/use/
# and /research/) + the user's flagged failure modes.
#
# Order: I list the bigger / more-frequent buckets first because in case of
# a near-tie the alphabetically-first bucket wins -- listing the more
# common one first reduces tie-breaking ambiguity.

PATTERNS: dict[str, dict[str, list[str]]] = {

    # ============================================================
    # Borrow / circulation
    # ============================================================

    "circulation_basic": {
        "strong": [
            "place a hold", "place hold", "put a hold", "put hold",
            "did my hold", "hold went through",
            "did my request", "did the request",
            "request went through", "request go through",
            "get a confirmation", "get confirmation",
            "ready for pickup", "ready to pick up", "ready for pick up",
            "when my book", "when the book is ready", "book is ready",
            "when my hold", "is my hold ready",
            "home delivery", "curbside pickup", "department delivery",
            "dorm delivery",
            "request for pickup", "request a book for pickup",
            "request a book", "request a copy", "book request",
            "checkout a book", "check out a book", "checking out a book",
            "how do i borrow", "how to borrow", "how does borrowing",
            "i'd like to request", "i would like to request",
        ],
        "phrases": [
            "request a copy", "hold on a book", "hold on the book",
            "notified when", "pick up my", "pickup my",
            "place a request", "submit a request",
            "request sent", "submitted a request",
            "from storage", "storage request", "sw depository",
            "swords depository", "southwest depository",
        ],
        "keywords": ["pickup", "checkout", "borrow"],
        "negative": [
            "interlibrary", "ohiolink", "ohio link", "worldcat",
            "world cat", "another library", "another university",
            "another school", "different library",
            "miami doesn't have", "miami doesn't own", "you don't have",
            "renew", "renewal",
        ],
    },

    "interlibrary_loan": {
        "strong": [
            "interlibrary loan", "inter-library loan", "inter library loan",
            "ohiolink", "ohio link", "worldcat", "world cat", "illiad",
            "from another library", "from another university",
            "from a different library", "from another school",
            "miami doesn't have", "miami doesn't own", "miami does not have",
            "not in your collection", "not at miami",
            "ill request", "ill book", "ill form", "ill page",
            "borrow from another", "borrow from a different",
            "article delivery", "lending service",
        ],
        "phrases": [
            "you don't have", "don't have it",
            "another library", "request from ohiolink",
            "ill book", "interlibrary",
        ],
        "keywords": ["ill"],
        "negative": [
            "place a hold on a miami", "miami's copy",
        ],
    },

    "renewal": {
        "strong": [
            "renew my book", "renew my checkout", "renew my loan",
            "renew the book", "extend my checkout",
            "extend the due date", "extend due date",
            "can i renew", "how do i renew", "how to renew",
            "renewal limit", "renew this book",
            "renew a book", "renew the books",
            "many times can i renew", "how many times can i renew",
            "how do i renew",
            "renew online", "renew my books", "renew this",
        ],
        "phrases": [
            "extend my", "extend the loan",
        ],
        "keywords": [],
        "negative": [
            "interlibrary loan", "subscription",
            # Book titles containing "renewal" -- common false positive
            # for academic/architecture/urban titles.
            "urban renewal", "renewal of berlin", "renewal of cities",
            "spiritual renewal", "the renewal of",
        ],
    },

    "loan_policy": {
        "strong": [
            "loan period", "how long can i keep",
            "how long can i borrow",
            "checkout period", "borrowing period",
            "due date policy",
            "loan policy", "borrowing policy",
            "fines and charges",
        ],
        "phrases": [
            # Less load-bearing -- can falsely fire on tech/printing
            # questions like "how many days" for poster printing.
        ],
        "keywords": [],
        "negative": [
            # If user is asking about THEIR fines/fees -> account.
            "my fines", "my fees", "i owe", "i have fees",
            "i have late fees", "i have a late fee",
            "i have overdue", "my late fee", "pay my fine",
            "renew",
            # Tech-checkout questions often phrase as "how long can I have X"
            "speaker", "calculator", "laptop", "chromebook",
            "ipad", "tablet", "camera", "tripod", "microphone",
            # Printing questions
            "poster", "printing",
            # ILL through OhioLINK has its own loan policy distinct
            # from regular MU policy -- that's an ILL question.
            "ohiolink", "ohlink", "ohio link", "ohio link",
            "another college", "another university", "another school",
            "different college", "different university",
            "cuyahoga", "ohio state", "akron",  # ohio-link partner schools
        ],
    },

    "account": {
        "strong": [
            "my library account", "my library fines", "my library fees",
            "my fines", "my fees", "my late fee", "my late fees",
            "what i owe", "how much do i owe", "how much i owe",
            "books i have checked out", "what i have checked out",
            "books i checked out", "books i borrowed",
            "my checkouts", "my borrowed",
            "see my account", "check my account",
            "my borrowing history", "my loan history",
            "my borrowed books", "my library card",
            "i have late fees", "i have a late fee",
            "i have fees to pay", "pay my fines", "pay my fine",
        ],
        "phrases": [
            "i have checked out",
            "do i owe", "my holds",
        ],
        "keywords": [],
        "negative": [
            "loan period", "how long can i", "policy", "in general",
            "place a hold", "renew",
            # Excludes "deactivated email account" cases
            "email account", "muneutid account",
            # Tech/software accounts
            "adobe account", "creative cloud account",
            "ohiolink account",  # subset of ILL
        ],
    },

    "course_reserves": {
        "strong": [
            "course reserve", "course reserves",
            "class reserve", "class reserves",
            "professor put on reserve", "professor placed on reserve",
            "professor put", "professor placed",
            "on reserve for my class", "on reserve for my course",
            "reserve for my class", "reserve for my course",
            "textbook on reserve", "reserve textbook",
            "reserve a textbook", "books on reserve",
            "is on reserve",
        ],
        "phrases": [
            "reserves desk", "reserve desk",
            "reserve material",
        ],
        "keywords": [],
        "negative": [
            "reserve a room", "reserve a study room", "room reservation",
        ],
    },

    "find_resource": {
        "strong": [
            "do you have a copy of", "do you have the book",
            "do you have an article", "do you have the article",
            "is this book available", "is the book available",
            "looking for a book", "looking for an article",
            "looking for the book",
            "where can i find a book", "where can i find an article",
            "find a book by", "find an article by",
            "i'm trying to find", "i am trying to find",
            "trying to locate",
            "can i find", "where can i find",
            "do you carry", "does the library carry",
            "can i get a copy", "can i get the book",
            "i need a book", "i need an article",
            "search the catalog", "search the library catalog",
            "primo search", "in the catalog",
        ],
        "phrases": [
            "looking for", "in your collection",
            "does the library have a", "does the library have the",
            "does miami have a", "does miami have the",
            "have a book about", "have a book on",
        ],
        "keywords": [],
        "negative": [
            "interlibrary", "ohiolink", "ohio link", "worldcat",
            "another library", "another university",
            "renew", "place a hold", "did my request",
            "course reserve", "professor put",
            "database", "jstor", "ebsco", "psycinfo",
            "looking for a librarian", "looking for the librarian",
            "looking for help",
        ],
    },

    "databases": {
        "strong": [
            "jstor", "ebsco", "ebscohost", "proquest", "psycinfo",
            "lexisnexis", "nexis uni", "lexis nexis",
            "scopus", "web of science", "web of knowledge",
            "pubmed", "medline", "cinahl", "eric database",
            "academic search", "business source",
            "communication abstracts", "sociological abstracts",
            "mla international bibliography",
            "databases a-z", "databases a to z", "database list",
            "what databases", "research databases",
            "database access", "access to a database",
        ],
        "phrases": [
            "scholarly database", "online database",
            "subject database", "subscription database",
            "find articles", "find an article in",
            "scholarly articles", "peer reviewed articles",
            "peer-reviewed articles",
            "biology databases", "history databases",
            "psychology databases", "nursing databases",
            "education databases",
            "biology database", "history database",
        ],
        "keywords": ["database", "databases"],
        "negative": [
            "do you have a copy of", "looking for a book",
            "place a hold", "interlibrary",
        ],
    },

    "citation_help": {
        "strong": [
            "apa citation", "mla citation", "chicago citation",
            "turabian citation", "ieee citation",
            "apa format", "mla format", "chicago format",
            "citation generator", "citation tool", "citation guide",
            "how to cite", "how do i cite",
            "cite a website", "cite a book", "cite an article",
            "zotero help", "endnote help", "mendeley help",
            "refworks help",
            "citing sources", "citing a source",
            "works cited", "reference list", "reference page",
        ],
        "phrases": [
            "citation style", "citation manager",
            "in-text citation", "bibliography",
            "zotero", "endnote", "mendeley", "refworks",
        ],
        "keywords": [],
        "negative": [
            "blacklist citation", "court citation",
        ],
    },

    "research_consultation": {
        "strong": [
            "research appointment", "research consultation",
            "schedule a research", "schedule research",
            "meet with a librarian", "meet with the librarian",
            "appointment with a librarian", "appointment with the librarian",
            "appointment to meet", "schedule an appointment",
            "schedule a meeting with", "book an appointment with",
            "research help", "help with my research",
            "research workshop", "research strategy",
            "scholarly commons",
        ],
        "phrases": [
            "research support", "consultation",
            "appointment with",
            "publish my", "publishing help",
            "open access publishing",
            "copyright help", "copyright question",
        ],
        "keywords": [],
        "negative": [
            "research database",
        ],
    },

    "data_services": {
        "strong": [
            "data services", "data analysis help", "data analysis support",
            "data visualization help", "data viz help",
            "gis help", "gis support",
            "statistical analysis help",
            "data management plan", "data management help",
            "research data management",
            "spss help", "stata help",
            "r programming help", "python help",
        ],
        "phrases": [
            "data services", "data viz", "data visualization",
            "research data",
        ],
        "keywords": ["gis"],
        "negative": [
            "database", "personal data",
        ],
    },

    "digital_collections": {
        "strong": [
            "digital collection", "digital collections",
            "digital exhibit", "digital exhibits",
            "online exhibit", "online exhibits",
            "digital archive", "digital archives",
            "digitized", "digitization",
            "digital scholarship",
        ],
        "phrases": [
            "digital library",
            "online collection",
        ],
        "keywords": [],
        "negative": [],
    },

    "special_collections": {
        "strong": [
            "special collections", "scua",
            "university archives", "miami university archives",
            "rare book", "rare books",
            "manuscript collection",
            "finding aid", "finding aids",
            "havighurst",
            "the archivist", "university archivist",
            "appointment with the archivist",
        ],
        "phrases": [
            "archivist",
            "manuscripts", "primary source",
            "primary sources",
            "miami history",
        ],
        "keywords": [],
        "negative": [],
    },

    "newspapers": {
        "strong": [
            "new york times", "nyt", "ny times",
            "wall street journal", "wsj",
            "cincinnati enquirer", "washington post",
            "financial times", "the economist",
            "newspaper subscription", "newspaper access",
            "newspaper subscriptions",
            "free new york times", "free nyt",
            "miami nyt", "academic pass nyt",
        ],
        "phrases": [
            "newspaper",
            "online newspaper",
        ],
        "keywords": [],
        "negative": [],
    },

    # ============================================================
    # Spaces
    # ============================================================

    "room_booking": {
        "strong": [
            "book a room", "book a study room", "book a group study",
            "reserve a room", "reserve a study room", "reserve a group",
            "room reservation", "study room reservation",
            "study room booking", "study rooms",
            "schedule a room", "scheduling a room",
            "group study room",
            "conference room reservation", "conference room booking",
            "rooms have a whiteboard",
            "rooms have whiteboards",
            "study rooms in king",
            "use study rooms",
        ],
        "phrases": [
            "book a study", "reserve a study",
        ],
        "keywords": [],
        "negative": [
            "course reserve", "class reserve", "on reserve",
            # Avoid grabbing every mention of "study"
            "studying for",
        ],
    },

    "space_info": {
        "strong": [
            "quiet floor", "silent study", "quiet study",
            "silent floor", "graduate reading room",
            "faculty reading room", "howe writing center",
            "where can i study",
            "is the cafe open", "cafe hours",
            "the king cafe", "library cafe",
            "lockers in the library", "lockers at king",
            "food in the library", "drinks in the library",
            "can i bring food",
            "the cafe in",
        ],
        "phrases": [
            "quiet area", "silent area",
            "group study area",
            "study spaces",
            "writing center programs",
        ],
        "keywords": ["lockers"],
        "negative": [
            "course reserve",
            "tablets", "laptops", "chromebook", "ipad",
            "borrow a", "checkout a",
        ],
    },

    "makerspace_3d": {
        "strong": [
            "makerspace", "maker space",
            "3d printer", "3d printers", "3d printing",
            "vinyl cutter", "vinyl cutting", "vinyl transfer",
            "sewing machine", "sewing machines",
            "laser cutter", "laser cutting",
            "button maker",
            "in the maker", "use the maker",
            "the makerspace", "the maker space",
            "makers space", "maker's space",
            "laminator",
        ],
        "phrases": [],
        "keywords": [],
        "negative": [
            # Random article complaints sometimes contain "the maker"
            # in different context.
            "the maker of",
            # When a user is asking about an ARTICLE / THESIS that
            # happens to be about 3D printing, that's a find_resource
            # question, not a makerspace question.
            "article", "this article", "find this", "the article",
            "thesis", "dissertation",
            "i want this", "i need this",
            "wtf",  # frustrated find-resource complaints
        ],
    },

    # ============================================================
    # Technology
    # ============================================================

    "printing_wifi": {
        "strong": [
            "how do i print", "how do i scan", "how do i copy",
            "how to print", "how to scan",
            "print from my laptop", "print from my phone",
            "print from my computer",
            "print in color", "color print", "color printing",
            "color copy", "color copies",
            "wifi password", "wi-fi password",
            "the wifi", "the wi-fi",
            "how to connect to wifi", "connect to wifi",
            "where can i scan", "where can i print",
            "where can i copy", "scanner location",
            "photocopy", "photocopier",
        ],
        "phrases": [
            "printer", "scanner", "scanners",
            "print job", "printing services",
            "muconnect", "eduroam",
            "color print", "printing in color",
        ],
        "keywords": ["printing", "wifi", "wi-fi", "scanning", "scanner"],
        "negative": [],
    },

    "tech_checkout": {
        "strong": [
            "borrow a laptop", "borrow a chromebook",
            "checkout a laptop", "check out a laptop",
            "loan a laptop", "rent a laptop",
            "chromebook checkout", "chromebook loan",
            "borrow a charger", "checkout a charger",
            "borrow a calculator", "borrow a camera",
            "borrow a tablet", "borrow an ipad",
            "ipad pro", "apple pencil",
            "borrow headphones", "borrow a microphone",
            "borrow equipment", "tech checkout",
            "equipment checkout",
            "camera tripod", "tripod for",
            "graphing calculator", "scientific calculator",
        ],
        "phrases": [
            "chromebook",
            "loan a charger",
            "rental laptop",
        ],
        "keywords": [],
        "negative": [],
    },

    "software_access": {
        "strong": [
            "software available", "what software",
            "software on the library computer",
            "software on the library computers",
            "software on library computers",
            "software checkout", "checkout software",
            "what programs are on", "what programs available",
            "matlab", "spss", "stata", "nvivo", "tableau",
            "is r installed", "is python installed",
            "install software",
        ],
        "phrases": [
            "software list",
        ],
        "keywords": [],
        "negative": [
            "adobe", "photoshop", "illustrator", "indesign",
            "premiere", "lightroom", "acrobat",
        ],
    },

    "adobe_access": {
        "strong": [
            "adobe", "photoshop", "illustrator", "indesign",
            "premiere pro", "after effects", "lightroom",
            "acrobat pro", "creative cloud", "adobe cc",
            "adobe creative cloud",
            "adobe license", "adobe software",
        ],
        "phrases": [
            "premiere",
            "acrobat",
        ],
        "keywords": [],
        "negative": [],
    },

    # ============================================================
    # Lookup
    # ============================================================

    "hours": {
        "strong": [
            "library hours", "what are the hours",
            "what are your hours",
            "what time does the library open", "what time does the library close",
            "what time does king open", "what time does king close",
            "what time does wertz open", "what time does wertz close",
            "is the library open today", "is the library open tomorrow",
            "is the library open right now", "is the library open now",
            "library open today", "library open tomorrow",
            "open today", "open tomorrow", "open tonight",
            "open this weekend", "open on saturday", "open on sunday",
            "library still open", "still open",
            "closing time", "opening time",
        ],
        "phrases": [
            "hours today", "hours tomorrow",
            "open until",
            "what time", "when does",
        ],
        "keywords": [],
        "negative": [
            "office hours", "office hours of",
        ],
    },

    "location_directions": {
        "strong": [
            "where is king library", "where is king",
            "where is wertz", "where is the art library",
            "where is rentschler", "where is the hamilton library",
            "where is gardner-harvey", "where is the middletown library",
            "where is the library",
            "address of the library", "library address",
            "address of king", "address of wertz",
            "parking at the library", "library parking",
            "directions to the library", "directions to king",
            "how to get to the library", "how to find the library",
            "where can i park",
            "what floor", "which floor",
            "map of the library",
        ],
        "phrases": [
            "library located", "located",
            "find the library",
        ],
        "keywords": [],
        "negative": [
            "place a hold", "find a book", "find an article",
            "find a librarian",
        ],
    },

    "staff_lookup": {
        "strong": [
            "dean of the library", "dean of libraries",
            "library dean",
            "head of circulation", "head of reference",
            "library director",
            "staff directory", "library staff",
            "library administrator",
            "manager of",
        ],
        "phrases": [
            "supervisor of",
        ],
        "keywords": [],
        "negative": [
            "subject librarian", "liaison",
            "librarian for",
        ],
    },

    "subject_librarian": {
        "strong": [
            "subject librarian", "liaison librarian", "liaison",
            "librarian for my subject", "librarian for my major",
            "librarian for my class", "librarian for my course",
            "librarian for biology", "librarian for chemistry",
            "librarian for psychology", "librarian for nursing",
            "librarian for history", "librarian for english",
            "librarian for music", "librarian for art",
            "librarian for business", "librarian for education",
            "librarian for engineering", "librarian for sociology",
            "librarian for physics", "librarian for math",
            "librarian for architecture", "librarian for journalism",
            "librarian for political science", "librarian for economics",
            "librarian for global studies", "librarian for kinesiology",
            "subject specialist", "research liaison",
            "history librarian", "biology librarian",
            "psychology librarian", "nursing librarian",
            "business librarian", "english librarian", "music librarian",
            "art librarian", "education librarian",
            "who is the librarian for",
        ],
        "phrases": [
            "subject area",
        ],
        "keywords": [],
        "negative": [
            "dean", "head of",
        ],
    },

    # ============================================================
    # Other
    # ============================================================

    "events_news": {
        "strong": [
            "upcoming events", "library events", "library event",
            "upcoming exhibits", "upcoming exhibit",
            "upcoming workshop", "upcoming workshops",
            "library workshop", "library workshops",
            "next workshop",
            "library news",
            "what's happening at", "anything happening at",
            "events at the library", "events at king",
            "talk at the library", "lecture at the library",
            "is anything going on", "anything going on",
        ],
        "phrases": [
            "art exhibit",
            "library lecture",
            # NB: NOT "exhibit" alone -- "exhibition" appears in
            # academic catalog titles ("single exhibition from 1982")
            # and would false-positive find_resource queries.
        ],
        "keywords": [],
        "negative": [
            "research workshop", "data workshop",
            "instruction workshop",
            # Find-resource queries about exhibition catalogs
            "find books", "help me find", "looking for", "research project",
        ],
    },

    "instruction_request": {
        "strong": [
            "library instruction", "library session for my class",
            "library session for my students",
            "library session for my course",
            "instruction session", "research instruction",
            "teach my class", "teach my students",
            "schedule a class visit", "schedule an instruction",
            "information literacy session",
            "request a librarian for my class",
            "want a librarian to come",
            "have a librarian visit",
        ],
        "phrases": [
            "librarian to teach",
            "research session for my",
        ],
        "keywords": [],
        "negative": [],
    },

    "service_howto": {
        "strong": [
            # Generic "how do I" questions that don't fit a more
            # specific bucket. Use sparingly -- prefer specific intents.
        ],
        "phrases": [],
        "keywords": [],
        "negative": [],
    },

    "cross_campus_comparison": {
        "strong": [
            "all campuses", "every campus", "every miami library",
            "at all three campuses", "at all three libraries",
            "at each campus", "for each campus",
            "compare libraries", "compare the libraries",
            "compare campuses",
        ],
        "phrases": [
            "between hamilton and middletown",
            "oxford and hamilton", "oxford and middletown",
            "hamilton and oxford", "middletown and oxford",
            "all libraries open", "all libraries have",
            # "available at all" is too aggressive on its own (matches
            # "available at all hours" -- a different shape).
            "available at all three", "available at each",
        ],
        "keywords": [],
        "negative": [
            # Common false positive: "checkout not available at all"
            # is a circulation issue, not a campus comparison.
            "not available at all",
            "available at all hours", "open at all",
        ],
    },

    "human_handoff": {
        "strong": [
            "talk to a person", "talk to a human", "talk to someone",
            "speak to a person", "speak to a human", "speak to someone",
            "speak to a librarian", "speak with a librarian",
            "real person", "not a bot", "are you a bot",
            "a human", "is anyone there", "can i speak",
            "is anyone real", "is this a bot", "are you a robot",
            "i need a person", "i need a human",
        ],
        "phrases": [
            "live chat", "live person",
        ],
        "keywords": [],
        "negative": [
            "subject librarian",
        ],
    },

    "out_of_scope": {
        "strong": [
            # Out of scope is detected as the FALLBACK -- not via
            # patterns. Heuristics here are dangerous (false-positive
            # rate would block real questions).
        ],
        "phrases": [],
        "keywords": [],
        "negative": [],
    },
}


# Patterns that signal an out-of-scope question (sports, weather,
# homework help, random typed-in nonsense). Conservative.
OUT_OF_SCOPE_PATTERNS = [
    r"\bweather\b",
    r"\bbengals\b", r"\bcincinnati reds\b",
    r"\bfootball score\b", r"\bbasketball score\b", r"\bbaseball score\b",
    r"\bsports\b.*\bscore\b",
    r"^test$", r"^testing$", r"^hello world$", r"^123\b",
    r"\bhomework help\b",
    r"\bwrite my essay\b", r"\bwrite my paper\b",
    r"\bsolve this\b.*\bequation\b",
    r"\btranslate this\b",
]


# Strong threshold + minimum margin for confident labeling.
STRONG_THRESHOLD = 4.0
MIN_MARGIN = 2.0
PER_INTENT_CAP = 80


# ----------------------------------------------------------------------------


_WORD_BOUNDARY_CACHE: dict[str, re.Pattern] = {}


def _word_boundary_match(needle: str, haystack: str) -> bool:
    """True iff `needle` appears in `haystack` on word boundaries.

    Why not raw substring: short patterns like "nyt" / "ill" / "wsj"
    appear inside common English words ("a-NYT-hing", "tr-ILL-y",
    "an-SWE-r" almost) and would silently false-positive otherwise.
    Same bug class as the scope resolver fix.

    Phrases with whitespace (e.g. "study room") still get word-bounded
    on each side -- the inner whitespace is the natural separator.

    Cached because we re-test the same patterns thousands of times.
    """
    pat = _WORD_BOUNDARY_CACHE.get(needle)
    if pat is None:
        pat = re.compile(r"\b" + re.escape(needle) + r"\b")
        _WORD_BOUNDARY_CACHE[needle] = pat
    return bool(pat.search(haystack))


def _score_intent(utterance_lower: str, patterns: dict[str, list[str]]) -> float:
    score = 0.0
    for s in patterns.get("strong", []):
        if _word_boundary_match(s, utterance_lower):
            score += 5.0
    for p in patterns.get("phrases", []):
        if _word_boundary_match(p, utterance_lower):
            score += 3.0
    for k in patterns.get("keywords", []):
        if _word_boundary_match(k, utterance_lower):
            score += 1.0
    for n in patterns.get("negative", []):
        if _word_boundary_match(n, utterance_lower):
            score -= 3.0
    return score


def _is_out_of_scope(utterance_lower: str) -> bool:
    for pat in OUT_OF_SCOPE_PATTERNS:
        if re.search(pat, utterance_lower, re.IGNORECASE):
            return True
    # Very-short single-word / two-word questions that aren't
    # library-related. The keyword allowlist is the explicit ESCAPE
    # set: any short message containing one of these is library-
    # adjacent enough that we DON'T want to slap out_of_scope on it.
    if len(utterance_lower.split()) <= 2 and not any(
        kw in utterance_lower
        for kw in [
            # Buildings / hours / spaces
            "hours", "open", "close", "wifi", "library", "room",
            # Borrow / circulation
            "book", "ill", "hold", "renew", "checkout", "checkout?",
            "borrow", "due", "fine",
            # Tech / software
            "adobe", "photoshop", "illustrator", "indesign",
            "premiere", "acrobat", "matlab", "spss", "stata",
            "print", "scan", "copy",
            # Spaces
            "makerspace", "3d", "vinyl", "sewing",
            # Research
            "database", "databases", "jstor", "ebsco", "proquest",
            "pubmed", "psycinfo", "scifinder", "ohiolink", "worldcat",
            "citation", "apa", "mla", "zotero", "endnote",
            "gis", "data",
            # Collections
            "archives", "archive", "scua", "havighurst", "manuscript",
            # Newspapers
            "nyt", "wsj", "newspaper",
            # Subjects (single-word subject queries are usually
            # subject_librarian or find_resource, not OOS)
            "biology", "chemistry", "physics", "history", "english",
            "psychology", "sociology", "anthropology", "philosophy",
            "engineering", "nursing", "music", "art", "education",
            "business", "economics", "math", "mathematics",
            "literature", "spanish", "french", "german", "japanese",
            "kinesiology", "geology", "geography", "linguistics",
            "religion", "theatre", "theater", "architecture",
            "journalism", "communication", "marketing", "finance",
            "accounting", "biochemistry", "neuroscience",
        ]
    ):
        return True
    return False


def label_utterance(utterance: str) -> Optional[str]:
    """Return best-confidence intent or None if ambiguous."""
    lower = utterance.lower()

    # Check OOS first -- short-circuit obvious non-library questions.
    if _is_out_of_scope(lower):
        return "out_of_scope"

    # Score every intent.
    scores: list[tuple[str, float]] = []
    for intent, patterns in PATTERNS.items():
        s = _score_intent(lower, patterns)
        if s > 0:
            scores.append((intent, s))

    if not scores:
        return None

    scores.sort(key=lambda kv: -kv[1])
    top_intent, top_score = scores[0]
    runner_score = scores[1][1] if len(scores) > 1 else 0.0
    margin = top_score - runner_score

    # Confident enough?
    if top_score >= STRONG_THRESHOLD and margin >= MIN_MARGIN:
        return top_intent

    # Weak signal but ABOVE threshold (5+ points): we still take it
    # because high score = clear matches.
    if top_score >= 5.0:
        return top_intent

    # Otherwise leave blank for human review.
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--input", type=Path,
        default=Path(
            "ai-core/src/router/exemplars/exemplars_for_labeling.csv"
        ),
    )
    parser.add_argument(
        "--per-intent-cap", type=int, default=PER_INTENT_CAP,
        help="Maximum labels per intent (default 80).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print stats but don't write the CSV.",
    )
    parser.add_argument(
        "--show-samples", type=int, default=5,
        help="Print N example labels per intent (default 5).",
    )
    args = parser.parse_args()

    if not args.input.exists():
        print(f"input not found: {args.input}", file=sys.stderr)
        return 2

    rows: list[dict] = []
    with open(args.input, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    intent_counts: Counter = Counter()
    samples: dict[str, list[str]] = defaultdict(list)
    relabeled = 0
    new_labels = 0
    confirmed_kept = 0
    overridden = 0

    # Pass 1: label every row, respect cap.
    for row in rows:
        utt = (row.get("utterance") or "").strip()
        if not utt:
            continue

        existing = (row.get("intent") or "").strip()
        if existing:
            # Already human-labeled; trust + skip
            intent_counts[existing] += 1
            if len(samples[existing]) < args.show_samples:
                samples[existing].append(utt)
            continue

        proposed = label_utterance(utt)
        if proposed is None:
            continue

        # Skip if cap reached
        if intent_counts[proposed] >= args.per_intent_cap:
            continue

        # Validate against INTENTS
        if proposed not in INTENTS:
            continue  # safety net

        existing_suggested = (row.get("suggested_intent") or "").strip()
        if existing_suggested == proposed:
            confirmed_kept += 1
        elif existing_suggested:
            overridden += 1
        else:
            new_labels += 1

        row["intent"] = proposed
        relabeled += 1
        intent_counts[proposed] += 1
        if len(samples[proposed]) < args.show_samples:
            samples[proposed].append(utt)

    # Print stats.
    print(f"Read {len(rows)} rows from {args.input}")
    print(f"Labeled this pass: {relabeled}")
    print(f"  - confirming pre-labeled (suggested_intent matched): {confirmed_kept}")
    print(f"  - overriding pre-labeled (heuristic was wrong): {overridden}")
    print(f"  - filling blanks: {new_labels}")
    print()
    print(f"Per-intent label counts (cap={args.per_intent_cap}):")
    print(f"{'intent':<28s} {'count':>6s}")
    print("-" * 38)
    for intent in INTENTS:
        n = intent_counts.get(intent, 0)
        print(f"  {intent:<28s} {n:>4d}")
    print()
    print(f"Total labels: {sum(intent_counts.values())}")
    print(f"Intents with labels: {len([i for i in INTENTS if intent_counts.get(i, 0) > 0])}/{len(INTENTS)}")
    print(f"Intents with >= 20: {len([i for i in INTENTS if intent_counts.get(i, 0) >= 20])}")
    print(f"Intents with >= 30: {len([i for i in INTENTS if intent_counts.get(i, 0) >= 30])}")
    print()

    if args.show_samples > 0:
        print(f"Sample labels per intent (first {args.show_samples}):")
        print()
        for intent in INTENTS:
            sample_list = samples.get(intent, [])
            if not sample_list:
                continue
            print(f"  [{intent}] ({intent_counts[intent]} total)")
            for utt in sample_list:
                # Trim to 100 chars for readability
                print(f"    - {utt[:100]}")
            print()

    if args.dry_run:
        print("DRY RUN -- not writing the CSV.")
        return 0

    # Write back.
    with open(args.input, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["utterance", "suggested_intent", "intent", "source"],
        )
        w.writeheader()
        for row in rows:
            w.writerow({
                "utterance": row.get("utterance", ""),
                "suggested_intent": row.get("suggested_intent", ""),
                "intent": row.get("intent", ""),
                "source": row.get("source", ""),
            })
    print(f"Wrote labeled CSV: {args.input}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
