# FAQCluster Documentation

FAQCluster is an end-to-end FAQ generation system for agricultural knowledge data (KCC — Krishak Call Center). It transforms raw agricultural queries into structured, deduplicated FAQ sets with Q&A pairs. A POP-Translation module handles translating agricultural PDF documents (Package of Practices) to English.

---

## Documentation Index

| Document | Contents |
|----------|----------|
| [Architecture Overview](architecture.md) | System design, data flow, container boundaries |
| [Deployment](deployment.md) | Docker Compose setup, GitHub Actions CI/CD, production VM setup |
| [Backend](backend.md) | FastAPI server, routes, job management, file handling |
| [Frontend](frontend.md) | React UI, API client, component structure |
| [Pipeline](pipeline.md) | 7-stage FAQ generation pipeline |
| [Pre-Pipeline](pre_pipeline.md) | State filtering and crop normalization |
| [Post-Pipeline](post_pipeline.md) | LLM-based deduplication and final output |
| [POP-Translation](pop_translation.md) | Agricultural PDF translation using Gemini (part of web app) |
| [Entry Points](entry_points.md) | `run_full.py`, `run_pipeline.py`, `run_pre_pipeline.py`, `run_post_pipeline.py` |

---

## Quick Start

### Production (Docker)

```bash
# On the production VM — only docker-compose.yml needed, no source code
docker compose pull
docker compose up -d
# UI available at http://<vm-ip>:8030
```

See [Deployment](deployment.md) for full setup instructions including GPU, secrets, and CI/CD.

### Local Development (no Docker)

```bash
# Start backend
cd backend && uvicorn main:app --host 0.0.0.0 --port 8030

# Start frontend (separate terminal)
cd frontend && npm run dev
```

---

## Project Structure

```
FAQCluster/
├── app-data/              # User input/output storage
├── backend/               # FastAPI server
├── frontend/              # React + Vite UI
├── pipeline/              # Core clustering and LLM modules
├── pre_pipeline/          # State filter + crop normalization
├── post_pipeline/         # LLM deduplication + final output
├── POP-Translation/       # PDF translation pipeline
├── config/                # irrelevant_corpus.yaml, crops.yaml
├── outputs/               # Pipeline results
├── docs/                  # This documentation
├── run_full.py            # End-to-end orchestrator
├── run_pipeline.py        # Per-crop 7-stage pipeline
├── run_pre_pipeline.py    # Pre-processing entry point
├── run_post_pipeline.py   # Post-processing entry point
└── _job_ctl.py            # Process registration and cancellation
```
