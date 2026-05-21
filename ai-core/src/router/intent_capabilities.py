"""
Per-intent capability registry: tells the orchestrator whether to
run the full agent loop or short-circuit to a templated response.

Going from 14 to 31 intents broadened ROUTING coverage. It did NOT
broaden ANSWERING coverage. Some intents are deliberately not
answerable by the bot:

  - `account`        privacy (only the user can see their checkouts/fines)
  - `events_news`    excluded by ETL design (stale event/news content
                     is the prime suspect for "fake service" hallucinations)
  - `find_resource`  catalog search -- specialized; route to Primo
  - `databases`      database lookup -- users routinely misspell
                     names ("Web of Science" vs "Web of Knowledge");
                     authoritative source is the A-Z page

For these, running the agent + synth costs budget for an answer that
SHOULD be a deterministic templated response. The registry lets the
orchestrator skip the agent and return the right shape directly.

Three tiers:

  READY            run the agent normally; grounding contract handles
                   refusal naturally (no_results, low_confidence, etc.)
  POINT_TO_URL     skip agent + synth; return a templated message that
                   describes the right tool/page and links to it
  REFUSE           skip agent + synth; return a refusal explaining why
                   the bot can't answer + the right next step

Default: READY. Every intent resolves to a capability via
`get_intent_capability` -- no None returns, no missing-key crashes.

See plan: Citation and refusal contract; Operations Op 2.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class CapabilityTier(str, Enum):
    """How the orchestrator handles each intent.

    String-valued for log-friendly serialization.
    """

    READY = "ready"
    """Run the full agent loop. Most intents are this."""

    POINT_TO_URL = "point_to_url"
    """Skip agent. Return a templated 'here's how + here's the URL'
    message. Renders as an answer (not a refusal) in the UI -- the
    user got a useful response, just not from the LLM."""

    REFUSE = "refuse"
    """Skip agent. Return a templated refusal explaining why the bot
    can't help + pointing to the right next step."""


@dataclass(frozen=True)
class IntentCapability:
    """One row in the registry."""

    intent: str
    tier: CapabilityTier
    canonical_url: Optional[str] = None
    """The single URL that's the authoritative answer for this intent
    (or None for READY intents that don't have one canonical URL)."""

    short_message: str = ""
    """Templated body. Rendered verbatim to the user. Should NOT
    contain placeholders -- this isn't the format() pipeline of
    refusal_templates."""

    refusal_trigger: str = ""
    """For REFUSE tier: the refusal_trigger value logged with the
    response (matches a key in synthesis/refusal_templates). Empty
    for non-REFUSE."""


# --- POINT_TO_URL intents ------------------------------------------------
#
# The bot describes the service in one sentence and links to where the
# REAL answer lives. Saves agent + synthesizer tokens; the answer is
# more accurate than what the LLM would compose.

_POINT_TO_URL: dict[str, IntentCapability] = {
    "databases": IntentCapability(
        intent="databases",
        tier=CapabilityTier.POINT_TO_URL,
        canonical_url="https://libguides.lib.miamioh.edu/az/databases",
        short_message=(
            "To find articles or browse research databases, use the "
            "library's Databases A-Z list. It's the authoritative "
            "index of every database the library subscribes to -- "
            "organized alphabetically and by subject -- and links "
            "directly into each database with proper authentication.\n\n"
            "Why send you there instead of looking up a specific "
            "database name? Database names overlap and shift "
            "(\"Web of Science\" vs \"Web of Knowledge\", \"PsycINFO\" "
            "vs \"Psychology and Behavioral Sciences Collection\"); "
            "the A-Z page disambiguates them with current names + "
            "subject tags.\n\n"
            "Databases A-Z: https://libguides.lib.miamioh.edu/az/databases"
        ),
    ),
    "find_resource": IntentCapability(
        intent="find_resource",
        tier=CapabilityTier.POINT_TO_URL,
        canonical_url="https://ohiolink-mu.primo.exlibrisgroup.com/discovery/search?vid=01OHIOLINK_MU:MU",
        short_message=(
            "To find a specific book, article, journal, or DVD at "
            "Miami University Libraries, search Primo -- the library "
            "catalog. It searches across our physical collection, "
            "ebooks, journal articles, and OhioLINK partner libraries "
            "in one place.\n\n"
            "Primo: https://ohiolink-mu.primo.exlibrisgroup.com/discovery/search?vid=01OHIOLINK_MU:MU\n\n"
            "If Primo says \"no results\" and you think the library "
            "should have it, you can request it through Interlibrary "
            "Loan: https://www.lib.miamioh.edu/use/borrow/ill/"
        ),
    ),
    "library_employment": IntentCapability(
        intent="library_employment",
        tier=CapabilityTier.POINT_TO_URL,
        canonical_url="https://www.lib.miamioh.edu/about/organization/employment/",
        short_message=(
            "Miami University Libraries posts job openings on the "
            "library employment page. Student worker positions, staff "
            "positions, and faculty librarian positions all link out "
            "from there to the official Miami Workday job-posting "
            "system.\n\n"
            "Employment: https://www.lib.miamioh.edu/about/organization/employment/\n\n"
            "Why route here? Job-posting content changes constantly "
            "and lives on Workday, not in our indexed pages. The "
            "official page is always current."
        ),
    ),
}


