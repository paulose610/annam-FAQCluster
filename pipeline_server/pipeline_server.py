"""
Thin FastAPI wrapper that exposes run_pipeline.py as an HTTP service.
Runs inside the pipeline container; called by the webapp container when
PIPELINE_API_URL env var is set.

Endpoints:
  POST /run/pipeline  — start a pipeline job, returns {"job_id": "..."}
  GET  /jobs/{id}     — poll status + stdout
  POST /jobs/{id}/stop — kill the job
"""

import asyncio
import os
import signal
import sys
import uuid
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

app = FastAPI(title="FAQCluster Pipeline Service")

# job_id → {proc, lines, status, returncode}
_jobs: dict[str, dict] = {}


class PipelineRunRequest(BaseModel):
    raw_file: str
    crop: str
    model: str
    gpu_id: int = 0
    batch_size: int = 8
    grid_mode: str = "quick"
    output_dir: str = "outputs/repair"
    api_key: str = ""
    skip_phase1: bool = False
    skip_phase2: bool = False
    skip_repair: bool = False
    skip_unique_q: bool = False
    skip_corpus_filter: bool = False
    skip_qa_gen: bool = False


def _build_cmd(req: PipelineRunRequest) -> list[str]:
    cmd = [
        sys.executable, "-u", str(SCRIPT_DIR / "run_pipeline.py"),
        "--raw-file",   req.raw_file,
        "--crop",       req.crop,
        "--model",      req.model,
        "--gpu-id",     str(req.gpu_id),
        "--batch-size", str(req.batch_size),
        "--grid-mode",  req.grid_mode,
        "--output-dir", req.output_dir,
    ]
    if req.api_key:
        cmd += ["--api-key", req.api_key]
    if req.skip_phase1:        cmd += ["--skip-phase1"]
    if req.skip_phase2:        cmd += ["--skip-phase2"]
    if req.skip_repair:        cmd += ["--skip-repair"]
    if req.skip_unique_q:      cmd += ["--skip-unique-q"]
    if req.skip_corpus_filter: cmd += ["--skip-corpus-filter"]
    if req.skip_qa_gen:        cmd += ["--skip-qa-gen"]
    return cmd


async def _drain_stdout(job_id: str, proc: asyncio.subprocess.Process) -> None:
    job = _jobs[job_id]
    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        job["lines"].append(line.decode(errors="replace"))
    await proc.wait()
    job["returncode"] = proc.returncode
    job["status"] = "done" if proc.returncode == 0 else "failed"


@app.get("/")
def health():
    return {"status": "ok"}


@app.post("/run/pipeline")
async def run_pipeline(req: PipelineRunRequest):
    job_id = uuid.uuid4().hex[:12]
    cmd = _build_cmd(req)
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        preexec_fn=os.setsid,
    )
    _jobs[job_id] = {
        "proc": proc,
        "lines": [],
        "status": "running",
        "returncode": None,
    }
    asyncio.create_task(_drain_stdout(job_id, proc))
    return {"job_id": job_id}


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    job = _jobs.get(job_id)
    if job is None:
        return {"status": "not_found", "stdout": "", "returncode": None}
    return {
        "status": job["status"],
        "stdout": "".join(job["lines"]),
        "returncode": job["returncode"],
    }


@app.post("/jobs/{job_id}/stop")
def stop_job(job_id: str):
    job = _jobs.get(job_id)
    if job and job["status"] == "running":
        proc: asyncio.subprocess.Process = job["proc"]
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        job["status"] = "stopped"
    return {"ok": True}
