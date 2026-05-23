# Architecture Overview

## System Components

```
┌─────────────────────────────────────────────────────────────────────┐
│                   FRONTEND CONTAINER (port 8030)                     │
│                                                                       │
│  React + Vite SPA (served by nginx)                                  │
│   FunctionsPanel  │  PopTranslationPanel  │  Job Monitor             │
│                                                                       │
│  FAQ calls  → FAQ_API_URL  (http://<pipeline-tailscale-ip>:7000)    │
│  POP calls  → POP_API_URL  (http://<pop-server-tailscale-ip>:8000)  │
└──────────────────┬────────────────────────┬────────────────────────-─┘
                   │ HTTP                   │ HTTP
                   ▼                        ▼
┌──────────────────────────────┐    ┌──────────────────────────────┐
│  PIPELINE CONTAINER          │    │  POP SERVER (planned)         │
│  (port 7000, host network)   │    │  (port 8000, separate VM)     │
│                               │    │                               │
│  pipeline_server.py (FastAPI) │    │  /run/pop   /pop/states       │
│   /run/pre  /run/pipeline     │    │  /pop/crops /pop/docs         │
│   /run/post /run/full         │    │  /pop/upload /pop/download    │
│   /files/*  /jobs/*           │    │  (see pop_translation.md)     │
│   /app/*                      │    └──────────────────────────────┘
│                               │
│  pipeline/     (Stages 1–7)   │
│  pre_pipeline/ (state filter) │
│  post_pipeline/(LLM dedup)    │
│  run_pipeline.py  (subprocess)│
│  Qwen-7B / vLLM / HDBSCAN    │
└──────────────────────────────┘
```

---

## Data Flow

### Full FAQ Pipeline

```
Raw KCC CSV  (app-data/cleaned_data.csv)
       │
       ▼
[Pre-Pipeline]  pipeline_server/run_pre_pipeline.py
  1. State filter      → filter rows by state (e.g. Karnataka)
  2. Crop normalizer   → map crop name variants to canonical names
       │
       ▼
Normalized CSV  (e.g. app-data/karnataka_norm.csv)
       │
       ├──────────────────────────────┐
       ▼                              ▼
[Pipeline: crop=Cotton]     [Pipeline: crop=Sugarcane]   ...
  pipeline_server/run_pipeline.py (×N crops, sequential)
  Stage 1: Hyperparameter screening (HDBSCAN/UMAP grid)
  Stage 2: LLM evaluation of top configs
  Stage 3: Cluster repair (5 sub-steps)
  Stage 4: Unique question extraction
  Stage 5: Deduplication
  Stage 6: Irrelevant corpus filtering
  Stage 7: Q&A generation (vLLM)
       │
       ▼
Per-crop outputs/ (Docker volume)
  outputs/repair/<state>/<crop>/unique_questions_freq_qa.csv
       │
       ▼
[Post-Pipeline]  pipeline_server/run_post_pipeline.py
  LLM deduplication across questions within each crop
       │
       ▼
outputs/repair/<state>/<crop>/<state>_<crop>.csv
```

### POP-Translation Flow (separate server)

```
Source PDF  (POP_Work/Data/<State>/<Crop>/example.pdf)
       │
       ▼
[POP Server]  run_pop_to_docx.py  (separate VM)
  1. Split PDF into per-page PDFs
  2. Translate each page via Gemini API (parallel)
  3. Extract images from original pages
  4. Inject images into translated HTML
  5. Merge all page HTMLs
  6. Convert HTML → DOCX via Pandoc
       │
       ▼
Output DOCX  (POP_Work/Workdir/<State>/<Crop>/<doc>/final_output/<doc>_translated.docx)
```

---

## Component Connections

### Pipeline Server ↔ Entry Points

