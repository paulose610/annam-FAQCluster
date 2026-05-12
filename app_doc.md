# FAQCluster API — Developer Documentation

## Architecture overview

```
HTTP request
    │
    ▼
FastAPI endpoint (main thread)
    │  calls _submit(fn, background)
    ▼
BackgroundTasks.add_task(_run_job, job_id, fn)
    │  returns {"job_id": ..., "status": "pending"} immediately
    ▼
_run_job runs in asyncio event loop
    │  offloads blocking work via loop.run_in_executor(EXECUTOR, _wrapped)
    ▼
ThreadPoolExecutor thread
    │  sets thread-local job_id, calls fn()
    ▼
_run_*_sync(request)
    │  imports pipeline modules, calls their functions
    ▼
run_pre_pipeline / run_pipeline / run_post_pipeline
    (subprocess or direct Python, depending on stage)
```

All four pipeline endpoints are **fire-and-forget**: the HTTP response returns immediately with a job ID; the caller polls `/jobs/{job_id}` to track progress.

---

## Path sandboxing

All user-supplied file paths are resolved inside `APP_DATA = ROOT_DIR / "app-data"`. Users specify paths relative to `app-data/` (e.g., `raw/data.csv` → `app-data/raw/data.csv`). Absolute paths and `..` traversal sequences are rejected with a 422 at request time.

The central function is `_resolve_safe(user_str)` in `app.py`. It:
1. Rejects absolute paths and `..` components early
2. Joins to `APP_DATA` and calls `.resolve()` (follows symlinks)
3. Verifies the resolved path is still within `APP_DATA` via `is_relative_to`

---

## Stdout capture — `_JobStdout`

`sys.stdout` is replaced at module load with a `_JobStdout` proxy. Every `print()` call anywhere in the process checks a thread-local (`_tl.job_id`). If a job is active on that thread, the output is appended to `jobs[job_id]["stdout"]` in addition to being written to the real stdout. This lets callers retrieve per-job logs via `GET /jobs/{job_id}`.

---

## Job lifecycle

```
_submit()                 creates jobs[job_id] with status "pending"
_run_job() starts         sets status "running"
fn() completes normally   sets status "done",  stderr ""
fn() raises SystemExit 0  sets status "done"
fn() raises SystemExit N  sets status "failed", stderr "SystemExit(N)"
fn() raises CalledProcessError  sets status "failed", stderr includes cmd + traceback
fn() raises anything else sets status "failed", stderr full traceback
```

Jobs are stored in an in-memory dict (`jobs: dict[str, dict]`) — they are lost on server restart.

Each job record:
```json
{
  "job_id":     "<uuid4>",
  "status":     "pending | running | done | failed",
  "stdout":     "<captured print output>",
  "stderr":     "<error detail or empty string>",
  "created_at": "<ISO 8601 UTC timestamp>"
}
```

---

## Pydantic models

### `PreRequest`
Drives `_run_pre_sync` → `run_state_filter` + `run_crop_normalizer`.

| Field | Type | Default | Purpose |
|---|---|---|---|
| `input` | str | required | Raw CSV path (relative to `app-data/`) |
| `state` | str | required | State name to filter rows |
| `crops` | list[str] | required | Crops to retain after normalisation |
| `output` | str | required | Normalised CSV output path |
| `keep_intermediate` | bool | `true` | Retain the state-filtered intermediate file |

### `PipelineRequest`
Drives `_run_pipeline_sync` — full per-crop clustering pipeline.

| Field | Type | Default | Purpose |
|---|---|---|---|
| `raw_file` | str | required | Normalised CSV (output of pre-pipeline) |
| `crop` | str | required | Single crop to process |
| `output_dir` | str | `"outputs/repair"` | Base output dir |
| `model` | str | `"../models/qwen2.5-7b-instruct"` | LLM path/name |
| `api_key` | str | `null` | Key for remote model |
| `gpu_id` | int | `0` | CUDA device index |
| `batch_size` | int | `8` | Inference batch size |
| `grid_mode` | str | `"medium"` | Grid search intensity: `quick`/`medium`/`full` |
| `skip_phase1` | bool | `false` | Load candidates from disk instead of generating |
| `skip_phase2` | bool | `false` | Load best config from disk instead of grid search |
| `skip_repair` | bool | `false` | Skip cluster repair step |
| `skip_unique_q` | bool | `false` | Skip unique-question deduplication |
| `skip_corpus_filter` | bool | `false` | Skip irrelevant-corpus filtering |
| `skip_qa_gen` | bool | `false` | Skip QA pair generation |

### `PostRequest`
Drives `_run_post_sync` → `run_collect` + `run_dedup`.

| Field | Type | Default | Purpose |
|---|---|---|---|
| `input` | str | `"outputs/repair"` | Dir containing per-crop subdirectories |
| `skip_collect` | bool | `false` | Skip collect step (requires `final/` to exist) |
| `skip_dedup` | bool | `false` | Skip LLM deduplication |

