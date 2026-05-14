# FAQCluster App — Documentation

## Overview

FAQCluster is a web application for generating crop-specific FAQ datasets from raw KCC (Kisan Call Centre) CSV data. It wraps a 7-stage NLP pipeline in a browser UI so you can upload data, trigger runs, monitor progress, and download results — all without touching the command line.

The app has two parts:

- **Backend** — a FastAPI server (`app.py`) that manages files, runs pipeline stages as background jobs, and exposes a REST API.
- **Frontend** — a React single-page app that talks to the backend, showing a three-column layout: file explorer on the left, pipeline controls in the centre, job monitor on the right.

---

## Starting the App

```bash
# Terminal 1 — backend (port 8000)
source venv/bin/activate
uvicorn app:app --reload --port 8000

# Terminal 2 — frontend dev server (port 5173, proxies API calls to 8000)
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173` in your browser.

For production, build the frontend (`npm run build`) and serve the `dist/` folder statically alongside the backend.

---

## File Sandbox

All file I/O is restricted to the `app-data/` directory at the project root. The backend rejects absolute paths, `..` traversal, and null bytes. The directory layout inside `app-data/` is:

```
app-data/
├── data/                          ← uploaded raw CSV files (input to pipelines)
├── outputs/
│   └── repair/
│       └── {state_slug}/          ← one folder per state (e.g. maharashtra_norm)
│           └── {crop_slug}/       ← one folder per crop (e.g. maize)
│               ├── phase1_results.pkl
│               ├── phase2_scores.csv
│               ├── repaired_clusters.csv
│               ├── unique_questions_freq.csv
│               └── unique_questions_freq_qa.csv   ← final FAQ file per crop
└── final/
    └── {state_slug}/              ← collected + deduplicated outputs (post-pipeline)
        └── *.csv
```

---

## Three-Column Layout

### Left — File Explorer

Shows all files in `app-data/` organised into three collapsible groups:

| Group | What it shows |
|-------|--------------|
| **Input CSVs** | Every CSV not inside `outputs/` or `final/` — the raw or normalised data files you upload |
| **Crop QA Files** | The final `unique_questions_freq_qa.csv` for each crop that has completed Stage 7, grouped by state folder |
| **Final CSVs** | Collected output files inside `final/{state}/` produced by Post-Pipeline |

Each file row has two icons:
- **↓** — downloads the file to your browser.
- **🗑** — permanently deletes the file from `app-data/` (cannot be undone).

The **+** button at the top opens a file-upload dialog. Files land in the root of `app-data/` by default, or in a sub-folder if you specify one.

### Centre — Pipeline Controls

Four cards, each triggering a different pipeline mode. Fill in the form fields and press **Run**. The run returns immediately with a job ID (toasted on screen); actual work happens in the background.

### Right — Job Monitor

Lists all jobs submitted in the current server session (jobs are in-memory; they reset when the server restarts). Each card shows:
- Job type (pre / pipeline / post / full) and status
- Job ID and creation time
- Click the card to expand live stdout output
- Failed jobs also show the stderr / traceback

**Filter tabs** at the top: All · Running · Done · Failed.  
The **✕** button deletes a finished or failed job from the list. Running jobs cannot be deleted (stop them first via the Stop button if one exists).

---

## Pipeline Modes

### Pre-Pipeline

**What it does:** Filters a raw KCC CSV down to a single state, then normalises crop name variants to their canonical primary names using `pre_pipeline/mapping.py`.

**When to use it:** Before running the main Pipeline when you have a raw all-India KCC CSV and need a state-specific, crop-normalised file as input.

**Fields:**

| Field | Description |
|-------|-------------|
| Input CSV | Select from uploaded CSVs in the file explorer |
| State | State name to filter rows by (e.g. `Karnataka`) |
| Crops | Select one or more canonical crop names (searchable dropdown with tags) |
| Output path | Relative path for the output file inside `app-data/` (e.g. `data/karnataka_norm.csv`) |
| Keep intermediate | If checked, the state-filtered intermediate file is kept alongside the final output |

**Output:** A normalised CSV at the path you specified, ready to feed into Pipeline or Full Pipeline.

---

### Pipeline

**What it does:** Runs the full 7-stage clustering and FAQ-generation pipeline for one or more crops against an already-normalised CSV.

**When to use it:** When you already have a normalised CSV (either from Pre-Pipeline or a previous run) and want to process specific crops.

**Fields:**

| Field | Description |
|-------|-------------|
| Raw file | Select the normalised input CSV |
| Crops | Select one or more canonical crop names — the pipeline runs each crop sequentially |
| Grid mode | How many hyperparameter combinations Stage 1 searches: Quick (18) · Medium (108) · Full (240) · Exhaustive (480). Quick is fastest; use Medium or Full for better clustering quality |
| Skip phase 1 | Re-use existing `phase1_results.pkl` instead of re-running the HP search |
| Skip phase 2 | Re-use existing `phase2_scores.csv` instead of re-running LLM evaluation |
| Skip repair | Skip cluster repair — use existing `cluster_questions.csv` |
| Skip unique-Q | Skip unique question extraction — use existing `unique_questions_freq.csv` |
| Skip corpus filter | Skip Stage 6 irrelevant query removal |
| Skip QA gen | Skip Stage 7 answer generation (saves significant GPU time) |

**Output:** For each crop, a folder at `app-data/outputs/repair/{state}/{crop}/` containing all intermediate files and the final `unique_questions_freq_qa.csv`.

**Notes:**
- Stages 1–3 and 7 require a GPU (~16 GB VRAM for Qwen2.5-7B). Stage 4 is GPU-free when an Anthropic API key is configured server-side.
- Each crop runs sequentially within a single job. If one crop fails it is logged and the job continues with the rest.
- The skip flags are useful for resuming an interrupted run — skip the stages that already produced output files.

