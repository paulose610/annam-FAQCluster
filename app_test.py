#!/usr/bin/env python3
import asyncio
import json
import pickle
import sys
import threading
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, model_validator

ROOT_DIR = Path(__file__).resolve().parent
APP_DATA = ROOT_DIR / "app-data"
APP_DATA.mkdir(exist_ok=True)

app = FastAPI(title="FAQCluster API (mock)", redirect_slashes=False)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

jobs: dict[str, dict] = {}
_tl = threading.local()


class _JobStdout:
    """Same stdout proxy as real app — routes print() to job buffer."""
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


# ---------------------------------------------------------------------------
# Pydantic models — identical to app.py but with path validators removed
# ---------------------------------------------------------------------------

class PreRequest(BaseModel):
    input: str
    state: str
    crops: List[str]
    output: str
    keep_intermediate: bool = True


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
    model: str = "../models/qwen2.5-7b-instruct"
    api_key: Optional[str] = None
    gpu_id: int = 1
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


# ---------------------------------------------------------------------------
# Job runner — identical to app.py
# ---------------------------------------------------------------------------

async def _run_job(job_id: str, fn) -> None:
    jobs[job_id]["status"] = "running"
    loop = asyncio.get_running_loop()

    def _wrapped():
        _tl.job_id = job_id
        try:
            fn()
        finally:
            _tl.job_id = None

    try:
        await loop.run_in_executor(None, _wrapped)
        jobs[job_id]["status"] = "done"
        jobs[job_id]["stderr"] = ""
    except Exception:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["stderr"] = traceback.format_exc()


def _submit(fn, background: BackgroundTasks) -> dict:
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _crop_slug(crop: str) -> str:
    return crop.strip().lower().replace(" ", "_")


def _write_csv(path: Path, rows: list) -> None:
    import csv
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# Sample data used across all dummy files
# ---------------------------------------------------------------------------

_SAMPLE_QUERIES = [
    "गेहूं में सिंचाई कब करें",
    "धान की बुवाई का सही समय",
    "मक्का में खाद की मात्रा",
    "कपास में कीट प्रबंधन",
    "सोयाबीन रोग पहचान",
    "गेहूं में उर्वरक कितना डालें",
    "धान में पीला रोग कैसे ठीक करें",
    "मक्का की उन्नत किस्में कौन सी हैं",
    "गेहूं कटाई का सही समय",
    "सिंचाई की विधि बताएं",
]

_CLUSTER_LABELS = [
    "Irrigation timing",
    "Fertilizer dosage",
    "Pest control",
    "Variety selection",
    "Disease management",
]

_SAMPLE_QA = [
    {
        "Generated_Question": "When should wheat be irrigated for optimal yield?",
        "Generated_Category": "Agronomy",
        "Generated_Answer": (
            "Wheat requires 4-6 irrigations depending on soil type. Critical stages: crown root "
            "initiation (21 DAS), tillering (40-45 DAS), jointing (60-65 DAS), flowering (80-85 DAS), "
            "and grain filling (100-105 DAS). Apply 5-6 cm of water per irrigation. Avoid waterlogging "
            "as it causes yellowing and root rot."
        ),
    },
    {
        "Generated_Question": "What is the recommended fertilizer dose for wheat?",
        "Generated_Category": "Fertilizer and Nutrient",
        "Generated_Answer": (
            "For wheat, apply 120 kg N, 60 kg P2O5, and 40 kg K2O per hectare. Split nitrogen into "
            "two doses: half as basal and half at first irrigation. Use DAP or SSP as phosphorus source. "
            "Zinc deficiency is common — apply 25 kg ZnSO4/ha if deficient."
        ),
    },
    {
        "Generated_Question": "How to manage aphids and pests in wheat?",
        "Generated_Category": "Pest",
        "Generated_Answer": (
            "Wheat aphids cause significant yield loss. Monitor from December onwards. Economic threshold: "
            "10 aphids/tiller. Spray Imidacloprid 17.8 SL @ 150 ml/ha or Thiamethoxam 25 WG @ 100 g/ha. "
            "Yellow sticky traps help monitor population. Avoid excess nitrogen which promotes aphid build-up."
        ),
    },
    {
        "Generated_Question": "Which wheat varieties are suitable for Punjab?",
        "Generated_Category": "Variety",
        "Generated_Answer": (
            "Recommended varieties: HD 3086 (high yield, disease resistant), PBW 723 (semi-dwarf, rust "
            "resistant), DBW 187 (yellow rust resistant, 65-70 q/ha potential), WH 1105 (suitable for "
            "late sowing). Sow between November 1-15 for best results."
        ),
    },
    {
        "Generated_Question": "How to identify and control yellow rust in wheat?",
        "Generated_Category": "Disease",
        "Generated_Answer": (
            "Yellow rust (Puccinia striiformis) appears as yellow-orange pustules in parallel stripes on "
            "leaves. Favoured by cool temperatures (10-15°C) and high humidity. Control: Spray "
            "Propiconazole 25 EC @ 500 ml/ha or Tebuconazole 250 EW @ 750 ml/ha. Use resistant varieties."
        ),
    },
]