# --- REFUSE intents ------------------------------------------------------
#
# Bot can't answer for principled reasons. Templated refusal explains
# why and points to the right next step.

_REFUSE: dict[str, IntentCapability] = {
    "account": IntentCapability(
        intent="account",
        tier=CapabilityTier.REFUSE,
        canonical_url="https://ohiolink-mu.primo.exlibrisgroup.com/discovery/account?vid=01OHIOLINK_MU:MU&section=overview&lang=en",
        short_message=(
            "I can't access your library account -- only you can. "
            "To see your current checkouts, holds, due dates, or "
            "fines, sign in to MyAccount with your Miami credentials.\n\n"
            "MyAccount: https://ohiolink-mu.primo.exlibrisgroup.com/discovery/account?vid=01OHIOLINK_MU:MU&section=overview&lang=en\n\n"
            "If you need help with something MyAccount doesn't show "
            "(e.g., a fine you think is wrong), please contact "
            "circulation at (513) 529-4141 or chat with a librarian "
            "via Ask Us."
        ),
        refusal_trigger="account_privacy",
    ),
    "events_news": IntentCapability(
        intent="events_news",
        tier=CapabilityTier.REFUSE,
        canonical_url="https://www.lib.miamioh.edu/about/news-events/news/",
        short_message=(
            "I don't have information about library events, news, or "
            "exhibits. The bot is intentionally limited to evergreen "
            "service and policy content -- old event listings are a "
            "common source of misleading answers, so they're excluded.\n\n"
            "For current events, exhibits, and library news, please "
            "visit the News & Events page directly: "
            "https://www.lib.miamioh.edu/about/news-events/news/"
        ),
        refusal_trigger="news_excluded",
    ),
    "website_feedback": IntentCapability(
        intent="website_feedback",
        tier=CapabilityTier.REFUSE,
        canonical_url="https://www.lib.miamioh.edu/research/research-support/ask/",
        short_message=(
            "I can't fix the library website, broken links, or chatbot "
            "behavior on my own -- those reports go to the library web "
            "team. Please describe the problem through Ask Us and a "
            "real person will follow up + log the issue.\n\n"
            "Ask Us: https://www.lib.miamioh.edu/research/research-support/ask/\n\n"
            "If it's a broken database link or off-campus access "
            "problem specifically (most common report), the proxy / "
            "EZproxy team handles those -- mention the database name "
            "and the URL you tried."
        ),
        refusal_trigger="website_feedback_handoff",
    ),
}


# --- Public lookup -------------------------------------------------------


def get_intent_capability(intent: str) -> IntentCapability:
    """Look up an intent's capability tier.

    Returns READY for any intent not explicitly registered as
    POINT_TO_URL or REFUSE. This means: the default for new intents
    (or typo'd intents) is to run the agent and let the grounding
    contract handle refusal naturally. Better to err on the side of
    letting the agent try than silently refuse.
    """
    if intent in _POINT_TO_URL:
        return _POINT_TO_URL[intent]
    if intent in _REFUSE:
        return _REFUSE[intent]
    return IntentCapability(intent=intent, tier=CapabilityTier.READY)


def all_capabilities() -> dict[str, IntentCapability]:
    """All explicitly-registered capabilities. READY intents are NOT
    included -- they have no special configuration. Used by tests
    and the admin dashboard's intent-coverage view.
    """
    out: dict[str, IntentCapability] = {}
    out.update(_POINT_TO_URL)
    out.update(_REFUSE)
    return out


__all__ = [
    "CapabilityTier",
    "IntentCapability",
    "all_capabilities",
    "get_intent_capability",
]
