# Pipeline — 7-Stage FAQ Generation

The core pipeline transforms a normalized crop CSV into a final FAQ dataset with Q&A pairs. It runs once per crop, is **resume-safe** (each stage checks for existing output before running), and is invoked by `run_pipeline.py`.

**Location**: `pipeline/`
**Entry point**: `run_pipeline.py` (see [Entry Points](entry_points.md))

---

## Stage Overview

| # | Stage | Module | Input | Output |
|---|---|---|---|---|
| 1 | Hyperparameter Screening | `hyperparameter_tuning.py` | Normalized CSV | `phase1_results.pkl`, `phase1_candidates.csv` |
| 2 | LLM Evaluation | `cluster_repair.py` (`run_phase2`) | Phase 1 pickle | `phase2_scores.csv` |
| 3 | Cluster Repair | `cluster_repair.py` | Phase 2 best config | `cluster_questions.csv`, `unique_q_id_to_raw_rows.csv` |
| 4 | Unique Question Extraction | `unique_question_finder.py` | `cluster_questions.csv` | `unique_question_mapping.csv`, `unique_questions_freq.csv` |
| 5 | Deduplication | `dedup_freq_csv.py` | `unique_questions_freq.csv` | `unique_questions_freq.csv` (updated) |
| 6 | Corpus Filtering | `filter_faq_corpus.py` | `unique_questions_freq.csv` | `unique_questions_freq.csv` (filtered), `corpus_filtered_out.csv` |
| 7 | Q&A Generation | `vllm_batch_qa_generator.py` | `unique_questions_freq.csv` | `unique_questions_freq_qa.csv` |

---

## Stage 1 — Hyperparameter Screening (`hyperparameter_tuning.py`)

**Goal**: Discover the best HDBSCAN + UMAP configuration for clustering queries of a given crop.

**Process**:
1. Load the normalized CSV and filter rows to the target crop.
2. Drop exact-duplicate queries; sample down to `max_queries` (default: 20,000).
3. Load multilingual MPNET sentence-transformer embeddings.
4. Generate a parameter grid based on `--grid-mode`:
   - `quick`: 18 configurations
   - `medium`: 108 configurations
   - `full`: 240 configurations
   - `exhaustive`: 480 configurations
5. For each config, run UMAP dimensionality reduction → HDBSCAN clustering.
6. Score each result: silhouette score, number of clusters, coverage (% queries assigned to a cluster).
7. Rank and save top candidates.

**Grid parameters swept**:
- UMAP: `n_neighbors`, `n_components`, `min_dist`
- HDBSCAN: `min_cluster_size`, `min_samples`

**Output files**:
- `phase1_results.pkl` — full pickle of all scored configurations
- `phase1_candidates.csv` — ranked metrics table

---

## Stage 2 — LLM Evaluation (`cluster_repair.py` → `run_phase2`)

**Goal**: Use an LLM to evaluate the top-k configurations from Stage 1 and select the best one.

**Process**:
1. Load top-k candidates (default: 5) from `phase1_candidates.csv`.
2. For each candidate, sample representative queries from each cluster.
3. Prompt the LLM (local Qwen-2.5-7B or Claude API) to rate:
   - **Coherence**: Are queries within a cluster semantically similar?
   - **Diversity**: Are clusters well separated from each other?
   - **Contamination**: Do clusters contain queries from other crops?
4. Compute composite score; pick the best configuration.

**Output**: `phase2_scores.csv` with best config parameters.

---

## Stage 3 — Cluster Repair (`cluster_repair.py`)

**Goal**: Refine the chosen clustering — improve quality through 5 sequential sub-steps.

### Step A — Diverse Representatives
- For each cluster, select the `k` most diverse queries using embedding cosine distances.
- Reduces size of cluster representation for subsequent LLM prompts.
- Controlled by `--diverse-k` (default: 3).

### Step B — Cross-Crop Filter
- Prompt LLM to identify and remove queries that are about a different crop.
- E.g., remove queries about "rice" from a "Cotton" cluster.

### Step C — Coherence + Split
- LLM evaluates each cluster's coherence on a 1–5 scale.
- Clusters rated ≤ threshold are split into sub-clusters via a recursive re-clustering step.
- Coherence flag `--coherence-flag`:
  - `'C'` (default): standard coherence check
  - `'B'`: broader coherence check

### Step D — Merge
- Compute pairwise cosine similarity between cluster centroids (embedding mean).
- Merge any two clusters whose similarity exceeds `--merge-sim` (default: 0.82).
- Prevents over-fragmentation from Step C splits.

