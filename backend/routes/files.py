import shutil
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, field_validator

from backend.common import APP_DATA, _resolve_safe

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