# ---------------------------------------------------------------------------
# Dummy file writers — one per pipeline stage
# ---------------------------------------------------------------------------

def _write_normalized_csv(path: Path, state: str, crops: List[str]) -> None:
    rows = [
        {
            "Query": _SAMPLE_QUERIES[i],
            "Crop": crops[i % len(crops)],
            "State": state,
            "Frequency": (10 - i) * 15,
        }
        for i in range(10)
    ]
    _write_csv(path, rows)


def _write_phase1_files(out_dir: Path, crop: str) -> None:
    (out_dir / "phase1_results.pkl").write_bytes(pickle.dumps([]))
    rows = [
        {
            "config": f"alpha{0.3 + i * 0.1:.1f}_mcs{5 + i}_ms3_nn15_nc5",
            "alpha": round(0.3 + i * 0.1, 1),
            "min_cluster_size": 5 + i,
            "min_samples": 3,
            "n_neighbors": 15,
            "n_components": 5,
            "n_clusters": 18 + i * 2,
            "noise_ratio": round(0.05 + i * 0.01, 3),
            "median_cluster_size": 12 - i,
            "mean_cluster_size": round(14.5 - i * 0.5, 1),
            "clusters_for_85pct": 8 + i,
            "coverage_efficiency": round(0.82 - i * 0.02, 3),
        }
        for i in range(5)
    ]
    _write_csv(out_dir / "phase1_candidates.csv", rows)


def _write_phase2_files(out_dir: Path) -> None:
    rows = [
        {
            "config": f"alpha{0.3 + i * 0.1:.1f}_mcs{5 + i}_ms3_nn15_nc5",
            "composite_score": round(0.91 - i * 0.03, 3),
        }
        for i in range(5)
    ]
    _write_csv(out_dir / "phase2_scores.csv", rows)


def _write_repair_files(out_dir: Path, crop: str) -> None:
    cluster_rows = [
        {
            "rank": i + 1,
            "cluster_id": i,
            "label": _CLUSTER_LABELS[i],
            "representative": _SAMPLE_QUERIES[i],
            "n_unique_questions": 8 - i,
            "query_volume": (5 - i) * 40,
            "pct_of_total": round((5 - i) * 8.0, 1),
            "was_split": False,
            "parent_cluster": "",
            "merged_from": "",
            "all_unique_questions": " | ".join(_SAMPLE_QUERIES[i:i + 2]),
        }
        for i in range(5)
    ]
    _write_csv(out_dir / "repaired_clusters.csv", cluster_rows)

    mapping_rows = [
        {
            "Query": _SAMPLE_QUERIES[i],
            "Crop": crop,
            "State": "Punjab",
            "Frequency": (10 - i) * 15,
            "raw_row_id": i,
            "final_cluster_id": i % 5,
            "cluster_label": _CLUSTER_LABELS[i % 5],
            "is_representative": i < 5,
        }
        for i in range(10)
    ]
    _write_csv(out_dir / "raw_row_mapping.csv", mapping_rows)

    cq_rows = [
        {
            "cluster_id": i % 5,
            "question": _SAMPLE_QUERIES[i],
            "is_representative": i < 5,
            "rank": (i % 5) + 1,
            "label": _CLUSTER_LABELS[i % 5],
            "representative": _SAMPLE_QUERIES[i % 5],
            "n_unique_questions": 8 - (i % 5),
            "query_volume": (5 - (i % 5)) * 40,
            "pct_of_total": round((5 - (i % 5)) * 8.0, 1),
            "was_split": False,
            "parent_cluster": "",
            "merged_from": "",
        }
        for i in range(10)
    ]
    _write_csv(out_dir / "cluster_questions.csv", cq_rows)


