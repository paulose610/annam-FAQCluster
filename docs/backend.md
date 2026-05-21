# Backend

The backend is a **FastAPI** application that orchestrates all pipeline runs, manages files, and exposes a REST API consumed by the React frontend.

**Entry point**: `backend/main.py`
**Default port**: `6100`

```bash
cd backend
uvicorn main:app --host 0.0.0.0 --port 6100
```

---

## File Structure

```
backend/
├── main.py            # App creation, router registration, root endpoints
├── common.py          # Shared constants and path utilities
├── jobs.py            # Job lifecycle management and async executor
└── routes/
    ├── faq_cluster.py     # /run/pre, /run/pipeline, /run/post, /run/full
    ├── files.py           # /files/* — upload, download, rename, delete, tree
    ├── pop_translation.py # /pop/*, /run/pop
    └── jobs_router.py     # /jobs/*
```

---

## `main.py`

Registers all routers and exposes two utility endpoints:

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Health check — returns `{"status": "ok"}` |
| `/app/tree` | GET | Combined FAQ file tree + POP data tree |

---

## `common.py`

Shared constants used across all routes:

| Name | Default | Description |
|---|---|---|
| `ROOT_DIR` | Project root | Absolute path to `FAQCluster/` |
| `APP_DATA` | `FAQCluster/app-data/` | User upload/download directory |
| `POP_WORK_DIR` | `POP_Work/` | POP translation working directory (overridable via env var) |

**`_resolve_safe(user_path, base)`** validates that a user-supplied path stays within `base`, preventing directory traversal attacks. All file routes use this before touching the filesystem.

---

## `jobs.py` — Job Lifecycle

All pipeline runs execute as background jobs. Each job has:

| Field | Values |
|---|---|
| `status` | `pending` → `running` → `done` / `failed` / `stopped` |
| `stdout` | Captured print() output from the job |
| `stderr` | Captured error output |
| `job_id` | Integer — `1`=pre, `2`=pipeline, `3`=post, `4`=full, `5`=pop |

**Key internals**:
- `_JobStdout`: Overrides `sys.stdout` inside a job so all `print()` calls feed into the job log visible via `GET /jobs/{id}`.
- `_run_job(fn)`: Wraps a sync function, sets status to `running`, captures output, updates status on completion or error.
- `_submit(job_id, fn)`: Submits the job to a `ThreadPoolExecutor`, returns the job object immediately.

---

## `routes/faq_cluster.py` — Pipeline Routes

### Request models

**`PreRequest`**
```
state: str            # e.g. "Karnataka"
crops: list[str]      # e.g. ["Cotton", "Sugarcane"]
domains: list[str]    # QueryType filter values (optional)
output: str           # Output CSV path (relative to app-data/)
keep_intermediate: bool
```

**`PipelineRequest`**
```
input: str            # Normalized CSV path
crops: list[str]
domains: list[str]
output_dir: str
model: str            # HuggingFace model ID or path
api_key: str          # Claude/Anthropic API key (optional)
batch_size: int
grid_mode: str        # "quick" | "medium" | "full" | "exhaustive"
skip_phase1: bool
skip_phase2: bool
skip_repair: bool
skip_unique: bool
skip_dedup: bool
skip_filter: bool
skip_qa: bool
```

**`PostRequest`**
```
input: str            # State-level output directory
crops: list[str]      # Optional crop filter
skip_dedup: bool
```

**`FullRequest`** — union of Pre + Pipeline + Post params.

### Routes

| Route | Handler | Behaviour |
|---|---|---|
| `POST /run/pre` | `_run_pre_sync()` | State filter → crop normalize |
| `POST /run/pipeline` | `_run_pipeline_sync()` | One subprocess per crop |
| `POST /run/post` | `_run_post_sync()` | LLM deduplication |
| `POST /run/full` | `_run_full_sync()` | Pre → pipeline per crop → post |

**`_run_pipeline_sync()`** details:
- Auto-discovers crops from the CSV if none specified.
- Spawns each crop as a separate subprocess via `subprocess.Popen` with a new process group so the whole group can be killed on cancellation.
- Polls `_job_ctl.check_cancel()` between crops and during stdout streaming.
- Streams subprocess stdout/stderr line-by-line into the job log.

