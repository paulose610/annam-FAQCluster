# Pipeline Fix Audit Log

Date: 2026-05-15  
Branch: convert-to-apis  
Author: Claude (Sonnet 4.6)

---

## Fix 1 — Zero-candidates `IndexError` in `run_phase2`

**File:** `pipeline/cluster_repair.py`  
**Function:** `run_phase2` (~line 653)  
**Stage:** Stage 2 — LLM Evaluation  
**Severity:** Critical — crashes pipeline for small crops

**Root cause:**  
When Phase 1 produces 0 viable candidates, the `for result in top:` loop never runs,
`rows = []`, `pd.DataFrame(rows)` is an empty DataFrame, and
`p2_df.sort_values(...).iloc[0]` raises `IndexError`.

**Before:**
```python
p2_df = pd.DataFrame(rows)
p2_df.to_csv(out_dir / 'phase2_scores.csv', index=False)
best_cfg = p2_df.sort_values('composite_score', ascending=False).iloc[0]['config']
```

**After:**
```python
p2_df = pd.DataFrame(rows)
p2_df.to_csv(out_dir / 'phase2_scores.csv', index=False)

if p2_df.empty:
    if not candidates:
        raise ValueError(
            "No Phase 1 candidates and no Phase 2 results. "
            "The crop may have too few unique queries to cluster."
        )
    best = min(candidates, key=lambda r: r.metrics.get('coverage_efficiency', 1))
    best_cfg = str(best.config)
    print(f"\n  WARNING: 0 candidates evaluated in Phase 2 — "
          f"falling back to Phase 1 best: {best_cfg}")
    return best_cfg

best_cfg = p2_df.sort_values('composite_score', ascending=False).iloc[0]['config']
```

---

## Fix 2 — Adaptive viability threshold for small crops

**File:** `pipeline/hyperparameter_tuning.py`  
**Function:** `phase1_fast_screening` (~line 351)  
**Stage:** Stage 1 — Phase 1 Hyperparameter Screening  
**Severity:** Critical — root cause of Fix 1 being triggered

**Root cause:**  
`is_viable_config` requires `n_clusters >= 50`. Crops with <200–300 unique queries
cannot form 50 clusters under any configuration, so the entire candidates list stays empty.

**Before:**  
No fallback existed. Empty candidates list propagated directly to Phase 2 and crashed.

**After:**  
Added `all_results` list to collect every non-None result during the screening loop.
After the loop, if `candidates` is still empty, a second pass runs with thresholds
scaled to dataset size:
- `n_clusters >= max(5, len(df) // 20)`  — scales from 5 (tiny crops) upward
- `noise_ratio <= 0.5`                   — relaxed from 0.30

```python
all_results = []   # collect all non-None results for fallback

# (inside loop, after run_clustering succeeds:)
all_results.append(result)

# (after loop:)
if not candidates and all_results:
    fallback_min = max(5, len(df) // 20)
    print(f"\n  WARNING: No viable configs under standard thresholds (n_clusters >= 50).")
    print(f"  Re-screening {len(all_results)} results with relaxed thresholds "
          f"(min_clusters={fallback_min}, noise_ratio<=0.5)...")
    for r in all_results:
        if (r.metrics['n_clusters'] >= fallback_min
                and r.metrics['noise_ratio'] <= 0.5):
            candidates.append(r)
    print(f"  Relaxed screening found {len(candidates)} candidates")
```

---

## Fix 3 — `keep == 1` list-vs-int comparison always False

**File:** `pipeline/cluster_repair.py`  
**Function:** `step_b_cross_crop` (~line 314)  
**Stage:** Stage 3 — Cluster Repair, Step B  
**Severity:** High — singleton clusters survive silently instead of being deleted

**Root cause:**  
`keep` is a list of surviving index positions. `keep == 1` compares the list object to the
integer 1, which is always `False` in Python. The branch was dead code.

**Before:**
```python
elif keep == 1:
    # Cluster shrank to 1: mark for deletion
    clusters[cid]['_delete'] = True
```

**After:**
```python
else:
    # Cluster shrank to 0 or 1 query: mark for deletion
    clusters[cid]['_delete'] = True
```

The `len(keep) >= 2` branch above already handles the keep case, so `else` correctly
covers both the 0-query and 1-query scenarios.

---

## Fix 4 — `max(clusters.keys())` crash on empty dict in Step C

**File:** `pipeline/cluster_repair.py`  
**Function:** `step_c_split` (~line 337)  
**Stage:** Stage 3 — Cluster Repair, Step C  
**Severity:** High — crashes if Step B deleted all clusters

**Root cause:**  
If Step B (`step_b_cross_crop`) marks every cluster for deletion (e.g. the entire crop was
mislabelled), `clusters` is an empty dict when Step C begins. `max({}.keys())` raises
`ValueError: max() arg is an empty sequence`.

