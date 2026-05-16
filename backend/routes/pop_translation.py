import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

import _job_ctl
from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.common import POP_WORK_DIR, ROOT_DIR, _resolve_any_safe
from backend.jobs import _submit

router = APIRouter()


class PopRequest(BaseModel):
    state: str
    crop: str
    docs: Optional[List[str]] = None  # None = all PDFs in state/crop folder
    concurrency: int = 1


def _safe_name(name: str) -> str:
    """Reject path traversal in a single directory-name component."""
    if not name or "/" in name or "\\" in name or ".." in name or "\x00" in name:
        raise ValueError(f"invalid name: {name!r}")
    return name


@router.get("/pop/states")
def get_pop_states():
    data_dir = POP_WORK_DIR / "Data"
    if not data_dir.exists():
        return {"states": []}
    states = sorted(p.name for p in data_dir.iterdir() if p.is_dir())
    return {"states": states}


@router.get("/pop/crops")
def get_pop_crops(state: str):
    _safe_name(state)
    crop_dir = POP_WORK_DIR / "Data" / state
    if not crop_dir.exists():
        return {"crops": []}
    crops = sorted(p.name for p in crop_dir.iterdir() if p.is_dir())
    return {"crops": crops}


@router.get("/pop/docs")
def get_pop_docs(state: str, crop: str):
    _safe_name(state)
    _safe_name(crop)
    pdf_dir = POP_WORK_DIR / "Data" / state / crop
    if not pdf_dir.exists():
        return {"docs": []}
    docs = sorted(p.name for p in pdf_dir.iterdir() if p.is_file() and p.suffix.lower() == ".pdf")
    return {"docs": docs}


@router.get("/pop/data/tree")
def get_pop_data_tree():
    """
    Returns two kinds of entries under POP_Work/Data/:
    - Original PDFs at {state}/{crop}/{pdf_name} — shown inside the doc folder if processed
    - Output .docx files shown as 'output' directly under {state}/{crop}/{doc_name}/

    `path` is always relative to POP_Work/ (for downloads).
    `treePath` is a virtual path used by the frontend tree builder for display grouping.
    """
    data_dir = POP_WORK_DIR / "Data"
    if not data_dir.exists():
        return {"files": []}
    entries = []
    for state_dir in sorted(data_dir.iterdir()):
        if not state_dir.is_dir():
            continue
        for crop_dir in sorted(state_dir.iterdir()):
            if not crop_dir.is_dir():
                continue
            s, c = state_dir.name, crop_dir.name
            processed_stems = {d.name for d in crop_dir.iterdir() if d.is_dir()}

            # Original uploaded PDFs
            for pdf in sorted(crop_dir.glob("*.pdf")):
                if pdf.stem in processed_stems:
                    tree_path = f"{s}/{c}/{pdf.stem}/{pdf.name}"
                else:
                    tree_path = f"{s}/{c}/{pdf.name}"
                entries.append({
                    "name": pdf.name,
                    "path": str(pdf.relative_to(POP_WORK_DIR)),
                    "treePath": tree_path,
                    "size": pdf.stat().st_size,
                })

            # Output docs — flattened: shown directly under doc folder, no final_output level
            for doc_dir in sorted(crop_dir.iterdir()):
                if not doc_dir.is_dir():
                    continue
                final_output = doc_dir / "final_output"
                if not final_output.is_dir():
                    continue
                for docx in sorted(final_output.glob("*.docx")):
                    entries.append({
                        "name": docx.name,
                        "displayName": "output",
                        "path": str(docx.relative_to(POP_WORK_DIR)),
                        "treePath": f"{s}/{c}/{doc_dir.name}/output.docx",
                        "size": docx.stat().st_size,
                    })
    return {"files": entries}


@router.get("/pop/output/tree")
def get_pop_output_tree():
    """All .docx files under POP_Work/Workdir/ with paths relative to Workdir/."""
    workdir = POP_WORK_DIR / "Workdir"
    if not workdir.exists():
        return {"files": []}
    files = []
    for p in sorted(workdir.rglob("*.docx")):
        if p.is_file():
            files.append({
                "name": p.name,
                "path": str(p.relative_to(workdir)),
                "size": p.stat().st_size,
            })
    return {"files": files}


