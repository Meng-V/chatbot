# How to run the colleague Round-1 re-test

This walks you through re-running the 37 questions from your colleague's
Nov 20, 2025 evaluation (the test that blocked v1 deployment) against the
current v2 chatbot, then generating a librarian-friendly report.

**Time:** ~30 minutes + ~$0.50 of OpenAI usage.
**Prerequisites:** Tunnels up, prod DB accessible, OPENAI_API_KEY in `.env`.

---

## Step 1 — Swap the gold file (1 min)

The eval runner reads `src/eval/golden_set.jsonl` by default. Swap it to
point at the colleague set:

```bash
cd /Users/qum/Documents/GitHub/chatbot/.claude/worktrees/nice-mcnulty-42183e/ai-core

# Back up the current 234-case set
cp src/eval/golden_set.jsonl src/eval/golden_set.jsonl.bak

# Swap in the colleague set (37 cases)
cp src/eval/golden_set_colleague_round1.jsonl src/eval/golden_set.jsonl

# Verify the swap
python3 -c "import json; print(sum(1 for l in open('src/eval/golden_set.jsonl') if l.strip() and not l.strip().startswith('//')))"
# Should print: 37
```

## Step 2 — Run the eval (~25 min, ~$0.50)

```bash
python -m src.eval.run_eval --with-real-llm --with-judge --results-out beta_colleague_round1.jsonl
```

What this does:
- For each of the 37 questions, sends it through the v2 chatbot end-to-end
  (kNN intent classifier → orchestrator → agent loop with real tools →
  synthesizer → post-processor)
- Captures the bot's answer, citations, refusal trigger (if any), latency, tokens
- Runs a 3-shot LLM judge per turn to verdict (correct / partial / wrong / refused_correctly / refused_incorrectly)
- Streams per-case rows to `beta_colleague_round1.jsonl` as it goes

You'll see progress on stdout. ~25 min for 37 cases. The full summary
prints at the end.

## Step 3 — Generate the librarian report (5 sec)

```bash
python scripts/generate_librarian_report.py \
  --results beta_colleague_round1.jsonl \
  --gold src/eval/golden_set_colleague_round1.jsonl \
  --output docs/eval/colleague_round1/REPORT.md
```

The output is markdown. It will show:
- **Headline:** "N of 37 answered well (X%)" with a 🟢/🟡/🔴 indicator
- **What got better since last year:** specific v1 failures (hallucinated articles, fake bookings) that v2 now handles correctly
- **What still needs attention:** remaining problems, with the bot's actual answer shown
- **Question-by-question breakdown:** every question grouped by topic, with the bot's answer, the verdict, and what v1 did for comparison
- **Bottom line:** plain-English summary for the librarian team

## Step 4 — Restore the original gold file (1 min)

```bash
mv src/eval/golden_set.jsonl.bak src/eval/golden_set.jsonl

# Verify back to 234
python3 -c "import json; print(sum(1 for l in open('src/eval/golden_set.jsonl') if l.strip() and not l.strip().startswith('//')))"
# Should print: 234
```

## Step 5 — Share with the librarian team

The markdown report is readable as-is in any text editor, but for sharing
with non-technical colleagues, convert to Word:

```bash
# Option A: pandoc (if installed)
pandoc docs/eval/colleague_round1/REPORT.md -o docs/eval/colleague_round1/REPORT.docx

# Option B: open in any markdown editor and "Save As Word"
# (e.g., Typora, Obsidian, VS Code with markdown plugin)

# Option C: paste into Google Docs — markdown renders cleanly there
```

---

## What to expect

The report is structured so a librarian can:

1. **Read the headline** and immediately know "should we be excited or worried?"
2. **Scan "What got better"** to see the specific dangerous failures v2 now handles (hallucinated Frankenstein titles, fake booking confirmations, made-up 9/11 article citations)
3. **Skim "What still needs attention"** to know where v2 is still imperfect
4. **Drill into the per-category breakdown** for full context, only if they want it

The technical section at the bottom is the only place that uses eval-speak
(verdicts, tokens, latency). The rest of the report is plain English.

---

## If something goes wrong

- **Eval crashes mid-run:** `beta_colleague_round1.jsonl` is streamed per-turn, so partial results are usable. Re-run just the missing IDs (see `--filter` flag in `run_eval --help`).
- **No tunnels / Weaviate down:** the eval will refuse cleanly with `live_data_down` trigger. Bring tunnels up and retry.
- **Wrong file in `eval_results.jsonl`:** the report generator reads whatever you pass to `--results`, so this can't bite you here.
- **Numbers look weirdly low:** check that step 1 actually swapped the gold file. `wc -l src/eval/golden_set.jsonl` should be ~50 (37 cases + 13 comment/blank lines), not ~350 (full 234 set).

---

## What this proves to the librarians

The Nov 20 test caught 4 critical failure modes in v1:

1. **Hallucinated scholarly articles** (Q21: invented Borenstein, Goeldner, Foote articles with fake authors, page counts, journal names)
2. **Fake booking confirmations** (Q14: returned a fabricated confirmation number for a King study room without actually booking anything)
3. **Hallucinated book titles** (Q17: invented three scholarly Frankenstein-adjacent titles, claimed they were "in catalog")
4. **Made-up activation steps** (Q12: invented a "Databases A-Z → proxy/VPN → register for group pass" NYT flow not on the actual page)

These are the failures that should make a librarian uncomfortable with deploying. The report's "What got better" section lists them by name with the result, so the librarian team can see at a glance which of these v2 has actually solved.
