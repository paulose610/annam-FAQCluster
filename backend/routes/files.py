import json
import re
import shutil
import tempfile
from pathlib import Path
from typing import List

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, field_validator

from backend.common import APP_DATA, _resolve_safe

_CHUNK_TMP = Path(tempfile.gettempdir()) / "faq_chunks"

router = APIRouter()


class RenameRequest(BaseModel):
    to: str

    @field_validator("to")
    @classmethod
    def _safe_to(cls, v: str) -> str:
        _resolve_safe(v)
        return v


@router.get("/files/download/{path:path}")
def download_file(path: str):
    target = _resolve_safe(path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(str(target), filename=target.name)


@router.get("/files/tree")
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
    # Directories that contain at least one CSV (used to find empty dirs below)
    csv_ancestor_dirs: set[Path] = set()
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
            for ancestor in p.parents:
                if ancestor == APP_DATA:
                    break
                csv_ancestor_dirs.add(ancestor)
    all_csvs.sort(key=lambda e: e["path"])

    # Emit empty directories so users can upload into them
    def _add_empty_dirs(d: Path) -> None:
        if ".ipynb_checkpoints" in d.parts or d.name.startswith('.'):
            return
        try:
            d.relative_to(outputs_dir)
            return
        except ValueError:
            pass
        try:
            d.relative_to(final_root)
            return
        except ValueError:
            pass
        if d not in csv_ancestor_dirs:
            # No CSV descendants — show as an empty folder
            all_csvs.append({
                "name": d.name,
                "path": str(d.relative_to(APP_DATA)),
                "size": 0,
                "isDir": True,
            })
        else:
            for sub in sorted(d.iterdir()):
                if sub.is_dir():
                    _add_empty_dirs(sub)

    if APP_DATA.exists():
        for d in sorted(APP_DATA.iterdir()):
            if d.is_dir():
                _add_empty_dirs(d)

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
            for crop_dir in sorted(state_dir.iterdir()):
                if not crop_dir.is_dir() or crop_dir.name == 'final':
                    continue
                for p in sorted(crop_dir.iterdir()):
                    if not p.is_file():
                        continue
                    if p.name.startswith("dedup_") or p.name.startswith("phase_"):
                        entry = _file_entry(p)
                        entry["state"] = state_dir.name
                        entry["crop"] = crop_dir.name
                        entry["folderPath"] = str(crop_dir.relative_to(APP_DATA))
                        final_csvs.append(entry)

    return {
        "all_csvs": all_csvs,
        "crop_qa_files": crop_qa_files,
        "final_csvs": final_csvs,
    }


@router.delete("/files/{path:path}")
def delete_file(path: str):
    target = _resolve_safe(path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="file not found")
    if target.is_dir():
        raise HTTPException(status_code=400, detail="path is a directory")
    target.unlink()
    parent = target.parent
    name = target.name
    for prefix in ("dedup_", "phase_"):
        if name.startswith(prefix):
            base = parent / name[len(prefix):]
            if base.exists() and base.is_file():
                base.unlink()
            break
    return {"deleted": path}


@router.delete("/folders/{path:path}")
def delete_folder(path: str):
    target = _resolve_safe(path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="folder not found")
    if not target.is_dir():
        raise HTTPException(status_code=400, detail="path is not a directory")
    shutil.rmtree(target)
    return {"deleted": path}


@router.post("/files/rename/{path:path}")
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


@router.post("/files/folders")
def create_folder(body: dict):
    """Create a folder inside app-data. Body: {"path": "relative/path"}."""
    rel_path = body.get("path", "")
    if not rel_path:
        raise HTTPException(status_code=400, detail="path is required")
    target = _resolve_safe(rel_path)
    target.mkdir(parents=True, exist_ok=True)
    return {"created": rel_path}


@router.post("/files/upload-chunk")
async def upload_file_chunk(
    request: Request,
    upload_id: str,
    chunk_index: int,
    total_chunks: int,
    filename: str,
    dest: str = "",
):
    """Receive one raw-binary chunk; assemble file when all chunks arrive."""
    tmp_dir = _CHUNK_TMP / upload_id
    tmp_dir.mkdir(parents=True, exist_ok=True)
    (tmp_dir / f"{chunk_index:06d}").write_bytes(await request.body())

    if not all((tmp_dir / f"{i:06d}").exists() for i in range(total_chunks)):
        return {"chunk": chunk_index, "total": total_chunks}

    save_dir = _resolve_safe(dest) if dest else APP_DATA
    save_dir.mkdir(parents=True, exist_ok=True)
    target = (save_dir / filename).resolve()
    if not target.is_relative_to(APP_DATA.resolve()):
        shutil.rmtree(tmp_dir)
        raise HTTPException(status_code=400, detail="path escapes sandbox")

    with target.open("wb") as f:
        for i in range(total_chunks):
            f.write((tmp_dir / f"{i:06d}").read_bytes())
    shutil.rmtree(tmp_dir)
    return {"uploaded": str(target.relative_to(APP_DATA))}


@router.post("/files/upload")
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


@router.get("/app/next-state")
def get_next_state(state: str = "", domains: List[str] = Query(default=[])):
    slug = re.sub(r"[^a-z0-9]+", "_", state.lower()).strip("_") if state else "state"
    pattern = re.compile(rf"^{re.escape(slug)}_(\d+)$")
    sorted_domains = sorted(domains)

    existing: list[tuple[int, Path]] = []
    if APP_DATA.exists():
        for p in APP_DATA.iterdir():
            m = pattern.match(p.name)
            if m and p.is_dir():
                existing.append((int(m.group(1)), p))

    # Return existing folder if it has matching domains
    for idx, folder in sorted(existing):
        meta_path = folder / "meta.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text())
                if sorted(meta.get("domains", [])) == sorted_domains:
                    return {
                        "name": folder.name,
                        "is_new": False,
                        "existing_crops": meta.get("crops", []),
                    }
            except Exception:
                pass

    next_idx = max((i for i, _ in existing), default=-1) + 1
    return {
        "name": f"{slug}_{next_idx}",
        "is_new": True,
        "existing_crops": [],
    }


@router.get("/app/state-table")
def get_state_table():
    """
    Flat rows: one per (state_folder, crop).
    Columns: state, crop, domains, output_file, audit_file.
    """
    import json
    repair_dir = APP_DATA / "outputs" / "repair"
    rows = []

    if not repair_dir.exists():
        return {"rows": rows}

    for state_dir in sorted(repair_dir.iterdir()):
        if not state_dir.is_dir():
            continue
        state_name = state_dir.name

        # Domains from meta.json written by pre-pipeline
        domains: list[str] = []
        meta_path = APP_DATA / state_name / "meta.json"
        if meta_path.exists():
            try:
                domains = json.loads(meta_path.read_text()).get("domains", [])
            except Exception:
                pass

        for crop_dir in sorted(state_dir.iterdir()):
            if not crop_dir.is_dir() or crop_dir.name == "final":
                continue

            dedup = crop_dir / f"{state_name}_{crop_dir.name}.csv"
            if not dedup.exists():
                dedup = crop_dir / "dedup_faq.csv"
            output_file = str(dedup.relative_to(APP_DATA)) if dedup.exists() else None

            audit_file = None
            for f in sorted(crop_dir.iterdir()):
                if f.name.startswith("audit_") and f.suffix == ".csv":
                    audit_file = str(f.relative_to(APP_DATA))
                    break

            crop_meta = {"download": False, "audit": False}
            crop_meta_path = crop_dir / "meta.json"
            if crop_meta_path.exists():
                try:
                    crop_meta = json.loads(crop_meta_path.read_text())
                except Exception:
                    pass
            elif output_file:
                crop_meta_path.write_text(json.dumps(crop_meta))

            rows.append({
                "state": state_name,
                "crop": crop_dir.name,
                "domains": domains,
                "output_file": output_file,
                "audit_file": audit_file,
                "downloaded": crop_meta.get("download", False),
                "audited": crop_meta.get("audit", False),
            })

    return {"rows": rows}


@router.get("/app/output/{state}/{crop}")
def download_output(state: str, crop: str):
    """Download the output CSV for a state/crop, named {state}_{crop}.csv, and mark it downloaded."""
    crop_dir = _resolve_safe(f"outputs/repair/{state}/{crop}")
    dedup = crop_dir / f"{state}_{crop}.csv"
    if not dedup.exists():
        dedup = crop_dir / "dedup_faq.csv"
    if not dedup.exists():
        raise HTTPException(status_code=404, detail="output not found")
    meta_path = crop_dir / "meta.json"
    meta = {"download": False, "audit": False}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text())
        except Exception:
            pass
    meta["download"] = True
    meta_path.write_text(json.dumps(meta))
    return FileResponse(str(dedup), filename=f"{state}_{crop}.csv")


def _csv_slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


@router.post("/files/upload-audited")
async def upload_audited(
    state: str = Form(...),
    crop: str = Form(...),
    file: UploadFile = File(...),
):
    """Upload an audited CSV for a specific state/crop."""
    target = _resolve_safe(f"outputs/repair/{state}/{crop}/audit_{file.filename}")
    if not target.parent.exists():
        raise HTTPException(status_code=404, detail="crop folder not found")
    content = await file.read()
    target.write_bytes(content)

    meta_path = target.parent / "meta.json"
    meta = {"download": False, "audit": False}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text())
        except Exception:
            pass
    meta["audit"] = True
    meta_path.write_text(json.dumps(meta))

    return {"uploaded": str(target.relative_to(APP_DATA))}
