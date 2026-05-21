import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional

import _job_ctl
from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.common import POP_WORK_DIR, ROOT_DIR, _resolve_any_safe
from backend.jobs import _submit

_CHUNK_TMP = Path(tempfile.gettempdir()) / "faq_chunks"

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
    Recursively scans POP_Work/Data/ at any depth.
    - PDFs: shown at their actual location; if a same-stem subdir exists they're
      nested one level deeper (showing the processed-doc virtual folder).
    - .docx files inside final_output/ subdirs are shown as 'output' entries.
    `path` is always relative to POP_Work/ (for downloads).
    `treePath` is a virtual path used by the frontend tree builder.
    """
    data_dir = POP_WORK_DIR / "Data"
    if not data_dir.exists():
        return {"files": []}
    entries = []

    def scan(directory: Path) -> None:
        subdirs = [d for d in sorted(directory.iterdir()) if d.is_dir() and not d.name.startswith('.')]
        processed_stems = {d.name for d in subdirs}
        for pdf in sorted(directory.glob("*.pdf")):
            rel = pdf.relative_to(data_dir)
            if pdf.stem in processed_stems:
                tree_path = str(rel.parent / pdf.stem / pdf.name)
            else:
                tree_path = str(rel)
            entries.append({
                "name": pdf.name,
                "path": str(pdf.relative_to(POP_WORK_DIR)),
                "treePath": tree_path,
                "size": pdf.stat().st_size,
            })
        for sub in subdirs:
            final_output = sub / "final_output"
            if final_output.is_dir():
                rel_sub = sub.relative_to(data_dir)
                for docx in sorted(final_output.glob("*.docx")):
                    entries.append({
                        "name": docx.name,
                        "displayName": "output",
                        "path": str(docx.relative_to(POP_WORK_DIR)),
                        "treePath": str(rel_sub / "output.docx"),
                        "size": docx.stat().st_size,
                    })
            else:
                before = len(entries)
                scan(sub)
                if len(entries) == before:
                    # Subdir is empty — emit it so user can upload into it
                    rel_sub = sub.relative_to(data_dir)
                    entries.append({
                        "name": sub.name,
                        "path": str(sub.relative_to(POP_WORK_DIR)),
                        "treePath": str(rel_sub),
                        "size": 0,
                        "isDir": True,
                    })

    for state_dir in sorted(data_dir.iterdir()):
        if state_dir.is_dir() and not state_dir.name.startswith('.'):
            before = len(entries)
            scan(state_dir)
            if len(entries) == before:
                entries.append({
                    "name": state_dir.name,
                    "path": str(state_dir.relative_to(POP_WORK_DIR)),
                    "treePath": state_dir.name,
                    "size": 0,
                    "isDir": True,
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


@router.post("/pop/upload-chunk")
async def upload_pop_file_chunk(
    request: Request,
    upload_id: str,
    chunk_index: int,
    total_chunks: int,
    filename: str,
    dest: str = "",
):
    """Receive one raw-binary chunk; assemble file when all chunks arrive."""
    base = POP_WORK_DIR / "Data"
    tmp_dir = _CHUNK_TMP / upload_id
    tmp_dir.mkdir(parents=True, exist_ok=True)
    (tmp_dir / f"{chunk_index:06d}").write_bytes(await request.body())

    if not all((tmp_dir / f"{i:06d}").exists() for i in range(total_chunks)):
        return {"chunk": chunk_index, "total": total_chunks}

    try:
        save_dir = _resolve_any_safe(base, dest) if dest else base
    except ValueError as e:
        shutil.rmtree(tmp_dir)
        raise HTTPException(status_code=400, detail=str(e))
    save_dir.mkdir(parents=True, exist_ok=True)
    target = (save_dir / filename).resolve()
    if not target.is_relative_to(base.resolve()):
        shutil.rmtree(tmp_dir)
        raise HTTPException(status_code=400, detail="path escapes sandbox")

    with target.open("wb") as f:
        for i in range(total_chunks):
            f.write((tmp_dir / f"{i:06d}").read_bytes())
    shutil.rmtree(tmp_dir)
    return {"uploaded": str(target.relative_to(base))}


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


@router.delete("/pop/files/{path:path}")
def delete_pop_file(path: str):
    """Delete a file from POP_Work/ by relative path."""
    try:
        target = _resolve_any_safe(POP_WORK_DIR, path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not target.exists():
        raise HTTPException(status_code=404, detail="file not found")
    if target.is_dir():
        raise HTTPException(status_code=400, detail="path is a directory")
    target.unlink()
    return {"deleted": path}


@router.delete("/pop/folders/{path:path}")
def delete_pop_folder(path: str):
    """Delete a folder (and contents) from POP_Work/ by relative path."""
    try:
        target = _resolve_any_safe(POP_WORK_DIR, path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not target.exists():
        raise HTTPException(status_code=404, detail="folder not found")
    if not target.is_dir():
        raise HTTPException(status_code=400, detail="path is not a directory")
    shutil.rmtree(target)
    return {"deleted": path}


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

    print(f"[POP] Total docs: {len(pdfs)}", flush=True)
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

        final_dir = workdir / "final_output"
        if final_dir.is_dir() and sorted(final_dir.glob("*.docx")):
            meta_path = workdir / "meta.json"
            existing = {"download": False, "audit": False}
            if meta_path.exists():
                try:
                    existing = json.loads(meta_path.read_text())
                except Exception:
                    pass
            meta_path.write_text(json.dumps(existing))

    print(f"\n[POP] All documents processed for {req.state}/{req.crop}", flush=True)


@router.get("/pop/state-table")
def get_pop_state_table():
    """
    Return flat table of POP docs.

    Scans POP_Work/Data/{state}/{crop}/ for PDF files.
    For each PDF, checks for a matching processed folder {doc_stem}/final_output/*.docx.
    Paths are relative to POP_Work/ (use /pop/download/{path} to fetch them).
    """
    data_dir = POP_WORK_DIR / "Data"
    rows = []
    if not data_dir.exists():
        return {"rows": rows}
    for state_dir in sorted(data_dir.iterdir()):
        if not state_dir.is_dir() or state_dir.name.startswith('.'):
            continue
        crop_dirs = [d for d in sorted(state_dir.iterdir()) if d.is_dir() and not d.name.startswith('.')]
        if not crop_dirs:
            rows.append({
                "state": state_dir.name,
                "crop": None,
                "doc_name": None,
                "doc_path": None,
                "output_path": None,
                "audit_file": None,
                "processed": False,
                "downloaded": False,
                "audited": False,
                "is_empty": True,
            })
            continue
        for crop_dir in crop_dirs:
            pdfs = sorted(crop_dir.glob("*.pdf"))
            if not pdfs:
                rows.append({
                    "state": state_dir.name,
                    "crop": crop_dir.name,
                    "doc_name": None,
                    "doc_path": None,
                    "output_path": None,
                    "audit_file": None,
                    "processed": False,
                    "downloaded": False,
                    "audited": False,
                    "is_empty": True,
                })
            else:
                for pdf in pdfs:
                    doc_stem = pdf.stem
                    doc_folder = crop_dir / doc_stem
                    final_dir = doc_folder / "final_output"
                    output_path = None
                    audit_file = None
                    processed = final_dir.is_dir()
                    downloaded = False
                    audited = False
                    if processed:
                        meta_path = doc_folder / "meta.json"
                        if meta_path.exists():
                            try:
                                m = json.loads(meta_path.read_text())
                                downloaded = bool(m.get("download", False))
                                audited = bool(m.get("audit", False))
                            except Exception:
                                pass
                        if final_dir.is_dir():
                            docx_list = sorted(final_dir.glob("*.docx"))
                            if docx_list:
                                output_path = str(docx_list[0].relative_to(POP_WORK_DIR))
                            for f in sorted(final_dir.iterdir()):
                                if f.name.startswith("audit_"):
                                    audit_file = str(f.relative_to(POP_WORK_DIR))
                                    break
                    rows.append({
                        "state": state_dir.name,
                        "crop": crop_dir.name,
                        "doc_name": pdf.name,
                        "doc_path": str(pdf.relative_to(POP_WORK_DIR)),
                        "output_path": output_path,
                        "audit_file": audit_file,
                        "processed": processed,
                        "downloaded": downloaded,
                        "audited": audited,
                        "is_empty": False,
                    })
    return {"rows": rows}


@router.get("/pop/output")
def download_pop_output(state: str, crop: str, doc_name: str):
    """Serve the translated DOCX for a doc and mark it downloaded in meta.json."""
    _safe_name(state)
    _safe_name(crop)
    doc_stem = Path(doc_name).stem
    final_dir = POP_WORK_DIR / "Data" / state / crop / doc_stem / "final_output"
    docx_list = sorted(final_dir.glob("*.docx")) if final_dir.is_dir() else []
    if not docx_list:
        raise HTTPException(status_code=404, detail="output not found")
    meta_path = POP_WORK_DIR / "Data" / state / crop / doc_stem / "meta.json"
    meta = {"download": False, "audit": False}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text())
        except Exception:
            pass
    meta["download"] = True
    meta_path.write_text(json.dumps(meta))
    return FileResponse(str(docx_list[0]), filename=docx_list[0].name)


@router.post("/pop/upload-audited")
async def upload_pop_audited(
    state: str = Form(...),
    crop: str = Form(...),
    doc_name: str = Form(...),
    file: UploadFile = File(...),
):
    """Upload an audited file for a POP doc; stored in final_output/ with audit_ prefix."""
    _safe_name(state)
    _safe_name(crop)
    doc_stem = Path(doc_name).stem
    final_output_dir = POP_WORK_DIR / "Data" / state / crop / doc_stem / "final_output"
    final_output_dir.mkdir(parents=True, exist_ok=True)
    target = final_output_dir / f"audit_{file.filename}"
    target.write_bytes(await file.read())
    meta_path = POP_WORK_DIR / "Data" / state / crop / doc_stem / "meta.json"
    meta = {"download": False, "audit": False}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text())
        except Exception:
            pass
    meta["audit"] = True
    meta_path.write_text(json.dumps(meta))
    return {"uploaded": str(target.relative_to(POP_WORK_DIR))}


@router.post("/run/pop")
def run_pop(req: PopRequest, background: BackgroundTasks):
    _safe_name(req.state)
    _safe_name(req.crop)
    return _submit(lambda: _run_pop_sync(req), background, "pop")
