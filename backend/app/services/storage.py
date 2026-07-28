"""File storage, scoped per user under UPLOAD_DIR.

Every stored path begins with the owning user's id; reads re-verify both the
DB ownership row and that the resolved path stays inside that user's
directory. Files are only ever served through authenticated endpoints.
"""
from __future__ import annotations

import re
import shutil
import uuid
from pathlib import Path

from app.config import get_settings

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def _user_root(user_id: int) -> Path:
    root = get_settings().upload_dir / str(user_id)
    root.mkdir(parents=True, exist_ok=True)
    return root


def safe_filename(original: str) -> str:
    name = _SAFE_NAME.sub("_", Path(original).name).strip("._") or "file"
    return name[:180]


def store_bytes(user_id: int, category: str, original_name: str, data: bytes) -> str:
    """Write bytes and return the path relative to UPLOAD_DIR."""
    name = f"{uuid.uuid4().hex[:12]}_{safe_filename(original_name)}"
    rel = Path(str(user_id)) / category / name
    absolute = get_settings().upload_dir / rel
    absolute.parent.mkdir(parents=True, exist_ok=True)
    absolute.write_bytes(data)
    return rel.as_posix()


def resolve_user_path(user_id: int, rel_path: str) -> Path:
    """Resolve a stored relative path, refusing anything that escapes the
    owner's directory."""
    base = (get_settings().upload_dir / str(user_id)).resolve()
    candidate = (get_settings().upload_dir / rel_path).resolve()
    if not candidate.is_relative_to(base):
        raise PermissionError("Path escapes the owner's storage scope")
    return candidate


def delete_file(user_id: int, rel_path: str) -> None:
    try:
        path = resolve_user_path(user_id, rel_path)
    except PermissionError:
        return
    path.unlink(missing_ok=True)


def delete_user_files(user_id: int) -> None:
    root = get_settings().upload_dir / str(user_id)
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
