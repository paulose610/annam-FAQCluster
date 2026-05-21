# Architecture Overview

## System Components

```
┌──────────────────────────────────────────────────────────────────────────┐
│                      WEBAPP CONTAINER (port 8030)                         │
│                                                                            │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │                     Frontend (React + Vite)                       │    │
│  │   FunctionsPanel  │  PopTranslationPanel  │  Job Monitor          │    │
│  └────────────────────────────┬─────────────────────────────────────┘    │
│                                │ HTTP (same container)                     │
│  ┌─────────────────────────────▼───────────────────────────────────────┐ │
│  │                      Backend (FastAPI)                               │ │
│  │   /run/*  │  /files/*  │  /jobs/*  │  /pop/*                        │ │
│  │                      jobs.py (async executor)                        │ │
│  └──────┬──────────────┬───────────────┬────────────────────────────── ┘ │
│         │              │               │                                   │
│         ▼              ▼               ▼                                   │
│   run_pre_        run_post_      POP-Translation/                          │
│   pipeline.py     pipeline.py   scripts/run_pop_to_docx.py                │
│   (subprocess)    (direct fn)   (subprocess, Gemini API)                  │
│                                                                            │
└──────────────────────┬───────────────────────────────────────────────────┘
                       │ HTTP  PIPELINE_API_URL=http://pipeline:7000
                       │ (Docker internal network only)
┌──────────────────────▼───────────────────────────────────────────────────┐
│                    PIPELINE CONTAINER (port 7000, internal)                │
│                                                                            │
│   pipeline_server.py (FastAPI)                                             │
│      POST /run/pipeline  →  run_pipeline.py (subprocess)                  │
│      GET  /jobs/{id}     →  stdout / status                                │
│                                                                            │
│   pipeline/  (HDBSCAN, UMAP, sentence-transformers, vLLM, Qwen-7B)        │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Data Flow

### Full FAQ Pipeline

```
Raw KCC CSV  (app-data/cleaned_data.csv)
       │
       ▼
[Pre-Pipeline]  run_pre_pipeline.py
  1. State filter      → filter rows by state (e.g. Karnataka)
  2. Crop normalizer   → map crop name variants to canonical names
       │
       ▼
Normalized CSV  (e.g. app-data/karnataka_norm.csv)
       │
       ├──────────────────────────────┐
       ▼                              ▼
[Pipeline: crop=Cotton]     [Pipeline: crop=Sugarcane]   ...
  run_pipeline.py (×N crops in parallel or sequence)
  Stage 1: Hyperparameter screening (HDBSCAN/UMAP grid)
  Stage 2: LLM evaluation of top configs
  Stage 3: Cluster repair (5 sub-steps)
  Stage 4: Unique question extraction
  Stage 5: Deduplication
  Stage 6: Irrelevant corpus filtering
  Stage 7: Q&A generation (vLLM)
       │
       ▼
Per-Crop outputs/repair/<state>/<crop>/
  unique_questions_freq_qa.csv   ← FAQ Q&A pairs
  unique_questions_freq.csv      ← questions only
  cluster_questions.csv          ← clustered view
       │
       ▼
[Post-Pipeline]  run_post_pipeline.py
  LLM deduplication across questions within each crop
       │
       ▼
Final FAQs
  outputs/repair/<state>/<crop>/<state>_<crop>.csv
```

### POP-Translation Flow

```
Source PDF  (POP_Work/Data/<State>/<Crop>/example.pdf)
       │
       ▼
[POP-Translation]  POP-Translation/scripts/run_pop_to_docx.py
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

### Backend ↔ Entry Points

| Backend call | Entry point / module called |
|---|---|
| `_run_pre_sync()` | `pre_pipeline/get_state_crop_rows.py` then `pre_pipeline/crop_normalizer.py` (direct function call) |
| `_run_pipeline_sync()` | `run_pipeline.py` launched as subprocess per crop |
| `_run_post_sync()` | `run_post_pipeline.py` called as module function |
| `_run_full_sync()` | All three above, in sequence |
| POP route | `POP-Translation/scripts/run_pop_to_docx.py` as subprocess |

### Frontend ↔ Backend

| Frontend action | API call | Backend handler |
|---|---|---|
| Upload raw CSV | `POST /files/upload` | `files.py` → saved to `app-data/` |
| Start full run | `POST /run/full` | `faq_cluster.py:_run_full_sync()` |
| Monitor job | `GET /jobs/{id}` | `jobs_router.py` → `jobs.py` state |
| Download result | `GET /files/download/{path}` | `files.py` → `app-data/` or `outputs/` |
| POP translation | `POST /run/pop` | `pop_translation.py:run_pop_to_docx.py` subprocess |

### Configuration Files

| File | Used by | Purpose |
|---|---|---|
| `config/irrelevant_corpus.yaml` | `pipeline/filter_faq_corpus.py` (Stage 6) | Keywords to filter off-topic queries |
| `crops.yaml` (optional) | `pipeline/filter_faq_corpus.py` | Cross-crop exclusion keywords |
| `pre_pipeline/mapping.py` | `pre_pipeline/crop_normalizer.py` | Crop name variant → canonical name |

---

## Output Directory Structure

```
outputs/
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

| Code | Webapp container | Pipeline container |
|---|---|---|
| `backend/` | ✓ | |
| `frontend/dist/` (built) | ✓ | |
| `POP-Translation/` | ✓ | |
| `pre_pipeline/` | ✓ | ✓ |
| `post_pipeline/` | ✓ | ✓ |
| `run_pre_pipeline.py` | ✓ | ✓ |
| `run_post_pipeline.py` | ✓ | ✓ |
| `pipeline_server.py` | | ✓ |
| `pipeline/` | | ✓ |
| `run_pipeline.py` | | ✓ |
| `run_full.py` | | ✓ |
| `config/` | ✓ | ✓ |
| `_job_ctl.py` | ✓ | ✓ |

**Shared at runtime (Docker named volumes):** `app-data/`, `outputs/`, `POP_Work/`

---

## Technology Stack

| Layer | Technology | Role |
|---|---|---|
| Backend | FastAPI, Pydantic, asyncio | REST API + async job management |
| Frontend | React 18, Vite, TailwindCSS | User interface |
| Clustering | HDBSCAN, UMAP | Unsupervised query clustering |
| Embeddings | sentence-transformers (multilingual MPNET) | Semantic similarity |
| Local LLM | HuggingFace transformers, vLLM, Qwen-2.5-7B | Cluster repair and Q&A gen |
| Cloud LLM | Anthropic Claude Haiku, Google Gemma-4-26B | Unique question extraction, dedup |
| POP Translation | Google Gemini API, Pandoc, pdf2image | PDF → DOCX translation |
| Data | Pandas, scikit-learn | CSV manipulation and ML utilities |
