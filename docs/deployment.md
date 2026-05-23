# Deployment

FAQCluster is deployed as two Docker containers orchestrated by Docker Compose, with a planned third container for POP-Translation running on a separate VM.

---

## Container Overview

| Image | Role | Exposed port |
|---|---|---|
| `vicharanashala/faqcluster-pipeline` | FastAPI pipeline server + ML models | `7000` (host network) |
| `vicharanashala/faqcluster-frontend` | React UI served by nginx | `8030` (public) |
| POP server *(planned)* | POP-Translation FastAPI server | `8000` (separate VM) |

The pipeline container uses `network_mode: host`, so port 7000 is accessible directly on the host. The frontend reaches the pipeline via the host's Tailscale IP. The only port that needs to be opened in the VM firewall for end users is `8030`.

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

Before deploying, set the Tailscale IPs in `docker-compose.yml`:

```yaml
environment:
  - FAQ_API_URL=http://<pipeline-tailscale-ip>:7000
  - POP_API_URL=http://<pop-server-tailscale-ip>:8000
```

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

Data volumes (`app-data`, `outputs`) persist across updates automatically.

---

## Environment Variables

Set in `docker-compose.yml`:

| Variable | Service | Description |
|---|---|---|
| `FAQ_API_URL` | `frontend` | Tailscale URL of the pipeline container (e.g. `http://100.x.x.x:7000`) |
| `POP_API_URL` | `frontend` | Tailscale URL of the POP server (e.g. `http://100.x.x.x:8000`) |
| `CUDA_VISIBLE_DEVICES` | `pipeline` | GPU index (default: `0`) |

The frontend reads `FAQ_API_URL` and `POP_API_URL` at nginx startup and injects them into the served HTML as `window.__FAQ_API_URL__` and `window.__POP_API_URL__`.

---

## Changing the public port

If port `8030` is taken, change the `ports` mapping in `docker-compose.yml`:

```yaml
ports:
  - "9090:80"   # expose on VM port 9090 instead
```

The internal nginx port (`80`) never changes — only the host-side binding does.

---

## Persistent Data

Two named Docker volumes store data across container restarts and image updates:

| Volume | Mounted at (pipeline container) | Contents |
|---|---|---|
| `app-data` | `/app/app-data` | Uploaded CSVs, normalised data |
| `outputs` | `/app/outputs` | Pipeline results, FAQ CSVs |

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
| `build-pipeline.yml` | `pipeline_server/**` | `vicharanashala/faqcluster-pipeline` |
| `build-frontend.yml` | `frontend/**` | `vicharanashala/faqcluster-frontend` |

### GitHub Secrets required

| Secret | Value |
|---|---|
| `DOCKERHUB_USERNAME` | DockerHub username for the Vicharana Shala organisation |
| `DOCKERHUB_TOKEN` | DockerHub access token (generate at hub.docker.com → Account Settings → Security) |

Once the secrets are set, any push to `main` touching the relevant paths will automatically build and push the updated image. The production VM just needs `docker compose pull && docker compose up -d` to pick up the new image.

---

## Running without GPU

Remove the `deploy.resources` block from the `pipeline` service in `docker-compose.yml`:

```yaml
  pipeline:
    image: vicharanashala/faqcluster-pipeline:latest
    expose: ["7000"]
    environment:
      - CUDA_VISIBLE_DEVICES=""
    volumes:
      - app-data:/app/app-data
      - outputs:/app/outputs
    network_mode: host
    # deploy.resources block removed
```

The pipeline will run on CPU (significantly slower for large datasets).

---

## Local development (no Docker)

```bash
# Pipeline server
cd pipeline_server
uvicorn pipeline_server:app --host 0.0.0.0 --port 7000

# Frontend dev server (in a separate terminal)
cd frontend && npm run dev   # proxies /api calls to localhost:7000
```