---

### Post-Pipeline

**What it does:** Collects all per-crop `unique_questions_freq_qa.csv` files from a state folder into a single `final/` directory, then runs a cross-crop deduplication pass.

**When to use it:** After Pipeline has finished for all crops in a state and you want a unified output.

**Fields:**

| Field | Description |
|-------|-------------|
| Crop QA folder | Select the state-level repair folder (e.g. `maharashtra_norm`). Only folders that contain at least one completed crop QA file appear in the dropdown |

**Output:** `app-data/outputs/repair/{state}/final/` containing the collected and deduplicated CSVs. These also appear under **Final CSVs** in the file explorer.

---

### Full Pipeline

**What it does:** Runs Pre-Pipeline → Pipeline → Post-Pipeline in one shot. The most convenient mode for a fresh end-to-end run.

**Fields:**

| Field | Description |
|-------|-------------|
| Raw file | The raw (all-India or state) KCC CSV |
| State | State name for the pre-pipeline filter step |
| Crops | Select one or more canonical crop names |
| Grid mode | Same as Pipeline — controls HP search depth |
| Skip pre-pipeline | Skip Stage 0 and treat the raw file as already normalised |
| Skip QA gen | Skip Stage 7 answer generation for all crops |
| Skip post-pipeline | Skip the final collect + dedup step |

**Output:** Same structure as running all three modes separately.

---

## Crop Selector

Crops fields across all pipeline forms use a searchable tag-based selector:

1. **Type** a keyword in the search box — the dropdown narrows to matching canonical crop names in real time (case-insensitive substring match).
2. **Click** a crop name in the dropdown to add it.
3. Added crops appear as **tag chips** below the search box, one per line.
4. Click **×** on any tag to remove that crop.
5. You can add as many crops as needed before pressing Run.

The crop list is derived from the canonical primary names in `pre_pipeline/mapping.py` (~230 crops covering paddy, wheat, vegetables, fruits, oilseeds, fodder grasses, forestry, medicinal plants, and more).

---

## Job Lifecycle

```
pending  →  running  →  done
                     →  failed
                     →  stopped   (if cancelled by user)
```

| Status | Meaning |
|--------|---------|
| pending | Queued, waiting for the thread pool |
| running | Actively executing in a background thread |
| done | All stages completed successfully |
| failed | One or more crops errored; see stderr in the job card |
| stopped | Cancelled by the user mid-run |

Jobs are held in memory. Restarting the backend server clears all job history. The files they produced on disk are not affected.

---

## REST API Reference

The backend is auto-documented at `http://localhost:8000/docs` (Swagger UI) when running with `--reload`.

### Run endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/run/pre` | Submit a Pre-Pipeline job |
| `POST` | `/run/pipeline` | Submit a Pipeline job |
| `POST` | `/run/post` | Submit a Post-Pipeline job |
| `POST` | `/run/full` | Submit a Full Pipeline job |

All four return immediately with `{job_id, job_type, job_type_id, status: "pending"}`.

### Job endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/jobs` | List all jobs |
| `GET` | `/jobs/{job_id}` | Get a single job (includes stdout, stderr) |
| `POST` | `/jobs/{job_id}/stop` | Cancel a running job |
| `DELETE` | `/jobs/{job_id}` | Delete a finished or failed job from memory |

### File endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/files/tree` | Structured listing of `app-data/` (three sections: all_csvs, crop_qa_files, final_csvs) |
| `GET` | `/files/download/{path}` | Download a file by its relative path inside `app-data/` |
| `POST` | `/files/upload` | Upload a file; optional `dest` query param sets the sub-folder |
| `DELETE` | `/files/{path}` | Delete a file by its relative path inside `app-data/` |

### Health

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Returns `{"status": "ok"}` — use to check the server is up |

---

## Typical Workflow

### Fresh run (raw all-India CSV)

1. **Upload** your raw KCC CSV via the + button in the Files panel. It lands in `app-data/`.
2. Open **Full Pipeline**, select the CSV, enter the state name, pick crops, choose a grid mode, and press **Run**.
3. Watch the job progress in the Jobs panel — click the card to see live stdout.
4. When the job reaches **done**, the crop QA files appear under **Crop QA Files** in the Files panel.
5. Download any per-crop `unique_questions_freq_qa.csv` from there, or find the unified output under **Final CSVs**.

### Resuming an interrupted run

1. Open **Pipeline**, select the normalised CSV, pick the same crops.
2. Tick the **Skip** checkboxes for stages that already produced output files (check the crop's folder in `app-data/outputs/repair/{state}/{crop}/`).
3. Press **Run** — only the remaining stages execute.

### Post-processing only

1. If you already have per-crop QA files from a previous Pipeline run, open **Post-Pipeline**.
2. Select the state folder from the dropdown (only folders with completed QA files are shown).
3. Press **Run** — the collect and dedup steps produce the unified `final/` output.

---

## Configuration Notes

- **Model path** and **GPU ID** are fixed server-side. The frontend no longer exposes these fields; they default to `../models/qwen2.5-7b-instruct` and GPU 1 respectively. Edit the `PipelineRequest` / `FullRequest` defaults in `app.py` to change them.
- **API key** for Claude Haiku (Stage 4) is also server-side. Pass it in the `PipelineRequest` default or via an environment variable before starting the server.
- **Output directory** defaults to `outputs/repair` inside `app-data/`. This is not configurable from the UI.
- The **corpus filter** config lives in `config/irrelevant_corpus.yaml`. Add new irrelevant category blocks there without touching any code.
