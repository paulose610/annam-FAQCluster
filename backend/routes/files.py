import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
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
