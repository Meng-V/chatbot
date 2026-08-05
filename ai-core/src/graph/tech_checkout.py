"""Answer "does the library lend <thing>?" from the tech-checkout page itself.

WHY THIS EXISTS
The tech-checkout page is a single 1,460-character chunk whose payload is a
two-level bullet list: seven categories, twenty-odd items. Retrieval already
puts that chunk first (`_ensure_tech_checkout_evidence`), so the synthesizer
has the text -- and still refuses about half the time, because "yes, we lend
graphing calculators" is not a sentence anywhere on the page. It is two list
items, nested. `Calculators` / `  - Graphing`.

Measured on the 2026-08-05 gold run: tech_charger and tech2_calculator_borrow
both refused, while the answer sat in the evidence both times.

WHAT IT DOES NOT DO
It does not hold a hardcoded equipment list. The list is parsed out of the
chunk text at answer time, so:
  * it cannot name equipment the page does not list, and
  * when the page changes, the answer changes with it -- no code edit, no
    stale inventory to forget about.

If the page's markup ever stops producing a parseable list, `parse_equipment`
returns {} and every entry point returns None, which puts the turn back on the
agent exactly as it is today.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

TECH_CHECKOUT_URL = "https://www.lib.miamioh.edu/use/technology/tech-checkout/"
KING_PHONE = "(513) 529-4141"

_AVAILABLE_MARKER = "Available Equipment"


def parse_equipment(text: str) -> Dict[str, List[str]]:
    """Parse the page's own two-level list into {category: [sub-items]}.

    Only the part after "Available Equipment" is read. The bullets before it
    are loan periods and availability advice ("Chromebook laptops may be
    checked out for 30 days"), which are prose, not inventory -- treating them
    as equipment is how you end up claiming the library lends
    "Call or stop by to check availability".
    """
    if not text:
        return {}
    idx = text.find(_AVAILABLE_MARKER)
    if idx < 0:
        return {}
    body = text[idx + len(_AVAILABLE_MARKER):]

    cats: Dict[str, List[str]] = {}
    current: Optional[str] = None
    for raw in body.splitlines():
        if not raw.strip().startswith("-"):
            continue
        indent = len(raw) - len(raw.lstrip())
        label = raw.strip().lstrip("-").strip()
        if not label:
            continue
        if indent <= 1:
            current = label
            cats.setdefault(current, [])
        elif current is not None:
            cats[current].append(label)
    return cats


_LOAN_MARKER = "Loan Periods and Late Fees"


def parse_loan_periods(text: str) -> List[str]:
    """The "Loan Periods and Late Fees" bullets, verbatim.

    These sit BEFORE "Available Equipment" and are deliberately excluded from
    `parse_equipment` -- they are prose, not inventory. But they answer the
    obvious follow-up. Gold `tech_borrow_laptop` wants "Chromebooks, 30 days",
    and the first version of this module dropped the 30 days and turned a
    passing case into a partial: the page says it, the answer did not.

    Returned verbatim so the sentence is quotable against the cited page.
    """
    if not text:
        return []
    start = text.find(_LOAN_MARKER)
    if start < 0:
        return []
    end = text.find(_AVAILABLE_MARKER, start)
    body = text[start + len(_LOAN_MARKER):end if end > 0 else len(text)]
    out = []
    for raw in body.splitlines():
        s = raw.strip()
        if s.startswith("-"):
            s = s.lstrip("-").strip()
            if s:
                out.append(s)
    return out


def _loan_note(item: str, parent: Optional[str], text: str) -> str:
    """A loan-period sentence for this item, or "".

    Matched on the words the page itself uses, so an item with no stated
    period simply gets nothing rather than inheriting someone else's.
    """
    words = {w.lower().strip(".,()") for w in (item + " " + (parent or "")).split()
             if len(w) > 3}
    for line in parse_loan_periods(text):
        low = line.lower()
        if any(w.rstrip("s") in low for w in words):
            return _clean(line)
    return ""


def _flat(cats: Dict[str, List[str]]) -> List[str]:
    out: List[str] = []
    for cat, items in cats.items():
        out.append(cat)
        out.extend(items)
    return out


# What students type -> what the page calls it. Left side is matched against
# the QUESTION, right side against the parsed list, so a rename on the page
# breaks the match into a None (agent handles it) rather than a wrong answer.
_SYNONYMS: Tuple[Tuple[str, str], ...] = (
    (r"charg(er|ers|ing)\s*(cable|cord|brick|block)?|power\s*(cord|adapter|adaptor|supply)", "charger"),
    (r"calculator|calculators", "calculator"),
    (r"laptop|laptops|chromebook|notebook\s+computer", "laptop"),
    (r"ipad|i-pad|tablet|tablets", "tablet"),
    (r"apple\s*pencil|stylus", "pencil"),
    (r"camera|cameras|dslr|camcorder", "camera"),
    (r"tripod|tripods", "tripod"),
    (r"projector|projectors", "projector"),
    (r"dvd\s*player|dvd\s*drive|blu-?ray", "dvd"),
    (r"microphone|microphones|mic\b|mics\b", "microphone"),
    (r"headphone|headphones|earphone|earbuds|headset", "headphone"),
    (r"audio\s*recorder|voice\s*recorder|digital\s*recorder", "recorder"),
    (r"speaker|speakers", "speaker"),
    # Generic only. `hdmi`, `vga` and `usb-c` were here and produced a WRONG
    # answer on gold tech2_hdmi_cable: the page lists "Adaptors" with no
    # connector types, and answering "Yes -- includes Adaptors" to "can I
    # borrow an HDMI cable?" asserts something the page does not support.
    # A specific item must not be satisfied by a generic list entry; those
    # questions belong to the agent, which can hedge and say "call to ask".
    (r"adapter|adaptor|adapters|adaptors|dongle", "adaptor"),
    (r"mouse|mice", "mouse"),
    (r"ethernet|network\s*cable|lan\s*cable", "network cable"),
    (r"card\s*reader|sd\s*card\s*reader", "card reader"),
    (r"external\s*(disc|disk)\s*drive|cd\s*drive|dvd\s*drive|optical\s*drive", "disc drive"),
    (r"translator|translators", "translator"),
    (r"cable|cables", "cable"),
)

# The question has to be ABOUT borrowing, or this fires on "where do I plug in
# my charger" and similar.
_BORROW_RE = re.compile(
    r"\b(lend|lends|lending|loan|loans|borrow|borrows|borrowing|"
    r"check\s*out|checkout|checking\s+out|rent|rents|"
    r"have|has|got|offer|offers|available|carry|carries|provide|provides)\b",
    re.IGNORECASE,
)

# Asked about a fee, a policy, a duration, or a specific building -> this
# handler cannot answer it from an inventory list, so it yields. Learned the
# hard way from the printing pointer, which overfired and cost four good
# answers before it was narrowed twice.
_NOT_INVENTORY_RE = re.compile(
    r"\b(how\s+long|how\s+many|loan\s*period|due|overdue|late\s*fee|fine|fines|"
    r"cost|costs|price|fee|fees|charge\s+me|deposit|replace|replacement|"
    r"damage|lost|reserve|reservation|renew|renewal|policy|policies)\b",
    re.IGNORECASE,
)


def _clean(entry: str) -> str:
    """Repair the page's mis-encoded punctuation before it reaches a patron.

    The chunk contains "iPad Pros and Apple Pencils â available at Art &
    Architecture Library" -- a UTF-8 em dash read as Latin-1. Echoing that
    verbatim looks like the bot is broken, so it is normalised here rather
    than left for someone to notice in production.
    """
    out = (entry or "")
    for bad, good in (("â", "-"), ("â", "-"),
                      ("â", "'"), ("â", '"'),
                      ("â", '"'), ("â", "-")):
        out = out.replace(bad, good)
    return re.sub(r"\s+", " ", out).strip().rstrip(".")


def looks_like_equipment_question(message: str) -> bool:
    """Cheap pre-filter so the caller can skip a Weaviate read.

    Roughly 95% of turns are not equipment questions, and the short-circuit
    sits ahead of the agent on every one of them. This is the same pair of
    regexes `tech_checkout_answer` applies, exposed so the orchestrator can
    decide not to pay for the fetch. It is deliberately permissive: a false
    positive here only costs one indexed read, because the real decision is
    still made against the page's own list.
    """
    m = message or ""
    return bool(_BORROW_RE.search(m)) and not _NOT_INVENTORY_RE.search(m)


# Connector and interface names. The page lists "Adaptors", "Network cables"
# and "Cables and peripherals" -- categories, with no interface types named
# anywhere. So when a student asks for one of these BY NAME, the page cannot
# support a yes, and a generic entry must not stand in for it.
#
# This is the rule, not a synonym patch. Removing `hdmi` from the adaptor
# synonym was not enough: "HDMI cable" then matched the generic `cable`
# synonym and answered "Yes -- Network cables", which is the same wrong answer
# by another route (gold tech2_hdmi_cable, partial -> WRONG on 2026-08-05).
#
# Checked against the page text, so if the page ever does start naming
# interfaces, these questions become answerable with no code change.
_INTERFACE_RE = re.compile(
    r"\b(hdmi|vga|display\s*port|dvi|thunderbolt|lightning|usb-?c|"
    r"cat-?[56]e?|aux\s*cord|3\.5\s*mm|firewire|micro-?usb)\b",
    re.IGNORECASE,
)


def _asks_for_something_the_page_never_names(message: str, page: str) -> bool:
    m = _INTERFACE_RE.search(message or "")
    if not m:
        return False
    return m.group(0).lower().replace(" ", "") not in (page or "").lower().replace(" ", "")


def _match_item(message: str, cats: Dict[str, List[str]]) -> Optional[Tuple[str, str]]:
    """Return (what the student asked about, the page's own wording) or None.

    Sub-items win over categories. "Does the library lend graphing
    calculators?" should land on `Graphing` under `Calculators`, not on the
    bare category -- gold asks whether GRAPHING calculators specifically are
    available, and answering with the category leaves the student to infer it.
    """
    subs = [(c, i) for c, items in cats.items() for i in items]

    # Pass 1: the question names a sub-item outright ("graphing", "chromebook").
    for cat, item in subs:
        head = re.split(r"[(–—-]", _clean(item))[0].strip()
        if len(head) < 4:
            continue
        if re.search(r"\b" + re.escape(head.rstrip("s")) + r"s?\b", message, re.IGNORECASE):
            return head, item

    # Pass 2: synonym -> the page's wording, sub-items before categories.
    for pattern, canon in _SYNONYMS:
        if not re.search(pattern, message, re.IGNORECASE):
            continue
        needle = canon.rstrip("s")
        for _cat, item in subs:
            if needle in item.lower():
                return canon, item
        for cat in cats:
            if needle in cat.lower():
                return canon, cat
    return None


def tech_checkout_answer(
    message: str, chunk_text: str
) -> "Optional[Tuple[str, List[dict]]]":
    """Answer an equipment question from the page's list, or return None.

    Returns None -- letting the normal agent path run -- whenever the question
    is not an inventory question, the list will not parse, or the asked-about
    item cannot be tied to something the page actually says.
    """
    m = message or ""
    if not _BORROW_RE.search(m) or _NOT_INVENTORY_RE.search(m):
        return None
    if _asks_for_something_the_page_never_names(m, chunk_text):
        return None
    cats = parse_equipment(chunk_text)
    if not cats:
        return None

    hit = _match_item(m, cats)
    if hit is None:
        return None
    _asked, entry = hit

    # Name the parent category when the hit is a sub-item, so "Graphing"
    # reads as "Graphing calculator" and not as a bare word. Rule 12b: a word
    # is not an answer.
    parent = None
    for cat, items in cats.items():
        if entry in items:
            parent = cat
            break

    shown = _clean(entry)
    if parent is None:
        what = f"**{shown}**"
    else:
        pclean = _clean(parent)
        # A one-word sub-item under a one-word plural category is a modifier,
        # not a thing: the page's "Graphing" under "Calculators" means graphing
        # calculators. Compose it so the answer is a noun phrase a student
        # recognises. Skip it when the category is itself compound
        # ("Laptops & Tablets"), where "Chromebook Laptops & Tablets" would be
        # worse than the bare item.
        if " " not in shown and " " not in pclean and pclean.lower().endswith("s"):
            what = f"**{shown} {pclean.lower()}**"
        else:
            what = f"**{shown}** ({pclean})"
    siblings = [_clean(i) for i in (cats.get(parent or entry) or []) if i != entry]
    also = ""
    if siblings:
        also = " The same section also lists " + ", ".join(siblings[:4]) + "."

    loan = _loan_note(entry, parent, chunk_text)
    loan_line = f" {loan} [1]." if loan else ""

    return (
        f"Yes — the libraries' equipment checkout list includes {what} [1].{also}"
        f"{loan_line}\n\n"
        f"Bring your university ID to a library checkout desk. Availability "
        f"changes as items go out or break, so it is worth calling "
        f"{KING_PHONE} first to confirm the item is on the shelf [1].",
        [{"n": 1, "url": TECH_CHECKOUT_URL,
          "snippet": "Miami University Libraries — Equipment to Checkout and Go"}],
    )
