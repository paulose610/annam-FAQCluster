# Pipeline State — AFTER Fixes

Date applied: 2026-05-15  
Branch: convert-to-apis

---

## What changed and what to expect

### Stage 2 — LLM Evaluation

**Fix 1: Zero-candidates fallback in `run_phase2`**  
If Phase 2 evaluates 0 candidates (empty `rows` list), instead of crashing the pipeline
now logs a warning and falls back to the Phase 1 candidate with the lowest
`coverage_efficiency` (i.e., the tightest, most discriminative config available).
The pipeline continues to Stage 3 with this config.

**Fix 2: Adaptive viability threshold in `phase1_fast_screening`**  
If the standard screening produces 0 viable candidates, a second pass runs with
relaxed thresholds: `n_clusters >= max(5, len(df) // 20)` and `noise_ratio <= 0.5`.
For example, a crop with 100 unique queries now needs only 5 clusters to be viable.
For large crops, nothing changes — the fallback only fires when the standard pass returns empty.

Together, Fix 1 + Fix 2 mean that **small/rare crops that previously crashed will now
produce output**. The clustering quality may be lower than for large crops (fewer clusters,
more noise allowed), but the pipeline completes and delivers a usable FAQ.

---

### Stage 3 — Cluster Repair

**Fix 3: Singleton cluster deletion in Step B**  
Clusters that shrink to 0 or 1 query after cross-crop filtering are now correctly
marked for deletion. Previously they survived as degenerate 1-question clusters.
This may slightly reduce the final cluster count for some crops — this is correct behaviour.

**Fix 4: Empty-dict guard at top of Step C**  
If Step B deleted all clusters, Step C now exits early with a clear message and returns
`(clusters, 0)` instead of crashing. The pipeline continues to Steps D and E (which handle
empty input gracefully).

**Fix 5: Correct `@staticmethod` signature for `_parse_json_list`**  
Removed the spurious `self` parameter. The method is now a proper static method called
as `RepairJudge._parse_json_list(raw)`. Behaviour is identical — the method body never
used `self` — but the code is now correct and refactor-safe.

---

### Stage 6 — Corpus Filter

**Fix 6: `col` replaced with `available_cols[0]` in debug printout**  
The removed-questions display now consistently uses the first available text column
(typically `representative_question`). No change to filtering logic.

---

### Stage 6 — Corpus Filter (enhancement)

**Fix 9: Cross-crop keyword exclusion added to Stage 6**  
Stage 6 now also filters out FAQ rows that mention keywords belonging to any crop
*other than* the target crop, using `crops.yaml` as the keyword source.

How it works:
- `load_cross_crop_keywords(crops_yaml, target_crop)` collects all `keywords` entries
  from every crop in `crops.yaml` except the target crop.
- It then subtracts the target crop's own keywords from that set, so any keyword shared
  between two crops (e.g. "blast disease" appearing under multiple crops) is **never** used
  as an exclusion criterion. This prevents false positives.
- The resulting exclusion set is merged with the existing `irrelevant_corpus.yaml` keywords
  and the combined list is passed to the existing `is_irrelevant()` function unchanged.

Behaviour to expect:
- `corpus_filtered_out.csv` will contain more rows than before — it now catches both
  irrelevant-topic rows and cross-crop rows in a single pass.
- The pipeline console will print how many cross-crop keywords were loaded and how many
  survived after own-keyword subtraction.
- If the target crop is not found in `crops.yaml`, a warning is printed and cross-crop
  filtering is skipped gracefully (irrelevant-corpus filter still runs normally).
- Feature is on by default when `crops.yaml` is present in the project root.
  Disable with `--crops-file ""` if needed.