def _write_stage4_files(out_dir: Path) -> None:
    checkpoint = {
        str(i): [{"group_id": 1, "answer_label": _CLUSTER_LABELS[i], "indices": [i, i + 5]}]
        for i in range(5)
    }
    (out_dir / "unique_questions_checkpoint.json").write_text(
        json.dumps(checkpoint, ensure_ascii=False)
    )

    uq_rows = [
        {
            "unique_q_id": f"{i}_1",
            "cluster_id": i,
            "cluster_rank": i + 1,
            "cluster_label": _CLUSTER_LABELS[i],
            "group_id_in_cluster": 1,
            "answer_label": _CLUSTER_LABELS[i],
            "representative_question": _SAMPLE_QUERIES[i],
            "n_questions_in_group": 3 - (i % 2),
            "raw_frequency": (5 - i) * 40,
            "pct_of_cluster_volume": round(60.0 + i * 5, 1),
            "was_cluster_split": False,
            "parent_cluster": "",
            "merged_from": "",
            "merged_cross_cluster": False,
        }
        for i in range(5)
    ]
    _write_csv(out_dir / "unique_questions.csv", uq_rows)
    _write_csv(out_dir / "unique_questions_freq.csv", uq_rows)

    mapping_rows = [
        {
            "unique_q_id": f"{i % 5}_1",
            "cluster_id": i % 5,
            "question": _SAMPLE_QUERIES[i],
            "raw_freq_individual": (10 - i) * 5,
            "is_representative": i < 5,
            "rank": (i % 5) + 1,
            "cluster_label": _CLUSTER_LABELS[i % 5],
            "representative": _SAMPLE_QUERIES[i % 5],
            "n_unique_questions": 8 - (i % 5),
            "query_volume": (5 - (i % 5)) * 40,
            "pct_of_total": round((5 - (i % 5)) * 8.0, 1),
            "was_split": False,
            "parent_cluster": "",
            "merged_from": "",
        }
        for i in range(10)
    ]
    _write_csv(out_dir / "unique_question_mapping.csv", mapping_rows)

    _write_csv(out_dir / "unique_questions_verification.csv", [{
        "total_raw_rows": 1200,
        "sum_group_frequencies": 1180,
        "noise_rows": 20,
        "freq_check_pass": True,
        "n_input_questions": 10,
        "n_unique_answer_groups": 5,
        "reduction_ratio": 0.5,
        "avg_answers_per_cluster": 1.0,
    }])


def _write_stage6_files(out_dir: Path) -> None:
    _write_csv(out_dir / "corpus_filtered_out.csv", [{
        "unique_q_id": "99_1",
        "cluster_id": 99,
        "cluster_rank": 99,
        "cluster_label": "Irrelevant",
        "group_id_in_cluster": 1,
        "answer_label": "Off-topic query",
        "representative_question": "किसान क्रेडिट कार्ड कैसे बनाएं",
        "n_questions_in_group": 1,
        "raw_frequency": 5,
        "pct_of_cluster_volume": 100.0,
        "was_cluster_split": False,
        "parent_cluster": "",
        "merged_from": "",
        "merged_cross_cluster": False,
    }])