@router.post("/pop/upload")
async def upload_pop_file(dest: str = "", file: UploadFile = File(...)):
    """Upload a file into POP_Work/Data/[dest]/. dest is a subfolder path relative to Data/."""
    base = POP_WORK_DIR / "Data"
    if dest:
        try:
            save_dir = _resolve_any_safe(base, dest)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    else:
        save_dir = base
    save_dir.mkdir(parents=True, exist_ok=True)
    target = (save_dir / file.filename).resolve()
    if not target.is_relative_to(base.resolve()):
        raise HTTPException(status_code=400, detail="path escapes sandbox")
    content = await file.read()
    target.write_bytes(content)
    return {"uploaded": str(target.relative_to(base))}


@router.post("/pop/folders")
def create_pop_folder(body: dict):
    """Create a folder inside POP_Work/Data/. Body: {"path": "state/crop"}."""
    rel_path = body.get("path", "")
    if not rel_path:
        raise HTTPException(status_code=400, detail="path is required")
    try:
        target = _resolve_any_safe(POP_WORK_DIR / "Data", rel_path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    target.mkdir(parents=True, exist_ok=True)
    return {"created": rel_path}


@router.get("/pop/download/{path:path}")
def download_pop_file(path: str):
    """Download any file from POP_Work/ by relative path."""
    try:
        target = _resolve_any_safe(POP_WORK_DIR, path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not target.exists():
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(str(target), filename=target.name)


def _run_pop_sync(req: PopRequest) -> None:
    data_dir = POP_WORK_DIR / "Data" / req.state / req.crop
    workdir_base = POP_WORK_DIR / "Data" / req.state / req.crop
    prompt_file = ROOT_DIR / "POP-Translation" / "prompts" / "page_to_pdf.txt"
    script = ROOT_DIR / "POP-Translation" / "scripts" / "run_pop_to_docx.py"

    if not data_dir.exists():
        raise FileNotFoundError(f"Data directory not found: {data_dir}")
    if not script.exists():
        raise FileNotFoundError(f"POP translation script not found: {script}")

    if req.docs:
        pdfs = [data_dir / doc for doc in req.docs]
        missing = [str(p) for p in pdfs if not p.exists()]
        if missing:
            raise FileNotFoundError(f"PDFs not found: {missing}")
    else:
        pdfs = sorted(data_dir.glob("*.pdf"))
        if not pdfs:
            raise FileNotFoundError(f"No PDFs found in {data_dir}")

    env = {**os.environ}

    for pdf in pdfs:
        _job_ctl.check_cancel()
        doc_name = pdf.stem
        workdir = workdir_base / doc_name
        workdir.mkdir(parents=True, exist_ok=True)

        cmd = [
            sys.executable,
            str(script),
            "--source-pdf", str(pdf),
            "--workdir-root", str(workdir),
            "--doc-name", doc_name,
            "--prompt-file", str(prompt_file),
            "--concurrency", str(req.concurrency),
        ]
        print(f"\n[POP] Processing: {pdf.name}", flush=True)
        print(f"[POP] Workdir: {workdir}", flush=True)

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
        )
        _job_ctl.register_proc(proc)
        try:
            for line in proc.stdout:
                print(line, end="", flush=True)
        finally:
            proc.wait()
            _job_ctl.deregister_proc()

        if proc.returncode != 0 and not _job_ctl.is_cancelled(_job_ctl.current_job_id()):
            raise subprocess.CalledProcessError(proc.returncode, cmd)

    print(f"\n[POP] All documents processed for {req.state}/{req.crop}", flush=True)


@router.post("/run/pop")
def run_pop(req: PopRequest, background: BackgroundTasks):
    _safe_name(req.state)
    _safe_name(req.crop)
    return _submit(lambda: _run_pop_sync(req), background, "pop")
