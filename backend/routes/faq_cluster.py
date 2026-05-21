import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel, field_validator, model_validator

from backend.common import APP_DATA, _resolve_safe
from backend.jobs import _submit

router = APIRouter()

_ROOT_DIR = Path(__file__).resolve().parent.parent.parent  # FAQCluster/
_RUN_PIPELINE = _ROOT_DIR / 'run_pipeline.py'


def slug(name: str) -> str:
    return re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')


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
    model: str = "google/gemma-4-26B-A4B-it"
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
    crops: Optional[List[str]] = None
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
    model: str = "google/gemma-4-26B-A4B-it"
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


def _next_versioned_path(current_path: Path) -> Path:
    """Return the next non-existent versioned path, e.g. maharashtra_1.csv → maharashtra_2.csv."""
    m = re.match(r'^(.+)_(\d+)$', current_path.stem)
    base, ver = (m.group(1), int(m.group(2))) if m else (current_path.stem, 0)
    next_ver = ver + 1
    while True:
        candidate = current_path.parent / f"{base}_{next_ver}{current_path.suffix}"
        if not candidate.exists():
            return candidate
        next_ver += 1


# --- Sync pipeline wrappers ---

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
        shutil.copy2(intermediate, output_path)

    if intermediate.exists() and not r.keep_intermediate:
        intermediate.unlink()


def _run_pipeline_sync(r: PipelineRequest) -> None:
    import _job_ctl
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
        (out_base / slug(crop)).mkdir(parents=True, exist_ok=True)

        # Run the full per-crop pipeline as a subprocess so that:
        # (1) stop button immediately kills it via os.killpg on the process group, and
        # (2) the auto-skip logic in run_pipeline.py:main() skips already-done stages.
        cmd = [
            sys.executable, '-u', str(_RUN_PIPELINE),
            '--raw-file',   resolved_raw,
            '--crop',       crop,
            '--model',      r.model,
            '--gpu-id',     str(r.gpu_id),
            '--batch-size', str(r.batch_size),
            '--grid-mode',  r.grid_mode,
            '--output-dir', str(_resolve_safe(r.output_dir)),
        ]
        if r.api_key:
            cmd += ['--api-key', r.api_key]
        if r.skip_phase1:        cmd += ['--skip-phase1']
        if r.skip_phase2:        cmd += ['--skip-phase2']
        if r.skip_repair:        cmd += ['--skip-repair']
        if r.skip_unique_q:      cmd += ['--skip-unique-q']
        if r.skip_corpus_filter: cmd += ['--skip-corpus-filter']
        if r.skip_qa_gen:        cmd += ['--skip-qa-gen']

        print(f"[INFO] Starting pipeline for '{crop}'...")
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, preexec_fn=os.setsid, bufsize=1,
        )
        _job_ctl.register_proc(proc)
        for line in proc.stdout:
            print(line, end="", flush=True)
            # Race-condition fix: cancel() may have fired before register_proc();
            # kill the proc here if it's still running.
            if _job_ctl.is_cancelled(_job_ctl.current_job_id()):
                if proc.poll() is None:
                    try:
                        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    except Exception:
                        proc.kill()
                break
        proc.wait()
        _job_ctl.deregister_proc()

        # Unconditional check: raises JobCancelled whether subprocess was killed (-9)
        # or completed with returncode=0 just as the user clicked Stop.
        _job_ctl.check_cancel()

        if proc.returncode != 0:
            print(f"[WARN] Crop '{crop}' failed (returncode={proc.returncode})")
            failed.append(crop)

    if failed:
        raise RuntimeError(f"The following crops failed: {', '.join(failed)}")


def _run_post_sync(r: PostRequest) -> None:
    from run_post_pipeline import run_dedup as post_run_dedup

    input_dir = _resolve_safe(r.input)
    if not input_dir.exists():
        raise FileNotFoundError(f"input folder not found: {input_dir}")

    if not r.skip_dedup:
        post_run_dedup(input_dir, r.crops or None)