### `FullRequest`
Drives `_run_full_sync` — pre → per-crop pipeline × N → post, all in one job.

| Field | Type | Default | Purpose |
|---|---|---|---|
| `raw_file` | str | required | Raw input CSV |
| `state` | str | required | State to filter |
| `crops` | list[str] | `null` | Inline crop list (required if `crops_file` absent) |
| `crops_file` | str | `null` | Path to plain-text crop list (required if `crops` absent) |
| `output_dir` | str | `"outputs/repair"` | Base output dir |
| `model` | str | `"../models/qwen2.5-7b-instruct"` | LLM path/name |
| `api_key` | str | `null` | Key for remote model |
| `gpu_id` | int | `1` | CUDA device index |
| `batch_size` | int | `8` | Inference batch size |
| `grid_mode` | str | `"quick"` | Grid search intensity |
| `skip_pre_pipeline` | bool | `false` | Use `raw_file` as-is, skip state filter + normalisation |
| `skip_qa_gen` | bool | `false` | Skip QA generation for all crops |
| `skip_post_pipeline` | bool | `false` | Skip final collect + dedup |

Validation: exactly one of `crops` or `crops_file` must be provided (`model_validator`).

---

## Sync wrappers

Each wrapper is imported and called inside a `ThreadPoolExecutor` thread.

### `_run_pre_sync(r: PreRequest)`
1. Resolves and validates `r.input` and `r.output` via `_resolve_safe`
2. Calls `run_state_filter(input_path, r.state, intermediate)` — filters rows by state
3. Calls `run_crop_normalizer(intermediate, output_path, r.crops)` — normalises crop names
4. Deletes `intermediate` if `keep_intermediate=False`

Imports: `run_pre_pipeline.run_state_filter`, `run_pre_pipeline.run_crop_normalizer`

### `_run_pipeline_sync(r: PipelineRequest)`
Builds an `argparse.Namespace` from the request and runs:
1. `run_phase1` — generates FAQ cluster candidates
2. `run_phase2` — grid search for best clustering config
3. `run_repair` — repairs low-quality clusters
4. `run_unique_questions` — deduplicates questions within a crop
5. `run_dedup` — cross-cluster deduplication
6. `run_corpus_filter` — removes questions matching irrelevant corpus
7. `run_qa_gen` — generates final QA pairs

Each step can be skipped individually via `skip_*` flags; skipped steps load their outputs from disk.

Hardcoded args (not exposed to user): `max_queries=20000`, `phase2_top_k=5`, `coverage_cap=0.80`, `diverse_k=3`, `coherence_flag='C'`, `merge_sim=0.82`, `fuzz_threshold=100`.

Imports: `run_pipeline.*`

### `_run_post_sync(r: PostRequest)`
1. Resolves `r.input` via `_resolve_safe`
2. Calls `run_collect(input_dir)` — gathers per-crop final files into `final/`
3. Calls `run_dedup(final_dir)` — LLM-based cross-crop deduplication

Imports: `run_post_pipeline.run_collect`, `run_post_pipeline.run_dedup`

### `_run_full_sync(r: FullRequest)`
Combines all three stages in sequence:
1. **Pre**: state filter + crop normalisation (unless `skip_pre_pipeline`)
2. **Per-crop loop**: runs all 7 pipeline phases for each crop; failures are caught per-crop and collected — remaining crops continue
3. **Post**: collect + dedup (unless `skip_post_pipeline`)

If any crops fail, raises `RuntimeError` at the end listing them (marks job `"failed"`).

---

## Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/` | — | Health check |
| POST | `/run/pre` | — | Submit pre-pipeline job |
| POST | `/run/pipeline` | — | Submit single-crop pipeline job |
| POST | `/run/post` | — | Submit post-pipeline job |
| POST | `/run/full` | — | Submit full end-to-end job |
| GET | `/jobs` | — | List all jobs |
| GET | `/jobs/{job_id}` | — | Get one job (404 if not found) |
| GET | `/files/tree` | — | Curated directory structure (all_csvs, crop_qa_files, final_csvs) |
| GET | `/files/download/{path}` | — | Download any file by relative path inside `app-data/` |

---

## Error handling matrix

| Exception type | Job status | `stderr` content |
|---|---|---|
| No exception | `done` | `""` |
| `SystemExit(0)` | `done` | `"SystemExit(0): 0"` |
| `SystemExit(N)` | `failed` | `"SystemExit(N): N"` |
| `subprocess.CalledProcessError` | `failed` | returncode + cmd + full traceback |
| Any other `Exception` | `failed` | full traceback |

HTTP 422 is returned synchronously (before job creation) for:
- Invalid path fields (absolute, `..`, null bytes, escaping sandbox)
- Missing required fields
- `FullRequest` with neither `crops` nor `crops_file`