### Step E — Raw Mapping
- Map repaired cluster assignments back to original raw CSV rows (before sampling/dedup).
- Preserves full frequency information.

**Output files**:
- `cluster_questions.csv` — one row per unique query, with `cluster_id` column
- `unique_q_id_to_raw_rows.csv` — mapping from unique query ID to original CSV row indices

---

## Stage 4 — Unique Question Extraction (`unique_question_finder.py`)

**Goal**: Generate one canonical representative question per cluster.

**Process**:
1. Load `cluster_questions.csv`; group rows by `cluster_id`.
2. For each cluster, pass the diverse representative queries to the LLM.
3. LLM returns a single clean, well-formed question that captures the cluster topic.
4. **Resume-safe**: checkpoint written to `unique_questions_checkpoint.json` after each cluster; incomplete runs resume from last checkpoint.

**LLM options**:
- `--api-key` provided → Claude Haiku (Anthropic API)
- No API key → local Qwen-2.5-7B via HuggingFace transformers

**Output files**:
- `unique_question_mapping.csv` — cluster_id → generated question
- `unique_questions_freq.csv` — questions with raw frequency counts and category metadata

---

## Stage 5 — Deduplication (`dedup_freq_csv.py`)

**Goal**: Remove near-duplicate questions that survived cluster-level deduplication.

**Process**:
- Embeds all generated questions.
- Identifies pairs with cosine similarity ≥ 0.85 (default threshold).
- Keeps the higher-frequency question; aggregates frequency counts from the removed duplicate.

**Output**: `unique_questions_freq.csv` (deduplicated in-place).

---

## Stage 6 — Irrelevant Corpus Filtering (`filter_faq_corpus.py`)

**Goal**: Remove questions about topics unrelated to agricultural advisory (market prices, weather, contact info, etc.).

**Configuration**: `config/irrelevant_corpus.yaml`

Each category in the YAML has:
```yaml
market_price:
  description: "Market and pricing queries"
  keywords: ["price", "mandi", "rate", "sell", "market"]
  typos: ["prise", "mrkt"]
```

**Process**:
1. Load `config/irrelevant_corpus.yaml`.
2. For each question, fuzzy-match against all keyword lists.
3. Optionally load `crops.yaml` for cross-crop keyword exclusion (e.g., exclude Cotton-specific terms from Wheat cluster).
4. Remove matching rows, saving them to `corpus_filtered_out.csv` for audit.

**Output files**:
- `unique_questions_freq.csv` (filtered)
- `corpus_filtered_out.csv` — removed rows for review

---

## Stage 7 — Q&A Generation (`vllm_batch_qa_generator.py`)

**Goal**: Generate an answer for every question, producing the final FAQ dataset.

**Process**:
1. Load `unique_questions_freq.csv`.
2. Group questions by crop for batched inference.
3. Use vLLM with Qwen-2.5-7B in batch mode to generate answers.
4. Each question is prompted with crop context for domain-specific answers.

**Key parameters**:
- `--batch-size` (default: 32) — number of questions per vLLM batch
- Model specified by `--model` (path or HuggingFace ID)

**Output**: `unique_questions_freq_qa.csv` — adds `Generated_Answer` and `Generated_Category` columns to the questions CSV.

---

## Resume Safety

Every stage checks for its expected output file before running. To force a stage to re-run, delete its output file and re-invoke `run_pipeline.py`. Use `--skip-*` flags to explicitly skip individual stages.

```bash
# Skip all stages except Q&A generation
python run_pipeline.py --raw-file data.csv --crop Cotton \
  --skip-phase1 --skip-phase2 --skip-repair --skip-unique \
  --skip-dedup --skip-filter
```

---

## Key Classes and Functions

| Symbol | File | Description |
|---|---|---|
| `run_phase1()` | `hyperparameter_tuning.py` | Grid search entrypoint |
| `run_phase2()` | `cluster_repair.py` | LLM evaluation of top-k configs |
| `RepairJudge` | `cluster_repair.py` | Wraps LLM for all repair prompts |
| `run_repair()` | `cluster_repair.py` | Orchestrates Steps A–E |
| `run_unique_question_finder()` | `unique_question_finder.py` | Stage 4 entrypoint |
| `run_dedup()` | `dedup_freq_csv.py` | Stage 5 entrypoint |
| `run_filter()` | `filter_faq_corpus.py` | Stage 6 entrypoint |
| `run_qa_generation()` | `vllm_batch_qa_generator.py` | Stage 7 entrypoint |
| `LLMEvaluator` | `llm_evaluator_hf.py` | HuggingFace LLM wrapper used by stages 2–4 |
