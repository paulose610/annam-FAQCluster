import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
APP_DATA = ROOT_DIR / "app-data"
APP_DATA.mkdir(exist_ok=True)

POP_WORK_DIR = Path(os.environ.get("POP_WORK_DIR", str(ROOT_DIR / "POP_Work")))


def _resolve_any_safe(base: Path, user_str: str) -> Path:
    """Sandbox resolver anchored to base — rejects absolute paths, .., null bytes, symlink escapes."""
    p = Path(user_str)
    if p.is_absolute():
        raise ValueError(f"absolute paths are not allowed: {user_str!r}")
    for part in p.parts:
        if part == "..":
            raise ValueError(f"path traversal not allowed: {user_str!r}")
        if "\x00" in part:
            raise ValueError(f"null bytes not allowed in path: {user_str!r}")
    resolved = (base / p).resolve()
    if not resolved.is_relative_to(base.resolve()):
        raise ValueError(f"path escapes sandbox: {user_str!r}")
    return resolved


def _resolve_safe(user_str: str) -> Path:
    """Resolve a user-supplied relative path inside APP_DATA."""
    return _resolve_any_safe(APP_DATA, user_str)