| Pipeline server call | Entry point / module called |
|---|---|
| `_run_pre_sync()` | `pre_pipeline/get_state_crop_rows.py` then `pre_pipeline/crop_normalizer.py` (direct function call) |
| `_run_pipeline_sync()` | `run_pipeline.py` launched as subprocess per crop |
| `_run_post_sync()` | `run_post_pipeline.py` called as module function |
| `_run_full_sync()` | All three above, in sequence |

### Frontend ↔ Pipeline Server

| Frontend action | API call | Pipeline server handler |
|---|---|---|
| Upload raw CSV | `POST /files/upload` | file saved to `app-data/` |
| Start full run | `POST /run/full` | `_run_full_sync()` |
| Monitor job | `GET /jobs/{id}` | job state (stdout, status) |
| Download result | `GET /app/output/{state}/{crop}` | streams from `outputs/` |

### Frontend ↔ POP Server

| Frontend action | API call |
|---|---|
| List states | `GET /pop/states` |
| Start translation | `POST /run/pop` |
| Download DOCX | `GET /pop/download/{path}` |

### Configuration Files

| File | Used by | Purpose |
|---|---|---|
| `pipeline_server/config/irrelevant_corpus.yaml` | `pipeline/filter_faq_corpus.py` (Stage 6) | Keywords to filter off-topic queries |
| `pipeline_server/crops.yaml` | `pipeline/filter_faq_corpus.py` | Cross-crop exclusion keywords |
| `pipeline_server/pre_pipeline/mapping.py` | `pre_pipeline/crop_normalizer.py` | Crop name variant → canonical name |

---

## Output Directory Structure

```
outputs/                      (Docker named volume, shared across restarts)
└── repair/
    └── <state_slug>/           (e.g. karnataka_norm)
        └── <crop_slug>/        (e.g. cotton)
            ├── phase1_results.pkl
            ├── phase1_candidates.csv
            ├── phase2_scores.csv
            ├── cluster_questions.csv
            ├── unique_q_id_to_raw_rows.csv
            ├── unique_question_mapping.csv
            ├── unique_questions_freq.csv
            ├── unique_questions_freq_qa.csv     ← primary FAQ output
            ├── corpus_filtered_out.csv
            ├── phase_data_faq.csv               ← post-pipeline log
            ├── <state>_<crop>.csv               ← final deduplicated FAQ
            └── meta.json                         ← UI tracking metadata
```

---

## Container Boundaries

| Code | Pipeline container | Frontend container | POP server (planned) |
|---|---|---|---|
| `pipeline_server/pipeline_server.py` | ✓ | | |
| `pipeline_server/pipeline/` | ✓ | | |
| `pipeline_server/pre_pipeline/` | ✓ | | |
| `pipeline_server/post_pipeline/` | ✓ | | |
| `pipeline_server/run_*.py` | ✓ | | |
| `pipeline_server/_job_ctl.py` | ✓ | | |
| `pipeline_server/config/` | ✓ | | |
| `frontend/dist/` (built) | | ✓ | |
| POP-Translation scripts | | | ✓ |
| POP_Work/ | | | ✓ |

**Docker volumes:** `app-data` and `outputs` are named volumes attached to the pipeline container and persist across restarts.

---

## Technology Stack

| Layer | Technology | Role |
|---|---|---|
| Pipeline API | FastAPI, Pydantic, asyncio | REST API + async job management |
| Frontend | React 18, Vite, nginx | User interface, static serving |
| Clustering | HDBSCAN, UMAP | Unsupervised query clustering |
| Embeddings | sentence-transformers (multilingual MPNET) | Semantic similarity |
| Local LLM | HuggingFace transformers, vLLM, Qwen-2.5-7B | Cluster repair and Q&A gen |
| Cloud LLM | Anthropic Claude Haiku, Google Gemma-4-26B | Unique question extraction, dedup |
| POP Translation | Google Gemini API, Pandoc, pdf2image | PDF → DOCX translation (separate server) |
| Data | Pandas, scikit-learn | CSV manipulation and ML utilities |
| Networking | Tailscale | Cross-VM service discovery |
