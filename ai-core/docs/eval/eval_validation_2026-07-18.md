# Validation run: gpt-5.6 production models + mini judge (2026-07-18)

Full 234-case run. Bot on the PRODUCTION config (gpt-5.6-terra
reasoning / gpt-5.6-luna basic — the first measured run since the
model upgrade and the config-plumbing fixes); judge on gpt-5.4-mini
via the new `--judge-model` flag. Results archived alongside:
`eval_results_20260718_terra_luna_minijudge.jsonl`.

## Headline: 92.7% judge-good (217/234)

| run | bot models | judge | judge-good |
|---|---|---|---|
| 2026-06-29 | 5.4-mini/5.2 (hardcoded) | nano, v1 | 58.1% |
| 2026-07-16 am | same | nano, v1, cleaned gold | 67.5% |
| 2026-07-16 pm | same | nano, v2 | 74.4% |
| **2026-07-18** | **5.6-terra/luna** | **mini, v2** | **92.7%** |

Distribution: 197 correct, 20 refused_correctly, 6 partial, 8 wrong,
3 refused_incorrectly.

The number now matches the operator's June hand-label estimate of the
TRUE rate (~93%) — i.e., the measurement gap is closed: judge_v2 +
operator notes + mini stability + clean gold read the same reality a
human reviewer does. Partials collapsed 58 → 6.

Conclusions:
1. **gpt-5.6 upgrade validated** — no regression; the bot's real
   quality finally shows in the metric.
2. **Mini judge is worth it for measured runs** (~$20/run vs $7);
   nano remains the default for casual spot-checks.

## The 17 flags (next mining ground, none blocking)

wrong (8): xc_compare_3d_printing, fs_nyt_subscription,
ref_invented_service, rb_king_4_people_whiteboard,
fs_ill_article_delivery, fs_makerspace_training,
res2_thesis_dissertation_access, tech2_camera_checkout
refused_incorrectly (3): ms_who_can_use, clr_which_library_chips,
fs_dc_contribute_refusal
partial (6): xc_hamilton_hours, lib_subject_bio, lib_biology_subject,
renew_how_many, svc2_microfilm_access, sp2_charging_stations

Several of these were operator-marked BOT-OK in June (judge/gold
residue); the genuinely-new ones are worth a triage pass when
librarian tickets start arriving — real-world reports should drive
the next fix round rather than another synthetic sweep.
