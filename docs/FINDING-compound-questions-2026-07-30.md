# Two questions in one turn: measured, 2026-07-30

There is no multi-question handling in the code and none in the prompts.
Whether the second half of a compound question gets answered is emergent: the
classifier picks ONE intent, and the second half survives only if the evidence
retrieved for the first happens to cover it.

29 compound questions, ten student voices, each with two independently-graded
halves. Marker regexes per half, so "answered" is not a judgement call.

| Pairing | Both halves | First half | Second half |
|---|---|---|---|
| Same intent (King hours + Wertz hours) | **3/6** | 6/6 | 3/6 |
| Adjacent (librarian + subject guide) | **4/6** | 6/6 | 4/6 |
| Different (3D printing + cost) | **3/10** | 6/10 | 5/10 |
| Three questions in one turn | **0/2** | 0/2 | 0/2 |
| One half genuinely unanswerable | **0/3** | 3/3 | 0/3 |
| Polite/formal compound | **2/2** | 2/2 | 2/2 |

**Overall: both halves answered 12/29 (41%). The second question is
silently dropped 15 times in 29 (51%).**

## What the numbers overturn

The obvious hypothesis -- same intent on both halves means both get answered --
is wrong. Same-intent pairs scored 3 of 6. "hoo is the biology libarian and hoo
is the histry one" answered Biology and ignored History. Nothing is arbitrating
coverage; there is no step that asks whether the question was finished.

## The three findings that matter

**Three questions in one turn loses everything, not just the tail.** 0 of 2, and
the FIRST half went too: "WIFI PASSWORD PRINTING COST AND QUIET FLOOR" answered
none of the three. Past two questions it does not degrade, it collapses.

**When a half is unanswerable it never says so.** 0 of 3. Asked "what time does
King close, and how many people are in there right now?" it gave the closing
time and passed over the occupancy question in silence. The patron has no way
to know half their question was dropped -- which makes this the most damaging
shape, worse than a wrong answer a reader can spot.

**Politeness is no longer a penalty.** 2 of 2, after the register fixes earlier
the same day. Before those, the formal voice was the second-worst scorer.

## Recommendation

Announce, don't decompose. The harm measured here is silence, not error, so the
cheap fix addresses the harm directly: detect the extra question, answer the
first, then say plainly what else was asked and whether it can be answered.
That converts a silent 52% loss into a visible one.

True decomposition -- routing each half separately and merging -- doubles
latency and, on the evidence of triple-question collapse, would compound an
intent guess that is not yet stable. Prompt instructions alone are not enough:
the agent prompt already says "NEVER refuse a booking request" and that was
violated repeatedly today.

Raw data: /tmp/compound.jsonl (per-question answers and per-half verdicts).
