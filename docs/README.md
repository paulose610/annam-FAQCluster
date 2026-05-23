# FAQCluster Documentation

FAQCluster is an end-to-end FAQ generation system for agricultural knowledge data (KCC — Krishak Call Center). It transforms raw agricultural queries into structured, deduplicated FAQ sets with Q&A pairs. A separate POP-Translation server (planned) handles translating agricultural PDF documents (Package of Practices) to English.

---

## Documentation Index

| Document | Contents |
|----------|----------|
| [Architecture Overview](architecture.md) | System design, data flow, container boundaries |
| [Deployment](deployment.md) | Docker Compose setup, GitHub Actions CI/CD, production VM setup |
| [Pipeline Server](backend.md) | FastAPI server (`pipeline_server.py`), routes, job management, file handling |
| [Frontend](frontend.md) | React UI, API client, component structure |
| [Pipeline](pipeline.md) | 7-stage FAQ generation pipeline |
| [Pre-Pipeline](pre_pipeline.md) | State filtering and crop normalization |
| [Post-Pipeline](post_pipeline.md) | LLM-based deduplication and final output |
| [POP-Translation](pop_translation.md) | Agricultural PDF translation — separate server spec |
| [Entry Points](entry_points.md) | `run_full.py`, `run_pipeline.py`, `run_pre_pipeline.py`, `run_post_pipeline.py` |

---

## Quick Start

### Production (Docker)

```bash
# On the production VM — only docker-compose.yml needed, no source code
# Set FAQ_API_URL and POP_API_URL in docker-compose.yml before running
docker compose pull
docker compose up -d
# UI available at http://<vm-ip>:8030
```

See [Deployment](deployment.md) for full setup instructions including GPU, Tailscale IPs, and CI/CD.

### Local Development (no Docker)

```bash
# Start pipeline server
cd pipeline_server
uvicorn pipeline_server:app --host 0.0.0.0 --port 7000

# Start frontend dev server (separate terminal)
cd frontend && npm run dev
```

---

## Project Structure

```
FAQCluster/
├── pipeline_server/       # Pipeline FastAPI server + all ML pipeline code
│   ├── pipeline_server.py     # FastAPI app (port 7000)
│   ├── pipeline/              # Core clustering and LLM modules (Stages 1–7)
│   ├── pre_pipeline/          # State filter + crop normalization
│   ├── post_pipeline/         # LLM deduplication + final output
│   ├── config/                # irrelevant_corpus.yaml
│   ├── crops.yaml             # Crop list config
│   ├── app-data/              # User input/output storage (Docker volume)
│   ├── run_full.py            # End-to-end orchestrator
│   ├── run_pipeline.py        # Per-crop 7-stage pipeline
│   ├── run_pre_pipeline.py    # Pre-processing entry point
│   ├── run_post_pipeline.py   # Post-processing entry point
│   ├── _job_ctl.py            # Process registration and cancellation
│   └── Dockerfile
├── frontend/              # React + Vite UI
│   └── Dockerfile
├── helpers/               # Standalone utility scripts (not used by server)
├── outputs/               # Pipeline results (Docker volume)
├── docs/                  # This documentation
└── docker-compose.yml
```
