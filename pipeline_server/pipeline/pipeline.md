# FAQCluster Pipeline Documentation

## Overview

The pipeline converts a raw KCC (Kisan Call Centre) CSV of farmer queries into a structured FAQ with Q&A pairs. It runs in 7 sequential stages, orchestrated by `run_pipeline.py`.

```
Raw CSV  →  Cluster  →  Tune  →  Repair  →  Extract  →  Dedup  →  Filter  →  Q&A
  Stage1      Stage2    Stage3   Stage4     Stage5    Stage6   Stage7
```

**Entry point:** `python run_pipeline.py --raw-file <csv> --crop "Crop Name" --api-key <key>`

**Final outputs** (in `outputs/repair/<crop_slug>/`):
- `unique_questions_freq.csv` — ranked FAQ questions
- `unique_questions_freq_qa.csv` — FAQ with generated Q&A pairs

---

## Data Model

The raw input CSV has at minimum these columns:
- `QueryText` — the farmer's question text (may be Hindi, Hinglish, or English)
- `Crop` — crop name (e.g. "Maize (Makka)")

Each stage transforms this data, eventually producing per-question rows with cluster assignments, frequencies, and generated answers.

---

## Stage 1 — Hyperparameter Screening (`hyperparameter_tuning.py`)

**What it does:** Finds the best combination of clustering parameters by testing many configurations quickly.

### Data preparation
1. Load raw CSV, filter rows to the target crop
2. Aggregate duplicate `QueryText` rows into `(query_text, count)` pairs — this reduces tens of thousands of rows to unique questions with a frequency count
3. Optionally sample down to `--max-queries` (default 20,000)

### Text preprocessing
Each query is lowercased, stripped of non-alpha characters, and filtered through a bilingual stop-word list. The stop-word list covers both English function words and common Hindi/Hinglish words (`hai`, `karna`, `fasal`, etc.) as well as generic farming vocabulary (`crop`, `khet`, `seed`) that would otherwise dominate cluster distances.

### Feature extraction
Two complementary representations are built:

**Dense embeddings** — `sentence-transformers/paraphrase-multilingual-mpnet-base-v2` encodes each preprocessed query into a 768-dimensional semantic vector. This model supports Hindi/English/mixed text. *(Learn separately: sentence transformers / SBERT)*

**Sparse TF-IDF features** — A `TfidfVectorizer` (max 1000 features, min_df=2) builds a keyword weight matrix. *(Learn separately: TF-IDF)*

### Hybrid distance matrix
```
hybrid_dist = α × cosine_dist(dense) + (1−α) × jaccard_dist(tfidf_binary)
```
Alpha (α) controls the trade-off between semantic similarity (dense) and keyword overlap (sparse). This is one of the tuned hyperparameters. *(Learn separately: Jaccard distance on binary vectors)*

### Dimensionality reduction (UMAP)
The hybrid distance matrix (NxN) is reduced to 5 dimensions with UMAP (`metric='precomputed'`). UMAP preserves local and global structure better than PCA for non-linear manifolds. This is what HDBSCAN operates on. *(Learn separately: UMAP)*

### Clustering (HDBSCAN)
HDBSCAN clusters the reduced points. Key parameters being tuned:
- `min_cluster_size` — minimum points to form a cluster
- `min_samples` — controls how conservative the clustering is (higher = fewer, denser clusters)
- `n_neighbors` (UMAP) — controls neighbourhood structure

Points labelled `-1` (noise) are handled in two ways:
1. High-frequency noise (count > 50) → promoted to their own singleton cluster
2. Remaining noise → assigned to nearest cluster via 1-NN

*(Learn separately: HDBSCAN — the core algorithm powering all clustering)*

### Screening logic
A config is "viable" if:
- 50 ≤ n_clusters ≤ 1000
- noise_ratio ≤ 0.30
- clusters_for_85pct ≥ 5

Viable candidates are pickled to `phase1_results.pkl`.

### Caching for speed
The code uses three shared cache dicts across all config iterations:
- `_embed_cache` — embeddings computed once
- `_dist_cache` — hybrid distance per alpha value (reused when only `min_cluster_size`/`min_samples` change)
- `_umap_cache` — UMAP output per `(alpha, n_neighbors, n_components)` triple

