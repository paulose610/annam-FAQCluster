# FAQCluster API Usage

Start the server:
```bash
uvicorn app:app --host 0.0.0.0 --port 6100
```

Base URL: `http://localhost:6100`

---

## Health check

```
GET /
```
Returns `{"status": "ok"}`.

---

## Pipeline endpoints

All four `/run/*` endpoints are **asynchronous** — they return a `job_id` immediately and run the work in the background.

```json
{ "job_id": "<uuid>", "status": "pending" }
```

Use the [Job endpoints](#job-endpoints) to poll for completion.

---

### Pre-pipeline — `POST /run/pre`

Filters a raw CSV to a single state and normalises crop names.

```json
{
  "input":            "data/raw.csv",
  "state":            "Maharashtra",
  "crops":            ["wheat", "rice", "sugarcane"],
  "output":           "data/maharashtra_norm.csv",
  "keep_intermediate": true
}
```

| Field | Type | Default | Description |
|---|---|---|---|
| `input` | string | required | Path to raw input CSV |
| `state` | string | required | State name to filter rows by |
| `crops` | list[str] | required | Crop names to retain/normalise |
| `output` | string | required | Path for the normalised output CSV |
| `keep_intermediate` | bool | `true` | Keep the state-filtered file before crop normalisation |

---

### Pipeline (single crop) — `POST /run/pipeline`

Runs the full clustering pipeline for one crop.

```json
{
  "raw_file":   "data/maharashtra_norm.csv",
  "crop":       "wheat",
  "output_dir": "outputs/repair",
  "model":      "../models/qwen2.5-7b-instruct",
  "gpu_id":     0,
  "batch_size": 8,
  "grid_mode":  "medium"
}
```

| Field | Type | Default | Description |
|---|---|---|---|
| `raw_file` | string | required | Normalised CSV (output of `/run/pre`) |
| `crop` | string | required | Crop to process |
| `output_dir` | string | `"outputs/repair"` | Base output directory |
| `model` | string | `"../models/qwen2.5-7b-instruct"` | Model path or name |
| `api_key` | string | `null` | API key if using a remote model |
| `gpu_id` | int | `0` | GPU device index |
| `batch_size` | int | `8` | Inference batch size |
| `grid_mode` | string | `"medium"` | Hyperparameter search intensity (`quick`/`medium`/`full`) |
| `skip_phase1` | bool | `false` | Skip candidate generation (load from disk) |
| `skip_phase2` | bool | `false` | Skip grid search (load best config from disk) |
| `skip_repair` | bool | `false` | Skip cluster repair |
| `skip_unique_q` | bool | `false` | Skip unique-question dedup |
| `skip_corpus_filter` | bool | `false` | Skip corpus-based filtering |
| `skip_qa_gen` | bool | `false` | Skip QA pair generation |

---

### Post-pipeline — `POST /run/post`

Collects and deduplicates results across all crop output directories.

```json
{
  "input":        "outputs/repair",
  "skip_collect": false,
  "skip_dedup":   false
}
```

| Field | Type | Default | Description |
|---|---|---|---|
| `input` | string | `"outputs/repair"` | Directory containing per-crop subdirectories |
| `skip_collect` | bool | `false` | Skip collecting into `final/`; requires `final/` to already exist |
| `skip_dedup` | bool | `false` | Skip deduplication of collected results |

---

### Full pipeline — `POST /run/full`

Runs pre → per-crop pipeline → post in a single job. Crops can be given inline or via a file.

```json
{
  "raw_file":   "data/raw.csv",
  "state":      "Maharashtra",
  "crops":      ["wheat", "rice"],
  "output_dir": "outputs/repair",
  "model":      "../models/qwen2.5-7b-instruct",
  "gpu_id":     1,
  "batch_size": 8,
  "grid_mode":  "quick"
}
```

Or pass a text file of crop names instead of the inline list:

```json
{
  "raw_file":   "data/raw.csv",
  "state":      "Maharashtra",
  "crops_file": "crops.txt",
  ...
}
```

`crops.txt` — one crop per line, `#` lines ignored.

| Field | Type | Default | Description |
|---|---|---|---|
| `raw_file` | string | required | Path to raw input CSV |
| `state` | string | required | State to filter |
| `crops` | list[str] | — | Inline crop list (required if `crops_file` not given) |
| `crops_file` | string | — | Path to plain-text crop list (required if `crops` not given) |
| `output_dir` | string | `"outputs/repair"` | Base output directory |
| `model` | string | `"../models/qwen2.5-7b-instruct"` | Model path or name |
| `api_key` | string | `null` | API key for remote model |
| `gpu_id` | int | `1` | GPU device index |
| `batch_size` | int | `8` | Inference batch size |
| `grid_mode` | string | `"quick"` | Grid search intensity |
| `skip_pre_pipeline` | bool | `false` | Skip state filter + crop normalisation; use `raw_file` as-is |
| `skip_qa_gen` | bool | `false` | Skip QA generation for every crop |
| `skip_post_pipeline` | bool | `false` | Skip final collect + dedup |

If any individual crop fails, the rest continue. A `RuntimeError` is raised at the end listing the failed crops, which marks the job `"failed"`.

---

## Job endpoints

### List all jobs — `GET /jobs`

Returns an array of all job records.

### Get one job — `GET /jobs/{job_id}`

```json
{
  "job_id":     "3f2a...",
  "status":     "running",
  "stdout":     "Phase 1 complete...",
  "stderr":     "",
  "created_at": "2026-05-11T10:00:00+00:00"
}
```

`status` values: `pending` → `running` → `done` | `failed`

---

## File endpoints

### Directory tree — `GET /files/tree`

Returns a curated view of `app-data/` with three sections:

- `all_csvs` — every CSV except under `outputs/repair/` and `final/`
- `crop_qa_files` — `unique_questions_freq_qa.csv` per crop, with `crop` and `state` fields
- `final_csvs` — every CSV under `final/{state}/`, with a `state` field

Each entry has `name`, `path` (relative to `app-data/`), and `size`. Use `path` with the download endpoint below.

### Download a file — `GET /files/download/{path}`

Streams any file by its path relative to `app-data/`. Use the `path` field from `/files/tree` directly.

```
GET /files/download/data/raw.csv
GET /files/download/outputs/repair/punjab/maize/unique_questions_freq_qa.csv
GET /files/download/final/punjab/final_qa.csv
```

Returns 404 if not found, 400 if the path escapes `app-data/`.

---

## Typical workflow

```
POST /run/full          # kick off everything for a state
→ { "job_id": "abc" }

GET /jobs/abc           # poll until status == "done" or "failed"

GET /files/tree         # browse curated results
GET /files/download/outputs/repair/wheat/unique_questions_freq_qa.csv   # download
```