def _write_stage7_files(out_dir: Path) -> None:
    rows = [
        {
            "unique_q_id": f"{i}_1",
            "cluster_id": i,
            "cluster_rank": i + 1,
            "cluster_label": _CLUSTER_LABELS[i],
            "group_id_in_cluster": 1,
            "answer_label": _CLUSTER_LABELS[i],
            "representative_question": _SAMPLE_QUERIES[i],
            "n_questions_in_group": 3 - (i % 2),
            "raw_frequency": (5 - i) * 40,
            "pct_of_cluster_volume": round(60.0 + i * 5, 1),
            "was_cluster_split": False,
            "parent_cluster": "",
            "merged_from": "",
            "merged_cross_cluster": False,
            **_SAMPLE_QA[i],
        }
        for i in range(5)
    ]
    _write_csv(out_dir / "unique_questions_freq_qa.csv", rows)


def _write_post_files(final_dir: Path, slugs: list) -> None:
    final_dir.mkdir(parents=True, exist_ok=True)
    for slug in slugs:
        faq_rows = [
            {
                "unique_q_id": f"{i}_1",
                "cluster_id": i,
                "cluster_rank": i + 1,
                "cluster_label": _CLUSTER_LABELS[i],
                "group_id_in_cluster": 1,
                "answer_label": _CLUSTER_LABELS[i],
                "representative_question": _SAMPLE_QUERIES[i],
                "n_questions_in_group": 3 - (i % 2),
                "raw_frequency": (5 - i) * 40,
                "pct_of_cluster_volume": round(60.0 + i * 5, 1),
                "was_cluster_split": False,
                "parent_cluster": "",
                "merged_from": "",
                "merged_cross_cluster": False,
                **_SAMPLE_QA[i],
            }
            for i in range(5)
        ]
        _write_csv(final_dir / f"{slug}_faq.csv", faq_rows)

        phase_rows = [
            {
                "representative_question": _SAMPLE_QUERIES[i],
                "phase_1": _SAMPLE_QUERIES[(i + 1) % 10],
                "false_positive": "",
                "phase_2": _SAMPLE_QUERIES[(i + 1) % 10] if i < 3 else "",
            }
            for i in range(5)
        ]
        _write_csv(final_dir / f"phase_data_{slug}_faq.csv", phase_rows)

        dedup_rows = [
            {
                "unique_q_id": f"{i}_1",
                "cluster_id": i,
                "cluster_rank": i + 1,
                "cluster_label": _CLUSTER_LABELS[i],
                "group_id_in_cluster": 1,
                "answer_label": _CLUSTER_LABELS[i],
                "representative_question": _SAMPLE_QUERIES[i],
                "n_questions_in_group": 3 - (i % 2),
                "raw_frequency": (5 - i) * 40 + 5,  # aggregated
                "pct_of_cluster_volume": round(60.0 + i * 5, 1),
                "was_cluster_split": False,
                "parent_cluster": "",
                "merged_from": "",
                "merged_cross_cluster": False,
                **_SAMPLE_QA[i],
            }
            for i in range(5)
        ]
        _write_csv(final_dir / f"dedup_{slug}_faq.csv", dedup_rows)


# ---------------------------------------------------------------------------
# Mock sync runners (called in ThreadPoolExecutor — use time.sleep, not asyncio)
# ---------------------------------------------------------------------------

def _mock_pre_sync(r: PreRequest) -> None:
    print(f"[Pre] Filtering rows for state '{r.state}'...")
    time.sleep(1)
    output_path = APP_DATA / r.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_normalized_csv(output_path, r.state, r.crops)
    print(f"[Pre] State filter done — 1,200 rows retained.")
    time.sleep(1)
    print(f"[Pre] Crop normalisation done — crops: {', '.join(r.crops)}")
    print(f"[Pre] Output written: {r.output}")