This means only HDBSCAN re-runs for configs sharing the same UMAP projection, making Phase 1 tractable even with 240+ configs.

**Grid modes:** `quick`(18 configs) / `medium`(108) / `full`(240) / `exhaustive`(480)

---

## Stage 2 — LLM Evaluation (`llm_evaluator_hf.py`)

**What it does:** Takes the top-K Phase 1 candidates and uses a local LLM (Qwen2.5-7B-Instruct) to score each configuration on 4 semantic quality dimensions.

### Candidate selection
Uses stratified sampling from the Phase 1 candidates pool (top / middle / bottom / diverse-in-parameter-space) rather than just taking the top K by metric. This ensures the LLM sees a calibrated range.

### LocalHFJudge
Loads Qwen2.5-7B-Instruct in `bfloat16` on a single GPU. Uses left-padded batch generation (greedy, `max_new_tokens=4`) since the model only needs to return a single letter (A/B/C). The Qwen chat template is applied via `apply_chat_template`.

### 4 evaluation passes per config

**Pass 1 — Coherence** (cluster-level, size-weighted): "Are all questions in this cluster about the same agricultural topic?" → A(1.0) / B(0.7) / C(0.2)

**Pass 2 — Separation** (random cluster pairs): "Should these two groups be in different clusters?" → A(1.0) / B(0.6) / C(0.0)

**Pass 3 — Merge detection** (keyword-overlap pairs): "Should these two near-identical clusters be merged?" → A(merge) / B(keep)

**Pass 4 — Outlier detection** (cluster-level): "Which question (if any) does NOT belong?"

### Composite score
```
composite = 0.45 × separation + 0.30 × coherence + 0.25 × (1 − outlier_rate) − 0.20 × merge_rate
```
Higher is better. The config with the highest composite score is the winner.

### Sharding support
`--shard 1/2` and `--shard 2/2` allows running two GPUs in parallel, each evaluating half the configs. Results are merged with `--merge-shards`.

---

## Stage 3 — Cluster Repair (`cluster_repair.py`)

**What it does:** Takes the best clustering config and applies 5 repair steps (A–E) to clean up the clusters using embeddings + LLM reasoning.

### Step A — Max-diversity representative selection
For each cluster, selects k=3 "maximally diverse" representative questions using greedy furthest-point selection on embeddings:
1. First representative = centroid-nearest question (most typical)
2. Subsequent reps = farthest from already-selected set (cosine distance)

These diverse reps are used as diagnostic inputs in Steps B–C rather than showing the LLM all questions, saving tokens and improving signal quality.

### RepairJudge
Extends `LocalHFJudge` with methods that produce JSON output (using `_gen_long`, `max_new_tokens=300–350`). JSON is extracted with regex and parsed safely.

### Step B — Cross-crop contamination filter
For each cluster, the LLM identifies query indices that "clearly ask about a DIFFERENT crop". Off-topic queries are removed. If a cluster shrinks to 1 query, it's deleted.

### Step C — Coherence diagnostic + split
For each cluster, the LLM is shown its 3 diverse reps and asked if an agricultural officer would give the same advice for all of them:
- A (identical advice) → keep
- B (mostly similar) → keep
- C (different advice needed) → trigger full split

For clusters rated C, the LLM receives all queries and groups them into sub-clusters by treatment type. Sub-clusters with fewer than 2 members are merged into the largest group. The `coherence_flag` parameter (`B` or `C`) controls aggressiveness.

### Step D — Merge near-duplicate clusters
1. Encode all cluster representatives with the sentence transformer
2. Build a cosine similarity matrix
3. Candidate pairs with similarity ≥ 0.82 are LLM-confirmed with "should_merge"
4. If yes, the smaller cluster is absorbed into the larger

### Step E — Raw row back-mapping
Builds a `query_text → final_cluster_id` mapping from the repaired clusters, then joins with the original raw CSV. Produces:
- `repaired_clusters.csv` — one row per final cluster with metadata
- `raw_row_mapping.csv` — original CSV rows annotated with cluster assignments
- `cluster_questions.csv` — one row per unique question in each cluster

