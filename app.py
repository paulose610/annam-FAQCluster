#!/usr/bin/env python3
import asyncio
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, model_validator

ROOT_DIR = Path(__file__).resolve().parent

app = FastAPI(title="FAQCluster API")

jobs: dict[str, dict] = {}


# --- Pydantic models ---

class PreRequest(BaseModel):
    input: str
    state: str
    crops: List[str]
    output: str
    keep_intermediate: bool = True


class PipelineRequest(BaseModel):
    raw_file: str
    crop: str
    output_dir: str = "outputs/repair"
    model: str = "/home/kshitij/models/qwen2.5-7b-instruct"
    api_key: Optional[str] = None
    gpu_id: int = 0
    batch_size: int = 8
    grid_mode: str = "medium"
    skip_phase1: bool = False
    skip_phase2: bool = False
    skip_repair: bool = False
    skip_unique_q: bool = False
    skip_corpus_filter: bool = False
    skip_qa_gen: bool = False


class PostRequest(BaseModel):
    input: str = "outputs/repair"
    skip_collect: bool = False
    skip_dedup: bool = False


class FullRequest(BaseModel):
    raw_file: str
    state: str
    crops: Optional[List[str]] = None
    crops_file: Optional[str] = None
    output_dir: str = "outputs/repair"
    model: str = "/home/kshitij/models/qwen2.5-7b-instruct"
    api_key: Optional[str] = None
    gpu_id: int = 0
    batch_size: int = 8
    grid_mode: str = "quick"
    skip_pre_pipeline: bool = False
    skip_qa_gen: bool = False
    skip_post_pipeline: bool = False

    @model_validator(mode="after")
    def require_crops_or_crops_file(self) -> "FullRequest":
        if not self.crops and not self.crops_file:
            raise ValueError("either 'crops' or 'crops_file' must be provided")
        return self


# --- Job runner ---

async def _run_job(job_id: str, cmd: list[str]) -> None:
    jobs[job_id]["status"] = "running"
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(ROOT_DIR),
    )
    stdout, stderr = await proc.communicate()
    jobs[job_id]["status"] = "done" if proc.returncode == 0 else "failed"
    jobs[job_id]["stdout"] = stdout.decode(errors="replace")
    jobs[job_id]["stderr"] = stderr.decode(errors="replace")


def _submit(cmd: list[str], background: BackgroundTasks) -> dict:
    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "job_id": job_id,
        "status": "pending",
        "cmd": cmd,
        "stdout": "",
        "stderr": "",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    background.add_task(_run_job, job_id, cmd)
    return {"job_id": job_id, "status": "pending"}


# --- Command builders ---

def _pre_cmd(r: PreRequest) -> list[str]:
    cmd = [
        sys.executable, "run_pre_pipeline.py",
        "--input", r.input,
        "--state", r.state,
        "--crops", *r.crops,
        "--output", r.output,
    ]
    if r.keep_intermediate:
        cmd.append("--keep-intermediate")
    return cmd


def _pipeline_cmd(r: PipelineRequest) -> list[str]:
    cmd = [
        sys.executable, "run_pipeline.py",
        "--raw-file", r.raw_file,
        "--crop", r.crop,
        "--output-dir", r.output_dir,
        "--model", r.model,
        "--gpu-id", str(r.gpu_id),
        "--batch-size", str(r.batch_size),
        "--grid-mode", r.grid_mode,
    ]
    if r.api_key:
        cmd += ["--api-key", r.api_key]
    for flag, arg in [
        (r.skip_phase1, "--skip-phase1"),
        (r.skip_phase2, "--skip-phase2"),
        (r.skip_repair, "--skip-repair"),
        (r.skip_unique_q, "--skip-unique-q"),
        (r.skip_corpus_filter, "--skip-corpus-filter"),
        (r.skip_qa_gen, "--skip-qa-gen"),
    ]:
        if flag:
            cmd.append(arg)
    return cmd


def _post_cmd(r: PostRequest) -> list[str]:
    cmd = [sys.executable, "run_post_pipeline.py", "--input", r.input]
    if r.skip_collect:
        cmd.append("--skip-collect")
    if r.skip_dedup:
        cmd.append("--skip-dedup")
    return cmd


def _full_cmd(r: FullRequest) -> list[str]:
    cmd = [
        sys.executable, "run_full.py",
        "--raw-file", r.raw_file,
        "--state", r.state,
        "--output-dir", r.output_dir,
        "--model", r.model,
        "--gpu-id", str(r.gpu_id),
        "--batch-size", str(r.batch_size),
        "--grid-mode", r.grid_mode,
    ]
    if r.crops:
        cmd += ["--crops", *r.crops]
    if r.crops_file:
        cmd += ["--crops-file", r.crops_file]
    if r.api_key:
        cmd += ["--api-key", r.api_key]
    for flag, arg in [
        (r.skip_pre_pipeline, "--skip-pre-pipeline"),
        (r.skip_qa_gen, "--skip-qa-gen"),
        (r.skip_post_pipeline, "--skip-post-pipeline"),
    ]:
        if flag:
            cmd.append(arg)
    return cmd


# --- Endpoints ---

@app.get("/")
def health():
    return {"status": "ok"}


@app.post("/run/pre")
def run_pre(req: PreRequest, background: BackgroundTasks):
    return _submit(_pre_cmd(req), background)


@app.post("/run/pipeline")
def run_pipeline(req: PipelineRequest, background: BackgroundTasks):
    return _submit(_pipeline_cmd(req), background)


@app.post("/run/post")
def run_post(req: PostRequest, background: BackgroundTasks):
    return _submit(_post_cmd(req), background)


@app.post("/run/full")
def run_full(req: FullRequest, background: BackgroundTasks):
    return _submit(_full_cmd(req), background)


@app.get("/jobs")
def list_jobs():
    return list(jobs.values())


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job


# --- File endpoints ---

@app.get("/files/outputs")
def list_outputs():
    outputs_dir = ROOT_DIR / "outputs"
    if not outputs_dir.exists():
        return []
    return [str(p.relative_to(ROOT_DIR)) for p in outputs_dir.rglob("*") if p.is_file()]


@app.get("/files/outputs/{path:path}")
def download_output(path: str):
    target = (ROOT_DIR / "outputs" / path).resolve()
    if not target.is_relative_to((ROOT_DIR / "outputs").resolve()):
        raise HTTPException(status_code=400, detail="invalid path")
    if not target.exists():
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(str(target), filename=target.name)


@app.get("/files/root")
def list_root_csvs():
    return [p.name for p in ROOT_DIR.iterdir() if p.is_file() and p.suffix == ".csv"]


@app.get("/files/root/{filename}")
def download_root_csv(filename: str):
    if "/" in filename or not filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="invalid filename")
    target = ROOT_DIR / filename
    if not target.exists():
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(str(target), filename=filename)
