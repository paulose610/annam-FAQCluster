#!/usr/bin/env python3
import argparse
import asyncio
import subprocess
import sys
import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, List, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, field_validator, model_validator

ROOT_DIR = Path(__file__).resolve().parent
APP_DATA = ROOT_DIR / "app-data"
APP_DATA.mkdir(exist_ok=True)

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

EXECUTOR = ThreadPoolExecutor()

app = FastAPI(title="FAQCluster API", redirect_slashes=False)

jobs: dict[str, dict] = {}

_tl = threading.local()


class _JobStdout:
    """Routes print() output to the current job's stdout buffer, thread-safely."""
    def __init__(self, original):
        self._orig = original

    def write(self, data):
        job_id = getattr(_tl, "job_id", None)
        if job_id and job_id in jobs:
            jobs[job_id]["stdout"] += data
        self._orig.write(data)

    def flush(self):
        self._orig.flush()

    def __getattr__(self, name):
        return getattr(self._orig, name)


sys.stdout = _JobStdout(sys.stdout)


# --- Path sandboxing ---

def _resolve_safe(user_str: str) -> Path:
    """Resolve a user-supplied relative path inside APP_DATA.

    Rejects absolute paths, '..' traversal, and null bytes.
    Final is_relative_to check catches symlink-based escapes.
    """
    p = Path(user_str)
    if p.is_absolute():
        raise ValueError(f"absolute paths are not allowed: {user_str!r}")
    for part in p.parts:
        if part == "..":
            raise ValueError(f"path traversal not allowed: {user_str!r}")
        if "\x00" in part:
            raise ValueError(f"null bytes not allowed in path: {user_str!r}")
    resolved = (APP_DATA / p).resolve()
    if not resolved.is_relative_to(APP_DATA.resolve()):
        raise ValueError(f"path escapes app-data sandbox: {user_str!r}")
    return resolved


# --- Pydantic models ---

class PreRequest(BaseModel):
    input: str
    state: str
    crops: List[str]
    output: str
    keep_intermediate: bool = True

    @field_validator("input", "output")
    @classmethod
    def _safe_path(cls, v: str) -> str:
        _resolve_safe(v)
        return v


class PipelineRequest(BaseModel):
    raw_file: str
    crops: List[str]
    output_dir: str = "outputs/repair"
    model: str = "../models/qwen2.5-7b-instruct"
    api_key: Optional[str] = None
    gpu_id: int = 1
    batch_size: int = 8
    grid_mode: str = "quick"
    skip_phase1: bool = False
    skip_phase2: bool = False
    skip_repair: bool = False
    skip_unique_q: bool = False
    skip_corpus_filter: bool = False
    skip_qa_gen: bool = False

    @field_validator("raw_file", "output_dir")
    @classmethod
    def _safe_path(cls, v: str) -> str:
        _resolve_safe(v)
        return v


class PostRequest(BaseModel):
    input: str = "outputs/repair"
    skip_collect: bool = False
    skip_dedup: bool = False

    @field_validator("input")
    @classmethod
    def _safe_path(cls, v: str) -> str:
        _resolve_safe(v)
        return v


