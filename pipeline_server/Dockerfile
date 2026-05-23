# Pipeline container — heavy ML deps (PyTorch, vLLM, HDBSCAN, UMAP, transformers)
# Exposes the full FAQ API (pipeline_server.py) on port 8031.
FROM pytorch/pytorch:2.1.0-cuda12.1-cudnn8-runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install exact pinned deps from lock file (reproducible builds)
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock

# Copy pipeline code
COPY pipeline/            pipeline/
COPY pre_pipeline/        pre_pipeline/
COPY post_pipeline/       post_pipeline/
COPY run_pipeline.py      .
COPY run_full.py          .
COPY run_pre_pipeline.py  .
COPY run_post_pipeline.py .
COPY _job_ctl.py          .
COPY config/              config/
COPY pipeline_server.py   .

RUN mkdir -p app-data outputs

EXPOSE 8031

CMD ["uvicorn", "pipeline_server:app", "--host", "0.0.0.0", "--port", "8031"]