def _mock_pipeline_sync(r: PipelineRequest) -> None:
    state_folder = Path(r.raw_file).stem
    out_base = APP_DATA / r.output_dir / state_folder
    failed = []

    for crop in r.crops:
        slug = _crop_slug(crop)
        out_dir = out_base / slug
        out_dir.mkdir(parents=True, exist_ok=True)

        try:
            print(f"[{crop}] Phase 1: Hyperparameter screening...")
            time.sleep(1)
            _write_phase1_files(out_dir, crop)
            time.sleep(2)
            print(f"[{crop}] Phase 1 done — 24 candidate configs evaluated.")

            print(f"[{crop}] Phase 2: LLM cluster evaluation...")
            time.sleep(1)
            _write_phase2_files(out_dir)
            time.sleep(2)
            print(f"[{crop}] Phase 2 done — best config: alpha=0.5, mcs=7.")

            print(f"[{crop}] Stage 3: Cluster repair (Steps A–E)...")
            time.sleep(1)
            _write_repair_files(out_dir, crop)
            time.sleep(2)
            print(f"[{crop}] Repair done — 18 clusters, 2 splits, 1 merge.")

            print(f"[{crop}] Stage 4: Unique question extraction...")
            time.sleep(1)
            _write_stage4_files(out_dir)
            time.sleep(1)
            print(f"[{crop}] Extraction done — 5 unique answer groups.")

            print(f"[{crop}] Stage 5: Deduplication...")
            time.sleep(1)
            print(f"[{crop}] Dedup done — 0 duplicates removed.")

            print(f"[{crop}] Stage 6: Corpus filter...")
            time.sleep(1)
            _write_stage6_files(out_dir)
            print(f"[{crop}] Corpus filter done — 1 irrelevant question removed.")

            print(f"[{crop}] Stage 7: Q&A generation...")
            time.sleep(1)
            _write_stage7_files(out_dir)
            time.sleep(2)
            print(f"[{crop}] Q&A generation done — 5 FAQ pairs written.")
            print(f"[{crop}] All stages complete. Output: {r.output_dir}/{state_folder}/{slug}/")

        except Exception as exc:
            print(f"[WARN] Crop '{crop}' failed: {exc}")
            failed.append(crop)

    if failed:
        raise RuntimeError(f"The following crops failed: {', '.join(failed)}")


def _mock_post_sync(r: PostRequest) -> None:
    input_dir = APP_DATA / r.input

    # Walk state subfolders under input_dir, collect QA files per state
    state_dirs = [d for d in input_dir.iterdir() if d.is_dir()] if input_dir.exists() else []

    total_crops = 0
    for state_dir in state_dirs:
        qa_files = list(state_dir.rglob("unique_questions_freq_qa.csv"))
        if not qa_files:
            continue
        slugs = [f.parent.name for f in qa_files]
        final_dir = APP_DATA / "final" / state_dir.name
        print(f"[Post] Collecting {len(slugs)} crop(s) for state '{state_dir.name}': {', '.join(slugs)}...")
        _write_post_files(final_dir, slugs)
        total_crops += len(slugs)

    if not state_dirs:
        # fallback if no pipeline has run yet
        final_dir = APP_DATA / "final" / "sample_state"
        _write_post_files(final_dir, ["wheat", "rice"])
        total_crops = 2

    time.sleep(2)
    print(f"[Post] Collect done — {total_crops} crop(s) collected into final/{{state}}/")
    print(f"[Post] LLM cross-crop deduplication...")
    time.sleep(2)
    print(f"[Post] Dedup done — final FAQ files ready in app-data/final/")