def _run_full_sync(r: FullRequest) -> None:
    import _job_ctl
    import pandas as pd
    from run_pre_pipeline import run_state_filter, run_crop_normalizer
    from run_post_pipeline import run_dedup as post_run_dedup

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
        crops = None

    if r.skip_pre_pipeline:
        effective_raw = str(APP_DATA / "cleaned_data.csv")
        if crops is None:
            _df = pd.read_csv(effective_raw, low_memory=False)
            if r.domains:
                _df = _df[_df["QueryType"].dropna().str.strip().isin(r.domains)]
            crops = _df["Crop"].dropna().str.strip().unique().tolist()
            print(f"[INFO] Auto-discovered {len(crops)} crop(s) from input CSV")
    else:
        raw_file = APP_DATA / "cleaned_data.csv"
        if r.pre_output:
            norm_file = _resolve_safe(r.pre_output)
            norm_file.parent.mkdir(parents=True, exist_ok=True)
            _norm_is_temp = False

            # meta.json lives in the folder — matches what getNextState looks for
            meta_path = norm_file.parent / "meta.json"
            existing_meta: dict = {}
            for _mp in (meta_path, norm_file.with_suffix('.json')):
                if _mp.exists():
                    try:
                        existing_meta = json.loads(_mp.read_text())
                        break
                    except Exception:
                        pass

            existing_domains     = set(existing_meta.get("domains", []))
            existing_crops_meta  = set(existing_meta.get("crops", []))
            requested_domains    = set(r.domains or [])
            file_exists          = norm_file.exists() and bool(existing_meta)
            same_state           = existing_meta.get("state") == r.state if existing_meta else False
            same_domains         = existing_domains == requested_domains

            if file_exists and same_state and same_domains:
                # --- Case 1/2: same state + domains — reuse or append new crops ---
                if crops is None:
                    print(f"[INFO] Reusing existing pre-pipeline output: {norm_file}")
                    crops = pd.read_csv(norm_file)["Crop"].dropna().str.strip().unique().tolist()
                    print(f"[INFO] {len(crops)} crop(s) from cached pre-pipeline output")
                else:
                    missing_crops = [c for c in crops if c not in existing_crops_meta]
                    if not missing_crops:
                        # Case 1: all requested crops already present
                        print(f"[INFO] Reusing existing pre-pipeline output: {norm_file}")
                    else:
                        # Case 2: run pre-pipeline only for new crops and append
                        print(f"[INFO] {len(crops) - len(missing_crops)} crop(s) reused; "
                              f"running pre-pipeline for {len(missing_crops)} new crop(s): {', '.join(missing_crops)}")
                        intermediate = norm_file.parent / f"{norm_file.stem}_state_rows.csv"
                        run_state_filter(raw_file, r.state, intermediate, domains=r.domains or [])
                        fd2, tmp2 = tempfile.mkstemp(suffix='_extra.csv', dir=str(norm_file.parent))
                        os.close(fd2)
                        tmp2_path = Path(tmp2)
                        try:
                            run_crop_normalizer(intermediate, tmp2_path, missing_crops)
                            _df_extra = pd.read_csv(tmp2_path, low_memory=False)
                            if 'domain' not in _df_extra.columns and 'QueryType' in _df_extra.columns:
                                _df_extra.insert(12, 'domain', _df_extra['QueryType'])
                            _df_existing = pd.read_csv(norm_file, low_memory=False)
                            pd.concat([_df_existing, _df_extra], ignore_index=True).to_csv(norm_file, index=False)
                            print(f"[INFO] Appended {len(missing_crops)} new crop(s) to {norm_file}")
                        finally:
                            if tmp2_path.exists():
                                tmp2_path.unlink()
                        if intermediate.exists():
                            intermediate.unlink()
                        meta_path.write_text(json.dumps({
                            "state": r.state,
                            "domains": r.domains or [],
                            "crops": sorted(existing_crops_meta | set(missing_crops)),
                        }))
            else:
                # --- Case 3: domain/state changed — version up and run fresh ---
                if file_exists:
                    norm_file = _next_versioned_path(norm_file)
                    norm_file.parent.mkdir(parents=True, exist_ok=True)
                    meta_path = norm_file.with_suffix('.json')
                    print(f"[INFO] Domain/state change — new pre-pipeline output: {norm_file}")

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
                meta_path.write_text(json.dumps({
                    "state": r.state,
                    "domains": r.domains or [],
                    "crops": sorted(crops) if crops else [],
                }))
                _df_norm = pd.read_csv(norm_file, low_memory=False)
                if 'domain' not in _df_norm.columns and 'QueryType' in _df_norm.columns:
                    _df_norm.insert(12, 'domain', _df_norm['QueryType'])
                    _df_norm.to_csv(norm_file, index=False)
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
            _df_norm = pd.read_csv(norm_file, low_memory=False)
            if 'domain' not in _df_norm.columns and 'QueryType' in _df_norm.columns:
                _df_norm.insert(12, 'domain', _df_norm['QueryType'])
                _df_norm.to_csv(norm_file, index=False)

        effective_raw = str(norm_file)

    state_folder = Path(effective_raw).stem
    out_base     = _resolve_safe(r.output_dir) / state_folder

    # Skip crops whose full pipeline output already exists
    def _output_done(crop_slug: str) -> bool:
        d = out_base / crop_slug
        return (d / f"{out_base.name}_{crop_slug}.csv").exists() or (d / "dedup_faq.csv").exists()

    crops_to_run = [c for c in crops if not _output_done(slug(c))]
    skipped_crops = [c for c in crops if _output_done(slug(c))]
    if skipped_crops:
        print(f"[INFO] Skipping {len(skipped_crops)} already-completed crop(s): {', '.join(skipped_crops)}")
    print(f"[INFO] Found {len(crops_to_run)} unique crop(s): {', '.join(crops_to_run)}")

    failed = []
    for crop in crops_to_run:
        _job_ctl.check_cancel()
        (out_base / slug(crop)).mkdir(parents=True, exist_ok=True)

        cmd = [
            sys.executable, '-u', str(_RUN_PIPELINE),
            '--raw-file',   effective_raw,
            '--crop',       crop,
            '--model',      r.model,
            '--gpu-id',     str(r.gpu_id),
            '--batch-size', str(r.batch_size),
            '--grid-mode',  r.grid_mode,
            '--output-dir', str(_resolve_safe(r.output_dir)),
        ]
        if r.api_key:
            cmd += ['--api-key', r.api_key]
        if r.skip_qa_gen:
            cmd += ['--skip-qa-gen']

        print(f"[INFO] Starting pipeline for '{crop}'...")
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, preexec_fn=os.setsid, bufsize=1,
        )
        _job_ctl.register_proc(proc)
        for line in proc.stdout:
            print(line, end="", flush=True)
            # Race-condition fix: cancel() may have fired before register_proc();
            # kill the proc here if it's still running.
            if _job_ctl.is_cancelled(_job_ctl.current_job_id()):
                if proc.poll() is None:
                    try:
                        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    except Exception:
                        proc.kill()
                break
        proc.wait()
        _job_ctl.deregister_proc()

        # Unconditional check: raises JobCancelled whether subprocess was killed (-9)
        # or completed with returncode=0 just as the user clicked Stop.
        # This also prevents post_run_dedup from running after a stop.
        _job_ctl.check_cancel()

        if proc.returncode != 0:
            print(f"[WARN] Crop '{crop}' failed (returncode={proc.returncode})")
            failed.append(crop)
        elif not r.skip_post_pipeline:
            try:
                post_run_dedup(out_base, [crop])
            except Exception as exc:
                print(f"[WARN] Post-pipeline for '{crop}' failed: {exc}")

    if not r.skip_pre_pipeline and _norm_is_temp and norm_file.exists():
        norm_file.unlink()
        print("[INFO] Temporary pre-pipeline file removed from disk")

    # Update meta with cumulative completed crops
    if r.pre_output and not r.skip_pre_pipeline:
        try:
            cur_meta: dict = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        except Exception:
            cur_meta = {}
        newly_done = [c for c in crops_to_run if c not in failed]
        all_crops = sorted(set(cur_meta.get("crops", [])) | set(newly_done))
        meta_path.write_text(json.dumps({
            "state": r.state,
            "domains": r.domains or [],
            "crops": all_crops,
        }))

    if failed:
        raise RuntimeError(f"The following crops failed: {', '.join(failed)}")


# --- Route handlers ---

@router.post("/run/pre")
def run_pre(req: PreRequest, background: BackgroundTasks):
    return _submit(lambda: _run_pre_sync(req), background, "pre")


@router.post("/run/pipeline")
def run_pipeline(req: PipelineRequest, background: BackgroundTasks):
    return _submit(lambda: _run_pipeline_sync(req), background, "pipeline")


@router.post("/run/post")
def run_post(req: PostRequest, background: BackgroundTasks):
    return _submit(lambda: _run_post_sync(req), background, "post")


@router.post("/run/full")
def run_full(req: FullRequest, background: BackgroundTasks):
    return _submit(lambda: _run_full_sync(req), background, "full")
