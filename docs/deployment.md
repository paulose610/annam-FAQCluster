# Deployment

FAQCluster is deployed as two Docker containers orchestrated by Docker Compose.

---

## Container Overview

| Image | Role | Exposed port |
|---|---|---|
| `vicharanashala/faqcluster-webapp` | FastAPI API + React UI + POP-Translation | `8030` (public) |
| `vicharanashala/faqcluster-pipeline` | ML pipeline HTTP service | `7000` (internal only) |

Port `7000` is **never opened on the host machine** — it is only reachable between the two containers on Docker's internal network. The only port you need to open in the VM's firewall is `8030`.

---

## Prerequisites (production VM)

```bash
# Docker Engine
curl -fsSL https://get.docker.com | sh

# Docker Compose plugin
sudo apt-get install -y docker-compose-plugin

# NVIDIA Container Toolkit (only if GPU available)
distribution=$(. /etc/os-release; echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/libnvidia-container/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list \
  | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker
```

---

## Deploying

Copy `docker-compose.yml` to the production VM (no source code needed):

```bash
scp docker-compose.yml user@prod-vm:~/faqcluster/
```

On the VM:

```bash
cd ~/faqcluster
docker compose pull          # pull latest images from DockerHub
docker compose up -d         # start both containers in background
```

Access the UI at `http://<vm-ip>:8030`.

---

## Updating to a new version

```bash
docker compose pull
docker compose up -d --force-recreate
```

Data volumes (`app-data`, `outputs`, `pop-work`) persist across updates automatically.

---

## Environment Variables

All env vars are set in `docker-compose.yml`. You can override them at runtime:

```bash
PIPELINE_API_URL=http://pipeline:7000 docker compose up
```

| Variable | Default | Description |
|---|---|---|
| `PIPELINE_API_URL` | `http://pipeline:7000` | URL the webapp uses to reach the pipeline container |
| `POP_WORK_DIR` | `/app/POP_Work` | POP translation working directory inside the webapp container |
| `CUDA_VISIBLE_DEVICES` | `0` | GPU index for the pipeline container |

---

## Changing the public port

If port `8030` is taken on the VM, change the `ports` mapping in `docker-compose.yml`:

```yaml
ports:
  - "9090:8030"   # expose on VM port 9090 instead
```

The internal port `8030` never changes — only the host-side binding does.

---

## Persistent Data

Three named Docker volumes store data across container restarts and image updates:

| Volume | Mounted at | Contents |
|---|---|---|
| `app-data` | `/app/app-data` | Uploaded CSVs, normalised data |
| `outputs` | `/app/outputs` | Pipeline results, FAQ CSVs |
| `pop-work` | `/app/POP_Work` | POP PDF uploads and translation outputs |

To back up data:
```bash
docker run --rm \
  -v faqcluster_outputs:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/outputs-backup.tar.gz /data
```

---

## GitHub Actions CI/CD

Two workflows in `.github/workflows/` automatically build and push images on every push to `main`:

| Workflow | Triggers on changes to | Image pushed |
|---|---|---|
| `build-webapp.yml` | `backend/`, `frontend/`, `POP-Translation/`, `pre_pipeline/`, `post_pipeline/`, `Dockerfile.webapp` | `vicharanashala/faqcluster-webapp` |
| `build-pipeline.yml` | `pipeline/`, `run_pipeline.py`, `pipeline_server.py`, `Dockerfile.pipeline` | `vicharanashala/faqcluster-pipeline` |

### GitHub Secrets required

Add these two secrets to the repository (`Settings → Secrets and variables → Actions`):

| Secret | Value |
|---|---|
| `DOCKERHUB_USERNAME` | DockerHub username for the Vicharana Shala organisation |
| `DOCKERHUB_TOKEN` | DockerHub access token (generate at hub.docker.com → Account Settings → Security) |

Once the secrets are set, any push to `main` that touches the relevant files will automatically build and push the updated image. The production VM just needs `docker compose pull && docker compose up -d` to pick up the new image.

---

## Running without GPU

If the production VM has no GPU, remove the `deploy.resources` block from `docker-compose.yml`:

```yaml
  pipeline:
    image: vicharanashala/faqcluster-pipeline:latest
    expose: ["7000"]
    environment:
      - CUDA_VISIBLE_DEVICES=""
    volumes:
      - app-data:/app/app-data
      - outputs:/app/outputs
    # deploy.resources block removed
```

The pipeline will run on CPU (significantly slower for large datasets).

---

## Local development (no Docker)

```bash
# Backend + frontend dev server
cd backend && uvicorn main:app --host 0.0.0.0 --port 8030 &
cd frontend && npm run dev          # proxies API calls to localhost:8030

# Pipeline (in same Python env, no PIPELINE_API_URL needed)
python run_pipeline.py --raw-file app-data/data.csv --crop Cotton --model ...
```
