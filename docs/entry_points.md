# Entry Points

These four scripts are the top-level CLI interfaces for the pipeline system. The backend calls them (directly or as subprocesses); users can also invoke them from the terminal.

---

## `run_full.py` — End-to-End Orchestrator

Runs the complete workflow: pre-pipeline → main pipeline (per crop) → post-pipeline.

```bash
python run_full.py \
  --raw-file app-data/cleaned_data.csv \
  --state Karnataka \
  --crops Cotton Sugarcane \
  --model google/gemma-4-26B-A4B-it \
  --api-key sk-ant-...
```

### Arguments

| Argument | Default | Description |
|---|---|---|
| `--raw-file` | required | Path to raw KCC CSV |
| `--state` | required | State name to filter |
| `--crops` | (all mapped) | Crops to process; omit to auto-detect from CSV |
| `--domains` | (all) | QueryType values to include |
| `--output` | `<state>_norm.csv` | Output path for normalized CSV |
| `--model` | required | HuggingFace model ID or local path |
| `--api-key` | `""` | Anthropic API key (enables Claude Haiku for Stage 4) |
| `--gpu-id` | `0` | CUDA device to use |
| `--batch-size` | `32` | vLLM batch size for Q&A generation |
| `--grid-mode` | `medium` | Hyperparameter grid size (`quick`/`medium`/`full`/`exhaustive`) |
| `--output-dir` | `outputs/repair` | Root directory for pipeline outputs |
| `--keep-intermediate` | `false` | Keep intermediate state-filtered CSV |
| `--skip-pre-pipeline` | `false` | Skip pre-pipeline (use existing normalized CSV) |
| `--skip-post-pipeline` | `false` | Skip post-pipeline deduplication |

### Execution Flow

```
1. [Optional] Pre-pipeline
   run_state_filter() + run_crop_normalizer()
   → produces <state>_norm.csv

2. For each crop (sequential):
   subprocess: python run_pipeline.py \
     --raw-file <norm_csv> \
     --crop <crop> \
     --model <model> \
     ...

3. [Optional] Post-pipeline
   run_post_pipeline() on outputs/<state>/
```

Registers each subprocess with `_job_ctl` so they can be cancelled via the backend's stop endpoint.

---

## `run_pipeline.py` — Per-Crop 7-Stage Pipeline

The core FAQ generation script. Runs all 7 stages for a single crop.

```bash
python run_pipeline.py \
  --raw-file app-data/karnataka_norm.csv \
  --crop "Cotton" \
  --model google/gemma-4-26B-A4B-it \
  --api-key sk-ant-... \
  --grid-mode medium
```

### Arguments

| Argument | Default | Description |
|---|---|---|
| `--raw-file` | required | Normalized CSV (output of pre-pipeline) |
| `--crop` | required | Canonical crop name to process |
| `--model` | required | LLM model ID or path |
| `--api-key` | `""` | Anthropic API key |
| `--gpu-id` | `0` | CUDA device |
| `--batch-size` | `32` | vLLM batch size |
| `--grid-mode` | `medium` | Phase 1 grid size |
| `--output-dir` | `outputs/repair` | Root output directory |
| `--max-queries` | `20000` | Cap on queries loaded for clustering |
| `--phase2-top-k` | `5` | Top-k Phase 1 configs to evaluate in Phase 2 |
| `--coverage-cap` | `0.80` | Minimum fraction of queries that must be clustered |
| `--diverse-k` | `3` | Representatives per cluster for LLM prompts |
| `--coherence-flag` | `C` | Coherence check variant (`B` or `C`) |
| `--merge-sim` | `0.82` | Cosine similarity threshold for cluster merging |
| `--skip-phase1` | `false` | Skip Phase 1 (use existing `phase1_results.pkl`) |
| `--skip-phase2` | `false` | Skip Phase 2 |
| `--skip-repair` | `false` | Skip cluster repair |
| `--skip-unique` | `false` | Skip unique question extraction |
| `--skip-dedup` | `false` | Skip deduplication |
| `--skip-filter` | `false` | Skip corpus filtering |
| `--skip-qa` | `false` | Skip Q&A generation |

### Output Location

All outputs written to `outputs/repair/<state_slug>/<crop_slug>/`.

The state slug is derived from the normalized CSV filename (e.g., `karnataka_norm.csv` → `karnataka_norm`). The crop slug is the canonical crop name lowercased with spaces replaced by underscores.

### Resume Behaviour

Each stage checks for its expected output file. Re-running the script will skip completed stages automatically. Delete a stage's output file to force it to re-run.

---

## `run_pre_pipeline.py` — Pre-Processing Orchestrator

Runs state filtering and crop normalization.

```bash
python run_pre_pipeline.py \
  --input app-data/cleaned_data.csv \
  --state Karnataka \
  --crops Cotton Sugarcane Paddy \
  --domains "pest,disease,nutrient" \
  --output app-data/karnataka_norm.csv
```

### Arguments

| Argument | Default | Description |
|---|---|---|
| `--input` | required | Raw KCC CSV |
| `--state` | required | State name to filter |
| `--crops` | (all mapped) | Canonical crop names to include |
| `--domains` | (all) | QueryType values to include |
| `--output` | required | Output normalized CSV path |
| `--keep-intermediate` | `false` | Preserve intermediate state-filtered CSV |

### Execution Flow

```
Stage 1: get_state_crop_rows.run_state_filter()
   → app-data/<state>_filtered_intermediate.csv  [deleted unless --keep-intermediate]

Stage 2: crop_normalizer.run_crop_normalizer()
   → <output>  (e.g. app-data/karnataka_norm.csv)
```

Both stages are called as direct Python function calls (not subprocesses). The backend `_run_pre_sync()` also imports and calls these functions directly.

---

## `run_post_pipeline.py` — Post-Processing Orchestrator

Runs LLM deduplication and final CSV generation for all crops in a state output directory.

```bash
python run_post_pipeline.py \
  --input outputs/repair/karnataka_norm \
  --crops Cotton Sugarcane
```

### Arguments

| Argument | Default | Description |
|---|---|---|
| `--input` | required | State-level output directory (contains crop subfolders) |
| `--crops` | (all found) | Crop names to process; omit to process every subfolder |
| `--skip-dedup` | `false` | Skip LLM deduplication (only produce final CSV from existing Q&A file) |
| `--batch-size` | `100` | Questions per deduplication batch |

### Execution Flow

```
For each crop subfolder in --input/:
  1. Load unique_questions_freq_qa.csv
  2. deduplicate_and_aggregate() → result_df, log_df
  3. Save log_df → phase_data_faq.csv
  4. Remove (unclassified) rows from result_df
  5. Save result_df → <state>_<crop>.csv
  6. Update meta.json
```

### Called From

- CLI (directly)
- `backend/routes/faq_cluster.py:_run_post_sync()` — called as `run_post_pipeline.run_post()` (direct import)
- `run_full.py` — called at the end of a full workflow run

---

## `_job_ctl.py` — Job Control

Not a user-facing script; a utility module used by the backend and entry point scripts for process registration and cancellation.

**Key functions**:

| Function | Description |
|---|---|
| `register(pid, job_id)` | Register a subprocess PID under a job ID |
| `check_cancel(job_id)` | Returns `True` if a stop was requested for this job |
| `kill_job(job_id)` | Send `SIGTERM` to the registered process group for a job |

The backend's `POST /jobs/{jobId}/stop` sets a cancellation flag, and the running script polls `check_cancel()` between stages (or between crop subprocesses in `run_full.py`). If cancelled, the subprocess is killed via `os.killpg(pgid, signal.SIGTERM)`.
