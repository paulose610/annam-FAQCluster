import argparse
import os
import shutil
import tempfile
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel, field_validator, model_validator

from backend.common import APP_DATA, _resolve_safe
from backend.jobs import _submit

router = APIRouter()


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
    from run_pipeline import (
        run_phase1, run_phase2, run_repair,
        run_unique_questions, run_dedup, run_corpus_filter, run_qa_gen,
        load_candidates, load_best_cfg, slug,
        DEFAULT_CORPUS,
    )
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

    state_folder = Path(effective_raw).stem
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

    if not r.skip_post_pipeline:
        post_run_dedup(out_base, crops)

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
