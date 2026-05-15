#!/usr/bin/env python3
import argparse
import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, List, Optional

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, field_validator, model_validator

ROOT_DIR = Path(__file__).resolve().parent
APP_DATA = ROOT_DIR / "app-data"
APP_DATA.mkdir(exist_ok=True)

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import _job_ctl

EXECUTOR = ThreadPoolExecutor()

app = FastAPI(title="FAQCluster API", redirect_slashes=False)

jobs: dict[str, dict] = {}

JOB_TYPE_IDS: dict[str, int] = {"pre": 1, "pipeline": 2, "post": 3, "full": 4}

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
    state: str
    crops: Optional[List[str]] = None
    domains: Optional[List[str]] = None
    output: str
    keep_intermediate: bool = True

    @field_validator("output")
    @classmethod
    def _safe_path(cls, v: str) -> str:
        _resolve_safe(v)
        return v

    @model_validator(mode="after")
    def require_crops_or_domains(self) -> "PreRequest":
        if not self.crops and not self.domains:
            raise ValueError("at least one of 'crops' or 'domains' must be provided")
        return self


class PipelineRequest(BaseModel):
    input: str = "cleaned_data.csv"
    crops: Optional[List[str]] = None
    domains: Optional[List[str]] = None
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

    @field_validator("output_dir", "input")
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
    state: str
    crops: Optional[List[str]] = None
    crops_file: Optional[str] = None
    domains: Optional[List[str]] = None
    output_dir: str = "outputs/repair"
    pre_output: Optional[str] = None
    model: str = "../models/qwen2.5-7b-instruct"
    api_key: Optional[str] = None
    gpu_id: int = 1
    batch_size: int = 8
    grid_mode: str = "quick"
    skip_pre_pipeline: bool = False
    skip_qa_gen: bool = False
    skip_post_pipeline: bool = False

    @field_validator("output_dir", "crops_file", "pre_output")
    @classmethod
    def _safe_path(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            _resolve_safe(v)
        return v


# --- Job runner ---

async def _run_job(job_id: str, fn: Callable[[], None]) -> None:
    jobs[job_id]["status"] = "running"
    loop = asyncio.get_running_loop()

    def _wrapped():
        _tl.job_id = job_id
        _job_ctl.set_job_id(job_id)
        try:
            fn()
        finally:
            _tl.job_id = None
            _job_ctl.set_job_id(None)
            _job_ctl.deregister_proc()

    try:
        await loop.run_in_executor(EXECUTOR, _wrapped)
        if _job_ctl.is_cancelled(job_id):
            jobs[job_id]["status"] = "stopped"
            jobs[job_id]["stderr"] = "stopped by user"
        else:
            jobs[job_id]["status"] = "done"
            jobs[job_id]["stderr"] = ""
    except _job_ctl.JobCancelled:
        jobs[job_id]["status"] = "stopped"
        jobs[job_id]["stderr"] = "stopped by user"
    except SystemExit as exc:
        code = exc.code if exc.code is not None else 0
        if _job_ctl.is_cancelled(job_id):
            jobs[job_id]["status"] = "stopped"
            jobs[job_id]["stderr"] = "stopped by user"
        else:
            jobs[job_id]["status"] = "done" if code == 0 else "failed"
            jobs[job_id]["stderr"] = f"SystemExit({code}): {code}"
    except subprocess.CalledProcessError as exc:
        if _job_ctl.is_cancelled(job_id):
            jobs[job_id]["status"] = "stopped"
            jobs[job_id]["stderr"] = "stopped by user"
        else:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["stderr"] = (
                f"CalledProcessError (returncode={exc.returncode}): "
                f"{exc.cmd!r}\n{traceback.format_exc()}"
            )
    except Exception:
        if _job_ctl.is_cancelled(job_id):
            jobs[job_id]["status"] = "stopped"
            jobs[job_id]["stderr"] = "stopped by user"
        else:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["stderr"] = traceback.format_exc()
    finally:
        _job_ctl.cleanup(job_id)


def _submit(fn: Callable[[], None], background: BackgroundTasks, job_type: str) -> dict:
    job_id = str(uuid.uuid4())
    _job_ctl.make_event(job_id)
    jobs[job_id] = {
        "job_id": job_id,
        "job_type": job_type,
        "job_type_id": JOB_TYPE_IDS[job_type],
        "status": "pending",
        "stdout": "",
        "stderr": "",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    background.add_task(_run_job, job_id, fn)
    return {
        "job_id": job_id,
        "job_type": job_type,
        "job_type_id": JOB_TYPE_IDS[job_type],
        "status": "pending",
    }


# --- Sync pipeline wrappers (run in ThreadPoolExecutor) ---

def _run_pre_sync(r: PreRequest) -> None:
    from run_pre_pipeline import run_state_filter, run_crop_normalizer

    input_path  = APP_DATA / "cleaned_data.csv"
    output_path = _resolve_safe(r.output)

    if not input_path.exists():
        raise FileNotFoundError(f"input file not found: {input_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    intermediate = output_path.parent / f"{output_path.stem}_state_rows.csv"

    run_state_filter(input_path, r.state, intermediate, domains=r.domains or [])
    if r.crops:
        run_crop_normalizer(intermediate, output_path, r.crops)
    else:
        import shutil
        shutil.copy2(intermediate, output_path)

    if intermediate.exists() and not r.keep_intermediate:
        intermediate.unlink()


def _run_pipeline_sync(r: PipelineRequest) -> None:
    from run_pipeline import (
        run_phase1, run_phase2, run_repair,
        run_unique_questions, run_dedup, run_corpus_filter, run_qa_gen,
        load_candidates, load_best_cfg, slug,
        DEFAULT_CORPUS,
    )

    import pandas as pd

    resolved_raw = str(APP_DATA / r.input)
    state_folder = Path(r.input).stem
    out_base     = _resolve_safe(r.output_dir) / state_folder
    failed       = []

    if r.crops or r.domains:
        _df = pd.read_csv(resolved_raw, low_memory=False)
        if r.crops:
            _df = _df[_df["Crop"].dropna().str.strip().isin(r.crops)]
        if r.domains:
            _df = _df[_df["QueryType"].dropna().str.strip().isin(r.domains)]
        crops = _df["Crop"].dropna().str.strip().unique().tolist()
        print(f"[INFO] Filtered to {len(crops)} unique crop(s): {', '.join(crops)}")
    else:
        print("[INFO] No crops/domains provided — discovering unique crops from input CSV...")
        _df = pd.read_csv(resolved_raw, low_memory=False)
        crops = _df["Crop"].dropna().str.strip().unique().tolist()
        print(f"[INFO] Found {len(crops)} unique crop(s): {', '.join(crops)}")

    for crop in crops:
        _job_ctl.check_cancel()
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
            _job_ctl.check_cancel()
            best_cfg   = load_best_cfg(out_dir, candidates) if args.skip_phase2 else run_phase2(args, out_dir, candidates)
            _job_ctl.check_cancel()

            if not args.skip_repair:
                run_repair(args, out_dir, candidates, best_cfg)
            _job_ctl.check_cancel()
            if not args.skip_unique_q:
                run_unique_questions(args, out_dir)

            run_dedup(out_dir)
            _job_ctl.check_cancel()

            if not args.skip_corpus_filter:
                corpus_path = Path(args.corpus_file)
                if corpus_path.exists():
                    run_corpus_filter(out_dir, args.corpus_file, args.fuzz_threshold)
            _job_ctl.check_cancel()

            if not args.skip_qa_gen:
                run_qa_gen(args, out_dir)

        except Exception as exc:
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
        _job_ctl.check_cancel()

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
    elif r.crops_file:
        crops_file = _resolve_safe(r.crops_file)
        if not crops_file.exists():
            raise FileNotFoundError(f"crops file not found: {crops_file}")
        lines = crops_file.read_text().splitlines()
        crops = [ln.strip() for ln in lines if ln.strip() and not ln.startswith('#')]
        if not crops:
            raise ValueError("no crops found in crops_file")
    else:
        crops = None  # will be auto-discovered below

    import pandas as pd

    # Stage 0: Pre-pipeline
    if r.skip_pre_pipeline:
        effective_raw = str(APP_DATA / "cleaned_data.csv")
        if crops is None:
            _df = pd.read_csv(effective_raw, low_memory=False)
            if r.domains:
                _df = _df[_df["QueryType"].dropna().str.strip().isin(r.domains)]
            crops = _df["Crop"].dropna().str.strip().unique().tolist()
            print(f"[INFO] Auto-discovered {len(crops)} crop(s) from input CSV")
    else:
        raw_file   = APP_DATA / "cleaned_data.csv"
        if r.pre_output:
            norm_file = _resolve_safe(r.pre_output)
            _norm_is_temp = False
        else:
            fd, tmp_path = tempfile.mkstemp(suffix='_norm.csv', dir=str(APP_DATA))
            os.close(fd)
            norm_file = Path(tmp_path)
            _norm_is_temp = True
            print("[INFO] No pre-pipeline output path provided — result kept in RAM only (temp file deleted after use)")
        intermediate = norm_file.parent / f"{norm_file.stem}_state_rows.csv"

        run_state_filter(raw_file, r.state, intermediate, domains=r.domains or [])

        if crops is None:
            run_crop_normalizer(intermediate, norm_file)
            crops = pd.read_csv(norm_file)["Crop"].dropna().str.strip().unique().tolist()
            print(f"[INFO] Auto-discovered {len(crops)} canonical crop(s) after normalization")
        else:
            run_crop_normalizer(intermediate, norm_file, crops)

        if intermediate.exists():
            intermediate.unlink()

        effective_raw = str(norm_file)

    # Per-crop pipeline
    state_folder = Path(effective_raw).stem  # e.g. "tamilnadu_norm"
    out_base     = _resolve_safe(r.output_dir) / state_folder
    failed = []
    for crop in crops:
        _job_ctl.check_cancel()
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
            _job_ctl.check_cancel()
            best_cfg   = run_phase2(args, out_dir, candidates)
            _job_ctl.check_cancel()
            run_repair(args, out_dir, candidates, best_cfg)
            _job_ctl.check_cancel()
            run_unique_questions(args, out_dir)
            run_dedup(out_dir)
            _job_ctl.check_cancel()
            corpus_path = Path(args.corpus_file)
            if corpus_path.exists():
                run_corpus_filter(out_dir, args.corpus_file, args.fuzz_threshold)
            _job_ctl.check_cancel()
            if not args.skip_qa_gen:
                run_qa_gen(args, out_dir)
        except Exception as exc:
            print(f"[WARN] Crop '{crop}' failed: {exc}")
            failed.append(crop)

    if not r.skip_pre_pipeline and _norm_is_temp and norm_file.exists():
        norm_file.unlink()
        print("[INFO] Temporary pre-pipeline file removed from disk")

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
    return _submit(lambda: _run_pre_sync(req), background, "pre")


@app.post("/run/pipeline")
def run_pipeline(req: PipelineRequest, background: BackgroundTasks):
    return _submit(lambda: _run_pipeline_sync(req), background, "pipeline")


@app.post("/run/post")
def run_post(req: PostRequest, background: BackgroundTasks):
    return _submit(lambda: _run_post_sync(req), background, "post")


@app.post("/run/full")
def run_full(req: FullRequest, background: BackgroundTasks):
    return _submit(lambda: _run_full_sync(req), background, "full")


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

@app.get("/files/download/{path:path}")
def download_file(path: str):
    target = _resolve_safe(path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(str(target), filename=target.name)


@app.get("/files/tree")
def app_data_tree():
    """
    Filtered view of app-data for the frontend. Returns three sections:
    - all_csvs: every CSV in app-data except inside outputs/repair/ and final/
    - crop_qa_files: unique_questions_freq_qa.csv per crop in outputs/repair/{state}/{crop}/
    - final_csvs: every CSV in app-data/final/{state}/
    Each entry has a 'path' usable with GET /files/download/{path}.
    """
    def _file_entry(p: Path) -> dict:
        return {
            "name": p.name,
            "path": str(p.relative_to(APP_DATA)),
            "size": p.stat().st_size,
        }

    outputs_dir = APP_DATA / "outputs"
    repair_dir = outputs_dir / "repair"
    final_root = APP_DATA / "final"

    all_csvs = []
    if APP_DATA.exists():
        for p in APP_DATA.rglob("*.csv"):
            if ".ipynb_checkpoints" in p.parts:
                continue
            try:
                p.relative_to(outputs_dir)
                continue
            except ValueError:
                pass
            try:
                p.relative_to(final_root)
                continue
            except ValueError:
                pass
            all_csvs.append(_file_entry(p))
    all_csvs.sort(key=lambda e: e["path"])

    crop_qa_files = []
    if repair_dir.exists():
        for qa_file in sorted(repair_dir.rglob("unique_questions_freq_qa.csv")):
            crop_slug = qa_file.parent.name
            state_name = qa_file.parent.parent.name
            entry = _file_entry(qa_file)
            entry["crop"] = crop_slug
            entry["state"] = state_name
            entry["displayName"] = crop_slug
            crop_qa_files.append(entry)

    final_csvs = []
    if repair_dir.exists():
        for state_dir in sorted(repair_dir.iterdir()):
            if not state_dir.is_dir():
                continue
            final_dir = state_dir / "final"
            if not final_dir.exists():
                continue
            for p in sorted(final_dir.iterdir()):
                if not p.is_file():
                    continue
                if p.name.startswith("dedup_") or p.name.startswith("phase_"):
                    entry = _file_entry(p)
                    entry["state"] = state_dir.name
                    entry["folderPath"] = str(final_dir.relative_to(APP_DATA))
                    final_csvs.append(entry)

    return {
        "all_csvs": all_csvs,
        "crop_qa_files": crop_qa_files,
        "final_csvs": final_csvs,
    }


@app.delete("/files/{path:path}")
def delete_file(path: str):
    target = _resolve_safe(path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="file not found")
    if target.is_dir():
        raise HTTPException(status_code=400, detail="path is a directory")
    target.unlink()
    # When deleting a prefixed file (dedup_* or phase_*) from a repair/final dir,
    # also remove the base file (without the prefix) if it exists.
    parent = target.parent
    name = target.name
    for prefix in ("dedup_", "phase_"):
        if name.startswith(prefix):
            base = parent / name[len(prefix):]
            if base.exists() and base.is_file():
                base.unlink()
            break
    return {"deleted": path}


@app.delete("/folders/{path:path}")
def delete_folder(path: str):
    target = _resolve_safe(path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="folder not found")
    if not target.is_dir():
        raise HTTPException(status_code=400, detail="path is not a directory")
    shutil.rmtree(target)
    return {"deleted": path}


class RenameRequest(BaseModel):
    to: str

    @field_validator("to")
    @classmethod
    def _safe_to(cls, v: str) -> str:
        _resolve_safe(v)
        return v


@app.post("/files/rename/{path:path}")
def rename_file(path: str, body: RenameRequest):
    source = _resolve_safe(path)
    dest = _resolve_safe(body.to)
    if not source.exists():
        raise HTTPException(status_code=404, detail="source not found")
    if dest.exists():
        raise HTTPException(status_code=409, detail="destination already exists")
    dest.parent.mkdir(parents=True, exist_ok=True)
    source.rename(dest)
    return {"from": path, "to": body.to}


@app.post("/files/upload")
async def upload_file(dest: str = "", file: UploadFile = File(...)):
    if dest:
        _resolve_safe(dest)
        save_dir = (APP_DATA / dest).resolve()
    else:
        save_dir = APP_DATA
    save_dir.mkdir(parents=True, exist_ok=True)
    target = (save_dir / file.filename).resolve()
    if not target.is_relative_to(APP_DATA.resolve()):
        raise HTTPException(status_code=400, detail="path escapes sandbox")
    content = await file.read()
    target.write_bytes(content)
    return {"uploaded": str(target.relative_to(APP_DATA))}


@app.post("/jobs/{job_id}/stop")
def stop_job(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    if job["status"] != "running":
        raise HTTPException(
            status_code=409,
            detail=f"job is not running (status={job['status']})",
        )
    _job_ctl.cancel(job_id)
    jobs[job_id]["status"] = "stopped"
    return {"job_id": job_id, "status": "stopped"}


@app.delete("/jobs/{job_id}")
def delete_job(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    if job["status"] == "running":
        raise HTTPException(status_code=409, detail="cannot delete a running job")
    del jobs[job_id]
    return {"deleted": job_id}
