"""
Stable cached prefix for the LLM-as-judge -- v2 rubric.

Why a v2 (2026-07-16): the post-hygiene triage found ~60 of 76 flagged
verdicts were judge harshness, concentrated in three patterns v1 didn't
address:

  1. The judge never saw the gold `notes` field, which carries the
     operator's review verdicts ("pointer answer marked BOT-OK",
     "closed status is what the operator asked for").
  2. Rule E1 counted the bot's interactive-capability offers ("or I
     can book one for you here in chat") as uncited claims and dragged
     verdicts to "partial".
  3. Pointer-style golds ("point to X", "give the booking link") were
     scored "partial" for not including page content the gold never
     required -- or for extras the gold explicitly marked as optional.

v2 = v1 rubric with a rewritten E1 plus rules 7/8/9 and three
exemplars mirroring the operator-triaged noise cases. The v1 module
stays registered for comparison runs.
"""

from src.prompts import register_prefix
from src.prompts.judge_v1 import JUDGE_V1_PREFIX


_E1_V1 = """\
E1. Partial citations. If the bot makes 5 claims and cites 3, the 2 \
uncited claims drag the verdict to "partial" even if the cited 3 are \
correct. Citation discipline is non-negotiable.
"""

_E1_V2 = """\
E1. Partial citations. If the bot makes 5 FACTUAL claims and cites 3, \
the 2 uncited claims drag the verdict to "partial" even if the cited 3 \
are correct. Citation discipline is non-negotiable. BUT: only factual \
assertions about the world count as claims. The bot's descriptions of \
its OWN in-chat capabilities and invitations ("or I can book one for \
you right here in chat -- just tell me the date...", "tell me your \
subject and I'll look up the librarian", "you can ask me to check") \
are NOT factual claims and need no citation; never downgrade for them.
"""

_V2_ADDITIONS = """\

# v2 rules (2026-07-16 -- operator-triage-driven)

7. OPERATOR NOTES are authoritative context. The input may end with an \
OPERATOR NOTES section: the case's review history written by the human \
operator (which answer style was accepted, which old expectation was \
overruled, why the gold reads the way it does). Use it to interpret \
EXPECTED. When the bot's answer matches behavior the notes describe as \
operator-approved ("marked BOT-OK", "operator confirmed", "the pointer \
IS the answer"), score "correct" even if a literal reading of EXPECTED \
alone would suggest "partial". Notes never make a factually-wrong \
answer right; they resolve style/format/strictness ambiguity only.

8. POINTER golds are satisfied by pointers. When EXPECTED asks the bot \
to point/guide/direct the user to a page ("point to X", "give the \
booking link", "cite the X page", "let them check the page"), a bot \
answer that provides that link with brief correct framing is \
"correct" -- NOT "partial" for omitting page content the gold never \
required. The pointer IS the requested substance (operator rule; same \
family as rule 5b).

9. Optional extras never downgrade. When EXPECTED marks something as \
optional ("a bonus, NOT required", "also acceptable", "ideally"), its \
absence must not reduce the verdict. Score only the required core.

# v2 exemplars (operator-triaged noise patterns)

Q: "Is the MakerSpace open right now?"
Expected: "Live MakerSpace LibCal status -- a closed status is a \
CORRECT answer when that is what LibCal reports."
Bot:      "No. The Makerspace is closed today, Thursday (2026-07-16) [1]."
Output:
{"verdict": "correct", "reason": "Truthful cited live status; closed \
is the requested information (rules 6 and 9).", "citation_validity": \
"all_valid"}

Q: "Can I book a study room at King today?"
Expected: "Confirm King rooms are bookable and give the reservation \
link. Live availability is a bonus, NOT required."
Bot:      "Yes -- you can reserve a study room at King through the \
LibCal reservation page [1]. Or I can book one for you right here in \
chat -- just tell me the date, start and end time, and your Miami email."
Output:
{"verdict": "correct", "reason": "Booking link satisfies the pointer \
gold (rule 8); the in-chat offer is a capability statement, not an \
uncited claim (E1); live availability was optional (rule 9).", \
"citation_validity": "all_valid"}

Q: "How do I book a study room?"
Expected: "Default King: with no campus named in the message, present \
King's reservation tool -- operator rule; defaulting to King is \
CORRECT, not an error."
Bot:      "Yes -- you can reserve a study room at King Library through \
the LibCal room reservation system [1]."
Output:
{"verdict": "correct", "reason": "EXPECTED itself designates the King \
default as correct; do not penalize the ambiguity resolution the gold \
endorses (rule 7).", "citation_validity": "all_valid"}
"""


def _build_v2() -> str:
    assert _E1_V1 in JUDGE_V1_PREFIX, (
        "judge_v1's E1 rule text changed -- update _E1_V1 in judge_v2.py"
    )
    return JUDGE_V1_PREFIX.replace(_E1_V1, _E1_V2) + _V2_ADDITIONS


JUDGE_V2_PREFIX = _build_v2()

register_prefix("judge_v2", JUDGE_V2_PREFIX)
