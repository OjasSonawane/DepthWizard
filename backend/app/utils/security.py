import re
import shutil
from pathlib import Path
from typing import Optional
from fastapi import HTTPException, UploadFile
from app.config import settings

SAFE_ID_REGEX = re.compile(r"^[a-zA-Z0-9_\-]+$")


def validate_safe_id(identifier: Optional[str], param_name: str = "id") -> str:
    """
    Validates that an identifier contains only alphanumeric characters, underscores, and hyphens.
    Strictly prevents path traversal attempts (e.g. '../', '..\\', null bytes).
    """
    if identifier is None:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required parameter '{param_name}'."
        )

    if not isinstance(identifier, str) or not identifier.strip():
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {param_name}: identifier cannot be empty."
        )

    identifier = identifier.strip()

    if ".." in identifier or "/" in identifier or "\\" in identifier or "\x00" in identifier:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {param_name}: path traversal attempt detected."
        )

    if not SAFE_ID_REGEX.match(identifier):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {param_name}: identifier must be alphanumeric, hyphen, or underscore."
        )

    if len(identifier) > 128:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {param_name}: identifier exceeds maximum allowed length of 128 characters."
        )

    return identifier


def assert_path_confined(target_path: Path, base_dir: Path) -> Path:
    """
    Ensures target_path resolves strictly within base_dir.
    Raises HTTPException 400 if path traversal or escape is detected.
    """
    try:
        resolved_base = base_dir.resolve()
        resolved_target = target_path.resolve()
        
        # In Python 3.9+, is_relative_to is standard
        if not resolved_target.is_relative_to(resolved_base):
            raise HTTPException(
                status_code=400,
                detail="Path traversal violation: target path is outside designated directory."
            )
        return resolved_target
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Path resolution error: {e}"
        )


def sanitize_filename(filename: Optional[str]) -> str:
    """
    Sanitizes an uploaded filename by stripping path delimiters and control characters.
    """
    if not filename:
        return "unnamed_file"
    
    # Strip directory components
    base = Path(filename).name
    # Strip null bytes and control chars
    clean = re.sub(r"[\x00-\x1f\x7f]", "", base)
    clean = clean.replace("..", "_")
    return clean or "unnamed_file"


async def save_upload_file_safely(
    upload_file: UploadFile,
    target_path: Path,
    max_bytes: Optional[int] = None
) -> int:
    """
    Streams an UploadFile to disk chunk-by-chunk while enforcing:
    1. Size ceiling (max_bytes) with HTTP 413.
    2. Non-empty payload (at least 1 byte) with HTTP 400.
    Automatically deletes partial/failed file targets on any error.
    """
    if max_bytes is None:
        max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    chunk_size = 64 * 1024  # 64 KB chunks
    total_bytes = 0
    target_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(target_path, "wb") as f:
            while True:
                chunk = await upload_file.read(chunk_size)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Uploaded file exceeds maximum allowed limit of {max_bytes // (1024 * 1024)}MB."
                    )
                f.write(chunk)

        if total_bytes == 0:
            raise HTTPException(
                status_code=400,
                detail="Uploaded file is empty (0 bytes)."
            )

        return total_bytes

    except Exception:
        if target_path.exists():
            try:
                target_path.unlink()
            except OSError:
                pass
        raise