**Before:**  
No guard; crash was immediate.

**After:**
```python
if not clusters:
    print("  No clusters remaining — skipping split step")
    return clusters, 0
max_cid = max(clusters.keys())
```

---

## Fix 5 — `@staticmethod` with phantom `self` parameter

**File:** `pipeline/cluster_repair.py`  
**Class:** `RepairJudge`  
**Method:** `_parse_json_list` (~line 153)  
**Stage:** Stage 3 — Cluster Repair, Step C (split)  
**Severity:** Medium — worked accidentally; breaks on any refactor

**Root cause:**  
The method was declared `@staticmethod` but had `self` as its first parameter.
It was called as `self._parse_json_list(self, raw)` — passing the instance manually
as the first positional arg to compensate. This worked only because the method body
never actually used `self`.

**Before:**
```python
@staticmethod
def _parse_json_list(self, raw: str) -> list:
    ...
# call site:
groups_raw = self._parse_json_list(self, raw)
```

**After:**
```python
@staticmethod
def _parse_json_list(raw: str) -> list:
    ...
# call site:
groups_raw = RepairJudge._parse_json_list(raw)
```

---

## Fix 6 — Undefined `col` in `filter_faq_corpus.py` debug output

**File:** `pipeline/filter_faq_corpus.py`  
**Function:** `filter_faq` (~line 147)  
**Stage:** Stage 6 — Corpus Filter  
**Severity:** Low — display-only; filtering logic unaffected

**Root cause:**  
`col` was a loop variable from the inner `for col in available_cols:` loop. After the
outer row-iteration loop completed, `col` retained whatever column name was last
assigned — non-deterministic, and potentially `NameError` if execution paths differed.

**Before:**
```python
for q in removed_df[col].tolist():
    print(f"    – {q}")
```

**After:**
```python
for q in removed_df[available_cols[0]].tolist():
    print(f"    – {q}")
```

`available_cols[0]` is always defined at this point (guarded by the `if not available_cols`
check earlier in the function) and is typically `representative_question`.

---

## Fix 7 — `int()` crash when LLM returns dict objects inside `indices`

**File:** `pipeline/cluster_repair.py`  
**Functions:** `split_cluster`, `cross_crop_filter`  
**Stage:** Stage 3 — Cluster Repair, Steps B & C  
**Severity:** High — crashes the entire crop run mid-repair

**Root cause:**  
The LLM occasionally returns malformed JSON where the `indices` array contains nested
objects instead of plain integers (e.g. `[{"value":1},{"value":2}]`). Both
`split_cluster` and `cross_crop_filter` called `int(i)` directly on each element,
raising `TypeError: int() argument must be a string, a bytes-like object or a real
number, not 'dict'`.

**Before:**
```python
# split_cluster
idxs = [int(i) - 1 for i in g.get("indices", [])
        if 1 <= int(i) <= len(queries) and (int(i) - 1) not in seen]

# cross_crop_filter
return [int(i) - 1 for i in off if 1 <= int(i) <= len(queries)]
```

**After:**  
Added `_safe_int(x)` helper that returns `None` for any non-castable type (dicts,
lists, bools). Both call sites now use it, silently skipping bad values. Unassigned
queries are absorbed into the largest group by the existing fallback.

```python
def _safe_int(x):
    if isinstance(x, bool): return None
    if isinstance(x, (int, float)): return int(x)
    if isinstance(x, str):
        try: return int(x)
        except ValueError: return None
    return None
```

---

## Fix 8 — LLM prompt hardening + retry for non-integer `indices`

**File:** `pipeline/cluster_repair.py`  
**Functions:** `split_cluster`, `cross_crop_filter`  
**Stage:** Stage 3 — Cluster Repair, Steps B & C  
**Severity:** Medium — preventive; reduces occurrence of Fix 7 scenario

**Root cause:**  
The original prompts did not explicitly forbid object values inside `indices`, making
it easy for the model to produce `[{"value":1}]`-style output.

**Changes:**  
1. Both prompts now say `"indices" values MUST be plain integers like [1,2,3] — NOT objects`.  
2. `split_cluster` extracted its prompt into `_split_prompt` (static) and wraps generation
   in a retry loop: if the first response contains any non-integer index, a warning is
   logged and one retry is issued. The `_safe_int` backstop (Fix 7) still applies on the
   second attempt.

```python
for attempt in range(2):
    raw        = self._gen_long(self._split_prompt(qstr, crop), max_new_tokens=350)
    groups_raw = RepairJudge._parse_json_list(raw)
    bad = any(not isinstance(i, (int, float))
              for g in groups_raw for i in g.get("indices", []))
    if bad and attempt == 0:
        logging.warning("split_cluster: non-integer indices in LLM output — retrying")
        continue
    break
```