class FullRequest(BaseModel):
    raw_file: str
    state: str
    crops: Optional[List[str]] = None
    crops_file: Optional[str] = None
    output_dir: str = "outputs/repair"
    model: str = "../models/qwen2.5-7b-instruct"
    api_key: Optional[str] = None
    gpu_id: int = 1
    batch_size: int = 8
    grid_mode: str = "quick"
    skip_pre_pipeline: bool = False
    skip_qa_gen: bool = False
    skip_post_pipeline: bool = False

    @field_validator("raw_file", "output_dir", "crops_file")
    @classmethod
    def _safe_path(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            _resolve_safe(v)
        return v

    @model_validator(mode="after")
    def require_crops_or_crops_file(self) -> "FullRequest":
        if not self.crops and not self.crops_file:
            raise ValueError("either 'crops' or 'crops_file' must be provided")
        return self


# --- Job runner ---

async def _run_job(job_id: str, fn: Callable[[], None]) -> None:
    jobs[job_id]["status"] = "running"
    loop = asyncio.get_running_loop()

    def _wrapped():
        _tl.job_id = job_id
        try:
            fn()
        finally:
            _tl.job_id = None

    try:
        await loop.run_in_executor(EXECUTOR, _wrapped)
        jobs[job_id]["status"] = "done"
        jobs[job_id]["stderr"] = ""
    except SystemExit as exc:
        code = exc.code if exc.code is not None else 0
        jobs[job_id]["status"] = "done" if code == 0 else "failed"
        jobs[job_id]["stderr"] = f"SystemExit({code}): {code}"
    except subprocess.CalledProcessError as exc:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["stderr"] = (
            f"CalledProcessError (returncode={exc.returncode}): "
            f"{exc.cmd!r}\n{traceback.format_exc()}"
        )
    except Exception:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["stderr"] = traceback.format_exc()


def _submit(fn: Callable[[], None], background: BackgroundTasks) -> dict:
    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "job_id": job_id,
        "status": "pending",
        "stdout": "",
        "stderr": "",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    background.add_task(_run_job, job_id, fn)
    return {"job_id": job_id, "status": "pending"}


# --- Sync pipeline wrappers (run in ThreadPoolExecutor) ---

def _run_pre_sync(r: PreRequest) -> None:
    from run_pre_pipeline import run_state_filter, run_crop_normalizer

    input_path  = _resolve_safe(r.input)
    output_path = _resolve_safe(r.output)

    if not input_path.exists():
        raise FileNotFoundError(f"input file not found: {input_path}")

    intermediate = output_path.parent / f"{output_path.stem}_state_rows.csv"

    run_state_filter(input_path, r.state, intermediate)
    run_crop_normalizer(intermediate, output_path, r.crops)

    if intermediate.exists() and not r.keep_intermediate:
        intermediate.unlink()


def _run_pipeline_sync(r: PipelineRequest) -> None:
    from run_pipeline import (
        run_phase1, run_phase2, run_repair,
        run_unique_questions, run_dedup, run_corpus_filter, run_qa_gen,
        load_candidates, load_best_cfg, slug,
        DEFAULT_CORPUS,
    )

    resolved_raw = str(_resolve_safe(r.raw_file))
    state_folder = Path(r.raw_file).stem  # e.g. "maharashtra_norm" from "data/maharashtra_norm.csv"
    out_base     = _resolve_safe(r.output_dir) / state_folder
    failed       = []

    for crop in r.crops:
        args = argparse.Namespace(
            raw_file           = resolved_raw,
            crop               = crop,
            model              = r.model,
            api_key            = r.api_key,
            gpu_id             = r.gpu_id,
            batch_size         = r.batch_size,
            grid_mode          = r.grid_mode,
            skip_phase1        = r.skip_phase1,
            skip_phase2        = r.skip_phase2,
            skip_repair        = r.skip_repair,
            skip_unique_q      = r.skip_unique_q,
            skip_corpus_filter = r.skip_corpus_filter,
            skip_qa_gen        = r.skip_qa_gen,
            max_queries        = 20000,
            phase2_top_k       = 5,
            coverage_cap       = 0.80,
            diverse_k          = 3,
            coherence_flag     = 'C',
            merge_sim          = 0.82,
            corpus_file        = str(DEFAULT_CORPUS),
            fuzz_threshold     = 100,
            output_dir         = str(out_base),
        )

        out_dir = out_base / slug(crop)
        out_dir.mkdir(parents=True, exist_ok=True)

        try:
            candidates = load_candidates(out_dir) if args.skip_phase1 else run_phase1(args, out_dir)
            best_cfg   = load_best_cfg(out_dir, candidates) if args.skip_phase2 else run_phase2(args, out_dir, candidates)

            if not args.skip_repair:
                run_repair(args, out_dir, candidates, best_cfg)
            if not args.skip_unique_q:
                run_unique_questions(args, out_dir)

            run_dedup(out_dir)

            if not args.skip_corpus_filter:
                corpus_path = Path(args.corpus_file)
                if corpus_path.exists():
                    run_corpus_filter(out_dir, args.corpus_file, args.fuzz_threshold)

            if not args.skip_qa_gen:
                run_qa_gen(args, out_dir)

        except (SystemExit, Exception) as exc:
            print(f"[WARN] Crop '{crop}' failed: {exc}")
            failed.append(crop)

    if failed:
        raise RuntimeError(f"The following crops failed: {', '.join(failed)}")


def _run_post_sync(r: PostRequest) -> None:
    from run_post_pipeline import run_collect, run_dedup as post_run_dedup

    input_dir = _resolve_safe(r.input)
    if not input_dir.exists():
        raise FileNotFoundError(f"input folder not found: {input_dir}")

    final_dir = input_dir / 'final'

    if r.skip_collect:
        if not final_dir.exists():
            raise FileNotFoundError(
                f"{final_dir} does not exist; run without skip_collect first."
            )
    else:
        final_dir = run_collect(input_dir)

    if not r.skip_dedup:
        post_run_dedup(final_dir)


def _run_full_sync(r: FullRequest) -> None:
    from run_pre_pipeline import run_state_filter, run_crop_normalizer
    from run_pipeline import (
        run_phase1, run_phase2, run_repair,
        run_unique_questions, run_dedup, run_corpus_filter, run_qa_gen,
        load_candidates, load_best_cfg, slug,
        DEFAULT_CORPUS,
    )
    from run_post_pipeline import run_collect, run_dedup as post_run_dedup

    # Resolve crop list
    if r.crops:
        crops = r.crops
    else:
        crops_file = _resolve_safe(r.crops_file)
        if not crops_file.exists():
            raise FileNotFoundError(f"crops file not found: {crops_file}")
        lines = crops_file.read_text().splitlines()
        crops = [ln.strip() for ln in lines if ln.strip() and not ln.startswith('#')]

    if not crops:
        raise ValueError("no crops specified")

    # Stage 0: Pre-pipeline
    if r.skip_pre_pipeline:
        effective_raw = str(_resolve_safe(r.raw_file))
    else:
        raw_file     = _resolve_safe(r.raw_file)
        state_slug   = r.state.strip().lower().replace(" ", "_")
        norm_file    = raw_file.parent / f"{state_slug}_norm.csv"
        intermediate = norm_file.parent / f"{norm_file.stem}_state_rows.csv"

        run_state_filter(raw_file, r.state, intermediate)
        run_crop_normalizer(intermediate, norm_file, crops)

        if intermediate.exists():
            intermediate.unlink()

        effective_raw = str(norm_file)

    # Per-crop pipeline
    state_folder = Path(effective_raw).stem  # e.g. "tamilnadu_norm"
    out_base     = _resolve_safe(r.output_dir) / state_folder
    failed = []
    for crop in crops:
        args = argparse.Namespace(
            raw_file           = effective_raw,
            crop               = crop,
            model              = r.model,
            api_key            = r.api_key,
            gpu_id             = r.gpu_id,
            batch_size         = r.batch_size,
            grid_mode          = r.grid_mode,
            skip_phase1        = False,
            skip_phase2        = False,
            skip_repair        = False,
            skip_unique_q      = False,
            skip_corpus_filter = False,
            skip_qa_gen        = r.skip_qa_gen,
            max_queries        = 20000,
            phase2_top_k       = 5,
            coverage_cap       = 0.80,
            diverse_k          = 3,
            coherence_flag     = 'C',
            merge_sim          = 0.82,
            corpus_file        = str(DEFAULT_CORPUS),
            fuzz_threshold     = 100,
            output_dir         = str(out_base),
        )

        out_dir = out_base / slug(crop)
        out_dir.mkdir(parents=True, exist_ok=True)

        try:
            candidates = run_phase1(args, out_dir)
            best_cfg   = run_phase2(args, out_dir, candidates)
            run_repair(args, out_dir, candidates, best_cfg)
            run_unique_questions(args, out_dir)
            run_dedup(out_dir)
            corpus_path = Path(args.corpus_file)
            if corpus_path.exists():
                run_corpus_filter(out_dir, args.corpus_file, args.fuzz_threshold)
            if not args.skip_qa_gen:
                run_qa_gen(args, out_dir)
        except (SystemExit, Exception) as exc:
            print(f"[WARN] Crop '{crop}' failed: {exc}")
            failed.append(crop)

    # Post-pipeline
    if not r.skip_post_pipeline:
        final_dir = run_collect(out_base)
        post_run_dedup(final_dir)

    if failed:
        raise RuntimeError(f"The following crops failed: {', '.join(failed)}")


# --- Endpoints ---

@app.get("/")
def health():
    return {"status": "ok"}


@app.post("/run/pre")
def run_pre(req: PreRequest, background: BackgroundTasks):
    return _submit(lambda: _run_pre_sync(req), background)


@app.post("/run/pipeline")
def run_pipeline(req: PipelineRequest, background: BackgroundTasks):
    return _submit(lambda: _run_pipeline_sync(req), background)


@app.post("/run/post")
def run_post(req: PostRequest, background: BackgroundTasks):
    return _submit(lambda: _run_post_sync(req), background)


@app.post("/run/full")
def run_full(req: FullRequest, background: BackgroundTasks):
    return _submit(lambda: _run_full_sync(req), background)


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
    outputs_dir = APP_DATA / "outputs"
    if not outputs_dir.exists():
        return []
    return [str(p.relative_to(APP_DATA)) for p in outputs_dir.rglob("*") if p.is_file()]


@app.get("/files/outputs/{path:path}")
def download_output(path: str):
    outputs_root = (APP_DATA / "outputs").resolve()
    target = (outputs_root / path).resolve()
    if not target.is_relative_to(outputs_root):
        raise HTTPException(status_code=400, detail="invalid path")
    if not target.exists():
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(str(target), filename=target.name)


@app.get("/files/root")
def list_root_csvs():
    return [p.name for p in APP_DATA.iterdir() if p.is_file() and p.suffix == ".csv"]


@app.get("/files/root/{filename}")
def download_root_csv(filename: str):
    if "/" in filename or not filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="invalid filename")
    target = APP_DATA / filename
    if not target.exists():
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(str(target), filename=filename)