def _mock_full_sync(r: FullRequest) -> None:
    crops = r.crops or ["wheat", "rice"]

    # Pre
    if not r.skip_pre_pipeline:
        state_slug = r.state.strip().lower().replace(" ", "_")
        norm_file = f"data/{state_slug}_norm.csv"
        print(f"[Full/Pre] Filtering for state '{r.state}', normalising crops...")
        time.sleep(1)
        output_path = APP_DATA / norm_file
        output_path.parent.mkdir(parents=True, exist_ok=True)
        _write_normalized_csv(output_path, r.state, crops)
        print(f"[Full/Pre] Pre-pipeline done — normalized file: {norm_file}")
        effective_raw = norm_file
    else:
        effective_raw = r.raw_file

    # Per-crop pipeline
    state_folder = Path(effective_raw).stem
    out_base = APP_DATA / r.output_dir / state_folder
    failed = []

    for crop in crops:
        slug = _crop_slug(crop)
        out_dir = out_base / slug
        out_dir.mkdir(parents=True, exist_ok=True)
        try:
            print(f"[Full/{crop}] Running all 7 pipeline stages...")
            time.sleep(1)
            _write_phase1_files(out_dir, crop)
            time.sleep(1)
            _write_phase2_files(out_dir)
            time.sleep(1)
            _write_repair_files(out_dir, crop)
            time.sleep(1)
            _write_stage4_files(out_dir)
            time.sleep(1)
            _write_stage6_files(out_dir)
            time.sleep(1)
            _write_stage7_files(out_dir)
            time.sleep(1)
            print(f"[Full/{crop}] Done.")
        except Exception as exc:
            print(f"[WARN] Crop '{crop}' failed: {exc}")
            failed.append(crop)

    # Post
    if not r.skip_post_pipeline:
        done_slugs = [_crop_slug(c) for c in crops if c not in failed]
        final_dir = APP_DATA / "final" / state_folder
        print(f"[Full/Post] Collecting and deduplicating {len(done_slugs)} crop(s)...")
        time.sleep(1)
        _write_post_files(final_dir, done_slugs)
        time.sleep(2)
        print(f"[Full/Post] Done — final FAQ files in final/{state_folder}/")

    if failed:
        raise RuntimeError(f"The following crops failed: {', '.join(failed)}")


# ---------------------------------------------------------------------------
# Endpoints — identical paths/methods to app.py
# ---------------------------------------------------------------------------

@app.get("/")
def health():
    return {"status": "ok"}


@app.post("/run/pre")
def run_pre(req: PreRequest, background: BackgroundTasks):
    return _submit(lambda: _mock_pre_sync(req), background)


@app.post("/run/pipeline")
def run_pipeline(req: PipelineRequest, background: BackgroundTasks):
    return _submit(lambda: _mock_pipeline_sync(req), background)


@app.post("/run/post")
def run_post(req: PostRequest, background: BackgroundTasks):
    return _submit(lambda: _mock_post_sync(req), background)


@app.post("/run/full")
def run_full(req: FullRequest, background: BackgroundTasks):
    return _submit(lambda: _mock_full_sync(req), background)


@app.get("/jobs")
def list_jobs():
    return list(jobs.values())


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@app.get("/files/download/{path:path}")
def download_any(path: str):
    """Download any file from app-data by its relative path."""
    target = (APP_DATA / path).resolve()
    if not target.is_relative_to(APP_DATA.resolve()):
        raise HTTPException(status_code=400, detail="invalid path")
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

    # All CSVs in app-data except under outputs/ and final/
    all_csvs = []
    if APP_DATA.exists():
        for p in APP_DATA.rglob("*.csv"):
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

    # unique_questions_freq_qa.csv files in outputs/repair/{state}/{crop}/
    crop_qa_files = []
    if repair_dir.exists():
        for qa_file in sorted(repair_dir.rglob("unique_questions_freq_qa.csv")):
            crop_slug = qa_file.parent.name
            state_name = qa_file.parent.parent.name
            entry = _file_entry(qa_file)
            entry["crop"] = crop_slug
            entry["state"] = state_name
            crop_qa_files.append(entry)

    # All CSVs in app-data/final/{state}/
    final_csvs = []
    if final_root.exists():
        for p in sorted(final_root.rglob("*.csv")):
            state_name = p.parent.name
            entry = _file_entry(p)
            entry["state"] = state_name
            final_csvs.append(entry)

    return {
        "all_csvs": all_csvs,
        "crop_qa_files": crop_qa_files,
        "final_csvs": final_csvs,
    }