**`_run_full_sync()`** smart caching:
- If a normalized CSV already exists for the same state and domains, re-uses it instead of re-running the pre-pipeline.
- When appending new crops, extends the existing normalized CSV rather than overwriting it.

---

## `routes/files.py` — File Management

All paths are resolved relative to `APP_DATA` using `_resolve_safe()`.

| Endpoint | Method | Description |
|---|---|---|
| `/files/tree` | GET | Returns `{all_csvs, crop_qa_files, final_csvs}` |
| `/files/download/{path}` | GET | Stream file as download |
| `/files/upload` | POST | Upload single file (chunked for > 800 KB) |
| `/files/upload-chunk` | POST | Receive a chunk; assemble on last chunk |
| `/files/rename/{path}` | POST | Rename/move file |
| `/files/{path}` | DELETE | Delete file |
| `/files/folders` | POST | Create directory |
| `/files/upload-audited` | POST | Upload manually audited FAQ replacement |

**Tree response shape**:
```json
{
  "all_csvs": ["outputs/repair/karnataka_norm/cotton/cluster_questions.csv", ...],
  "crop_qa_files": ["outputs/repair/karnataka_norm/cotton/unique_questions_freq_qa.csv", ...],
  "final_csvs": ["app-data/final/karnataka/karnataka_cotton.csv", ...]
}
```

**Chunked upload flow**:
1. Client splits file into ≤ 800 KB chunks.
2. Each chunk POST to `/files/upload-chunk` with `chunk_index`, `total_chunks`, `upload_id` (UUID).
3. Chunks stored under a temp path; on `chunk_index == total_chunks - 1`, reassembled and moved to destination.

---

## `routes/pop_translation.py` — POP Routes

| Endpoint | Method | Description |
|---|---|---|
| `/pop/states` | GET | List state folders in `POP_Work/Data/` |
| `/pop/crops` | GET | List crop folders for a state |
| `/pop/docs` | GET | List PDFs for a state/crop |
| `/pop/data/tree` | GET | Recursive tree of `POP_Work/Data/` |
| `/pop/output/tree` | GET | Recursive tree of `POP_Work/Workdir/` |
| `/pop/state-table` | GET | Summary table of states and crop counts |
| `/run/pop` | POST | Start POP translation job |
| `/pop/upload` | POST | Upload POP PDF |
| `/pop/upload-chunk` | POST | Chunked upload for large PDFs |
| `/pop/download/{path}` | GET | Download file from `POP_Work/` |
| `/pop/folders` | POST | Create folder |
| `/pop/files/{path}` | DELETE | Delete file |
| `/pop/folders/{path}` | DELETE | Delete folder tree |
| `/pop/upload-audited` | POST | Upload reviewed/corrected translation |

**`/run/pop` request body**:
```
source_pdf: str       # Path relative to POP_Work/
workdir: str          # Output workdir path
doc_name: str         # Document name prefix
prompt_file: str      # Prompt template path
start_page: int
end_page: int
concurrency: int      # Parallel Gemini API calls
```

The route launches `POP-Translation/scripts/run_pop_to_docx.py` as a subprocess and captures output into job `5`.

---

## `routes/jobs_router.py` — Job Control

| Endpoint | Method | Description |
|---|---|---|
| `/jobs` | GET | List all jobs (id, status, summary) |
| `/jobs/{jobId}` | GET | Full job details including stdout/stderr |
| `/jobs/{jobId}` | DELETE | Remove job from history |
| `/jobs/{jobId}/stop` | POST | Set cancellation flag; running subprocess will exit on next poll |

Cancellation works via `_job_ctl`: the running `_run_pipeline_sync()` checks `check_cancel()` between crop subprocesses, and the subprocess itself receives `SIGTERM` via `os.killpg`.

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `POP_WORK_DIR` | `<root>/POP_Work/` | Override POP working directory |
| `APP_DATA_DIR` | `<root>/app-data/` | Override user data directory |
