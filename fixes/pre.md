# Pipeline State — BEFORE Fixes

Date diagnosed: 2026-05-15  
Branch: convert-to-apis

---

## What was broken

### Stage 2 — LLM Evaluation

**Problem 1: Small/rare crops crashed with `IndexError`**  
Crops with few unique queries (typically <200–300) could not form the minimum 50 clusters
required by the standard viability check in `hyperparameter_tuning.py`. This meant Phase 1
produced 0 viable candidates. `run_phase2` then looped over an empty list, produced an
empty DataFrame, and crashed on `.iloc[0]`.

Affected crops: any crop that is rare in the dataset (low query volume per state file).

**Problem 2: No adaptive fallback for small crops**  
The `n_clusters >= 50` threshold in `is_viable_config` was hardcoded with no fallback.
A crop with 80 unique queries physically cannot produce 50 clusters. Every config was
rejected, leaving the pipeline with nothing to evaluate.

---

### Stage 3 — Cluster Repair

**Problem 3: Singleton clusters not deleted after cross-crop filter (Step B)**  
In `step_b_cross_crop`, the condition to delete a cluster that shrank to 1 query was:
```python
elif keep == 1:   # BUG: keep is a list — this is always False
```
This comparison always evaluates to `False`. Clusters that had all-but-one query removed
by the cross-crop filter were silently kept as 1-question clusters, producing degenerate
output downstream.

**Problem 4: Crash in Step C when Step B deletes all clusters**  
If Step B removed 100% of a crop's cluster contents (entire crop was off-topic / mislabelled),
`clusters` became an empty dict. Step C then attempted `max(clusters.keys())` on an empty
dict, raising `ValueError: max() arg is an empty sequence`.

**Problem 5: `_parse_json_list` had a phantom `self` parameter**  
The method was decorated `@staticmethod` but declared with `self` as its first argument:
```python
@staticmethod
def _parse_json_list(self, raw: str) -> list:
```
It was called as `self._parse_json_list(self, raw)` — which accidentally worked because
the instance was passed manually. However, this is incorrect and would silently break on
any refactor of the calling code.

---

### Stage 6 — Corpus Filter

**Problem 6: Undefined `col` variable in debug printout**  
In `filter_faq_corpus.py`, the removed-questions display loop referenced `col`, a variable
that was defined in an inner loop and retained whatever value it last held. In some execution
paths this variable was in scope (harmless); in others it could cause `NameError`. Regardless,
it always printed from the wrong column when multiple text columns were checked.
