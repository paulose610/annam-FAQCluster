# Pipeline Server

The pipeline server is a **FastAPI** application that orchestrates all pipeline runs, manages files, and exposes the REST API consumed by the React frontend. All pipeline logic (pre, main, post) lives inside `pipeline_server/`.

**Entry point**: `pipeline_server/pipeline_server.py`
**Default port**: `7000`

```bash
cd pipeline_server
uvicorn pipeline_server:app --host 0.0.0.0 --port 7000
```

---

## File Structure

```
pipeline_server/
├── pipeline_server.py     # FastAPI app — all routes in a single file
├── _job_ctl.py            # Shared process registration and cancellation
├── pipeline/              # Core clustering and LLM stages (1–7)
├── pre_pipeline/          # State filter + crop normalization
├── post_pipeline/         # LLM deduplication + final output
├── run_pipeline.py        # Per-crop subprocess entry point
├── run_pre_pipeline.py    # Pre-pipeline CLI entry point
├── run_post_pipeline.py   # Post-pipeline CLI entry point
├── run_full.py            # End-to-end orchestrator
├── config/
│   └── irrelevant_corpus.yaml
├── crops.yaml
└── Dockerfile
```

---

## Route Summary

### Health & App Utilities

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Health check — returns `{"status": "ok"}` |
| `/app/tree` | GET | Full FAQ file tree (outputs + app-data) |
| `/app/next-state` | GET | Get next versioned state folder name |
| `/app/state-table` | GET | Summary table of state/crop outputs |
| `/app/output/{state}/{crop}` | GET | Download final output CSV for a state/crop |

### Pipeline Runs

| Endpoint | Method | Description |
|---|---|---|
| `/run/pre` | POST | State filter → crop normalize |
| `/run/pipeline` | POST | Per-crop 7-stage pipeline (one subprocess per crop) |
| `/run/post` | POST | LLM deduplication + final CSV |
| `/run/full` | POST | Pre → pipeline per crop → post (end-to-end) |

### File Management

| Endpoint | Method | Description |
|---|---|---|
| `/files/tree` | GET | Filtered view of app-data and outputs |
| `/files/download/{path}` | GET | Stream file as download |
| `/files/upload` | POST | Upload single file |
| `/files/upload-chunk` | POST | Chunked upload (for large files) |
| `/files/rename/{path}` | POST | Rename / move file |
| `/files/{path}` | DELETE | Delete file |
| `/folders/{path}` | DELETE | Delete folder tree |
| `/files/folders` | POST | Create directory |
| `/files/upload-audited` | POST | Upload manually audited FAQ replacement |

### Job Control

| Endpoint | Method | Description |
|---|---|---|
| `/jobs` | GET | List all jobs (id, status, summary) |
| `/jobs/{job_id}` | GET | Full job details including stdout/stderr |
| `/jobs/{job_id}/stop` | POST | Set cancellation flag; subprocess exits on next poll |
| `/jobs/{job_id}` | DELETE | Remove job from history |

---

## Request Models

### `PreRequest`

```
state: str              # e.g. "Karnataka"
crops: list[str]        # e.g. ["Cotton", "Sugarcane"]
domains: list[str]      # QueryType filter values (optional)
output: str             # Output CSV path (relative to app-data/)
keep_intermediate: bool
```

### `PipelineRequest`

```
input: str              # Normalized CSV path (relative to app-data/)
crops: list[str]
domains: list[str]
output_dir: str
model: str              # HuggingFace model ID or path
api_key: str            # Anthropic API key (optional)
batch_size: int
grid_mode: str          # "quick" | "medium" | "full" | "exhaustive"
skip_phase1: bool
skip_phase2: bool
skip_repair: bool
skip_unique: bool
skip_dedup: bool
skip_filter: bool
skip_qa: bool
```

### `PostRequest`

```
input: str              # State-level output directory
crops: list[str]        # Optional crop filter
skip_dedup: bool
```

### `FullRequest`

Union of Pre + Pipeline + Post parameters.

---

## Job Lifecycle

All pipeline runs execute as background jobs via `asyncio` + `ThreadPoolExecutor`. Each job has:

| Field | Values |
|---|---|
| `job_id` | UUID string |
| `job_type` | `"pre"` / `"pipeline"` / `"post"` / `"full"` |
| `status` | `"pending"` → `"running"` → `"done"` / `"failed"` / `"stopped"` |
| `stdout` | Captured print() output, streamed line-by-line |
| `stderr` | Captured error output |

**Key internals**:
- `_run_job(job_id, fn)`: Wraps a sync function, captures `sys.stdout`, updates status on completion or error.
- `_submit(fn, background, job_type)`: Submits job to `ThreadPoolExecutor`, returns `{job_id}` immediately.

---

## Pipeline Sync Functions

### `_run_pipeline_sync(r: PipelineRequest)`

- Auto-discovers crops from the CSV if none specified.
- Spawns each crop as a separate subprocess via `subprocess.Popen` with a new process group so the whole group can be killed on cancellation.
- Polls `_job_ctl.check_cancel()` between crops and during stdout streaming.
- Streams subprocess stdout/stderr line-by-line into the job log.

### `_run_full_sync(r: FullRequest)`

- Smart caching: if a normalized CSV already exists for the same state and domains, re-uses it instead of re-running the pre-pipeline.
- When appending new crops, extends the existing normalized CSV rather than overwriting it.
- Runs pre → pipeline (per crop) → post in sequence.

---

## File Management

All paths are validated against `APP_DATA` or `OUTPUTS_DIR` using `_resolve_safe()` / `_resolve_any_safe()` to prevent directory traversal.

**Chunked upload flow**:
1. Client splits file into ≤ 800 KB chunks.
2. Each chunk POSTed to `/files/upload-chunk` with `chunk_index`, `total_chunks`, `upload_id` (UUID).
3. Chunks stored temporarily; on the last chunk, reassembled and moved to destination.

**`/files/tree` response shape**:
```json
{
  "files": [...],
  "directories": [...]
}
```

**`/app/state-table` response**: lists all state/crop pairs found under `outputs/repair/`, with `meta.json` status for each.

---

## Cancellation

Cancellation works via `_job_ctl`:
- `POST /jobs/{job_id}/stop` sets a cancellation flag.
- `_run_pipeline_sync()` checks `_job_ctl.check_cancel()` between crop subprocesses.
- The running subprocess receives `SIGTERM` via `os.killpg(pgid, signal.SIGTERM)`.

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `APP_DATA_DIR` | `<pipeline_server>/app-data/` | User upload/download directory |
| `CUDA_VISIBLE_DEVICES` | `0` | GPU index |
