# Pipeline container — heavy ML deps (PyTorch, vLLM, HDBSCAN, UMAP, transformers)
# Exposes a thin HTTP API (pipeline_server.py) for the webapp container to call.
FROM pytorch/pytorch:2.1.0-cuda12.1-cudnn8-runtime

# Build tools needed for some Python packages (hdbscan, umap)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install base pipeline requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install FastAPI + uvicorn for pipeline_server.py
RUN pip install --no-cache-dir "fastapi>=0.110.0" "uvicorn[standard]>=0.29.0" "pydantic>=2.0.0"

# Copy pipeline code
COPY pipeline/        pipeline/
COPY pre_pipeline/    pre_pipeline/
COPY post_pipeline/   post_pipeline/
COPY run_pipeline.py  .
COPY run_full.py      .
COPY run_pre_pipeline.py  .
COPY run_post_pipeline.py .
COPY _job_ctl.py          .
COPY config/              config/
COPY pipeline_server.py   .

# Create data directories (will be overridden by volumes in production)
RUN mkdir -p app-data outputs

EXPOSE 7000

CMD ["uvicorn", "pipeline_server:app", "--host", "0.0.0.0", "--port", "7000"]