---

## Stage 4 — Unique Question Extraction (`unique_question_finder.py`)

**What it does:** Within each cluster, further groups questions that would receive the **exact same agricultural answer** into a single "unique question" entry. This is the core FAQ compression step.

### Prompt design
The LLM is told to group questions so that "every question in a group would receive the EXACT SAME specific agricultural advice — same chemical, same dose, same method, same timing." The label must describe **the answer**, not the question topic (e.g. "Chlorpyrifos soil drench for termite" not "pest control").

### Two provider modes

**Anthropic (Claude Haiku via Batch API)** — Recommended. Submits all clusters as a single batch request, polls every 30 seconds until done. Handles clusters of 50+ questions cleanly.

**Local Qwen 7B** — Falls back to `RepairJudge._gen_long`. Large clusters (>12 questions) are split into batches of 12, processed independently, then merged with a cross-batch similarity + LLM check (`_merge_cross_batch`).

### Cross-cluster dedup
After per-cluster grouping, a final pass looks across clusters for representative questions with cosine similarity ≥ 0.92. Near-identical groups from different clusters are merged, keeping the one with higher frequency and summing the counts.

### Checkpoint / resume support
Results are written to `unique_questions_checkpoint.json` after each cluster. `--resume` skips already-processed clusters.

### Outputs
- `unique_questions.csv` — one row per answer-distinct group
- `unique_questions_freq.csv` — same, sorted by `raw_frequency` descending
- `unique_question_mapping.csv` — each input question mapped to its group
- `unique_questions_verification.csv` — sanity stats (frequency sum check, reduction ratio)

---

## Stage 5 — Deduplication (`dedup_freq_csv.py`)

**What it does:** Removes duplicate `representative_question` values from `unique_questions_freq.csv` (case-insensitive, whitespace-normalised). For each duplicate group, keeps the row with the highest `raw_frequency`. Drops the `rank` column (pipeline always passes `--drop-rank`).

This is a clean-up stage to catch any residual duplicates that cross-cluster dedup in Stage 4 may have missed.

---

## Stage 6 — Irrelevant Corpus Filtering (`filter_faq_corpus.py`)

**What it does:** Removes rows whose `representative_question`, `cluster_label`, or `answer_label` match keywords from an `irrelevant_corpus.yaml` file. This removes off-topic queries about weather, market prices, government schemes, contact numbers, etc. that slipped through clustering.

### Matching strategy
For each question, for each word (≥ 3 chars after stripping punctuation):
1. Exact match against keyword set
2. Fuzzy match (`fuzz.ratio ≥ threshold`) against keywords of similar length (`|len_word - len_kw| ≤ 2`)

Multi-word keywords use fast substring matching first.

The default `--fuzz-threshold` is 100 (exact-only) when called from `run_pipeline.py`.

Removed rows are saved to `corpus_filtered_out.csv` for audit.

---

## Stage 7 — Q&A Generation (`vllm_batch_qa_generator.py`)

**What it does:** Generates professional English Q&A pairs for each row in `unique_questions_freq.csv` using vLLM offline batch inference.

*(Learn separately: vLLM — offline batch inference engine for local LLMs)*

### System prompt engineering
A detailed system prompt is built per crop. It contains:
- A scope rule listing all out-of-scope crops (with synonym handling so "Maize" and "Makka" are treated as the same crop)
- Crop-specific expert hints (e.g. for Maize: focus on fall armyworm, stem borer, turcicum leaf blight)
- Mandatory English language rule (even if input is Hindi/Hinglish)
- Output format specification: `CATEGORY: / QUESTION: / ANSWER:`
- 7 valid categories: Disease / Pest / Fertilizer and Nutrient / Variety / Agronomy / Other / IRRELEVANT_CROP

### Generation
Uses `vllm.LLM` with `SamplingParams(temperature=0.0, max_tokens=4000)`. All prompts are batched in one `llm.generate()` call. The tokenizer's `apply_chat_template` formats them as instruct-model conversations.

### Parsing
`parse_text_response()` uses regex to extract CATEGORY, QUESTION, and ANSWER from the model's free-text output. Handles markdown code-block wrappers and bold headers. Rows that fail parsing get `Generated_Category = "PARSE_ERROR"`.

---

## Supporting Modules

### `cluster_raw_csv.py`
A standalone script (not called by `run_pipeline.py`) that runs the same HDBSCAN+UMAP pipeline directly on a raw CSV without hyperparameter tuning. Useful for quick one-off clustering. Outputs `mapping.csv`, `summary.csv`, and `top10_clusters.csv`.

### `cluster_mapping.py`
Generates human-readable cluster summary CSVs from a Phase 1 pickle, using an auto-detected or specified best config. Useful for manual inspection of clustering results without re-running anything.

---

## Full Data Flow

```
raw_file.csv
    │
    ├─ Stage 1: unique (query_text, count) pairs
    │           → phase1_results.pkl  [ClusteringResult objects]
    │
    ├─ Stage 2: LLM scores per config
    │           → phase2_scores.csv
    │
    ├─ Stage 3: repaired clusters
    │           → repaired_clusters.csv
    │           → cluster_questions.csv   ← one row per unique question
    │           → raw_row_mapping.csv
    │
    ├─ Stage 4: answer-grouped questions
    │           → unique_questions.csv
    │           → unique_questions_freq.csv
    │
    ├─ Stage 5: deduped freq CSV
    │           → unique_questions_freq.csv (overwrite)
    │
    ├─ Stage 6: irrelevant rows removed
    │           → unique_questions_freq.csv (overwrite)
    │           → corpus_filtered_out.csv
    │
    └─ Stage 7: Q&A generated
                → unique_questions_freq_qa.csv
```

---

## Topics to Learn Separately

| Topic | Used in | Why it matters |
|---|---|---|
| **HDBSCAN** | Stages 1–2 | Core clustering algorithm — understanding density-based clustering, noise points, `min_cluster_size`, `min_samples`, and the EOM leaf method is essential to reasoning about results |
| **UMAP** | Stages 1–2 | Dimensionality reduction before clustering — `n_neighbors` and `min_dist` control how local vs. global structure is preserved; the `precomputed` metric mode is used here |
| **Sentence Transformers (SBERT)** | Stages 1, 3, 4 | How `paraphrase-multilingual-mpnet-base-v2` encodes text into vectors, and why cosine similarity over these vectors captures semantic meaning |
| **TF-IDF + Jaccard distance** | Stage 1 | How TF-IDF weights terms by rarity, and why binarising it and using Jaccard distance captures keyword overlap as a complementary signal to dense embeddings |
| **vLLM** | Stage 7 | Offline batch inference engine — how it schedules prompts, what tensor parallelism means, and why it's faster than standard HF `generate()` for large batches |

---

## Pipeline Flags Reference

| Flag | Default | Description |
|---|---|---|
| `--skip-phase1` | off | Load existing `phase1_results.pkl` instead of re-running |
| `--skip-phase2` | off | Load best config from `phase2_scores.csv` instead of re-running |
| `--skip-repair` | off | Use existing `cluster_questions.csv` |
| `--skip-unique-q` | off | Use existing `unique_questions_freq.csv` |
| `--skip-corpus-filter` | off | Skip Stage 6 irrelevant query removal |
| `--skip-qa-gen` | off | Skip Stage 7 Q&A generation |
| `--grid-mode` | `medium` | HP grid size: quick(18) / medium(108) / full(240) / exhaustive(480) |
| `--phase2-top-k` | 5 | Number of Phase 1 candidates to LLM-evaluate |
| `--coverage-cap` | 0.80 | Fraction of query volume to cover in Phase 2 evaluation |
| `--coherence-flag` | `C` | LLM rating that triggers a cluster split (C=strict, B=aggressive) |
| `--merge-sim` | 0.82 | Cosine similarity threshold for merge candidates in Step D |
| `--diverse-k` | 3 | Number of max-diverse reps per cluster in Step A |
| `--fuzz-threshold` | 100 | Fuzzy match threshold for corpus filter (100 = exact only) |
