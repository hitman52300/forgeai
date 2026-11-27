"""Upload validation: extension whitelist, size limit, magic-byte sanity checks, hashing."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from app.config import Settings, get_settings


class IngestionError(ValueError):
    """User-facing error for an unsupported or unreadable file."""


@dataclass
class ValidatedFile:
    filename: str
    extension: str
    data: bytes
    sha256: str

    @property
    def size(self) -> int:
        return len(self.data)


_SAFE_NAME = re.compile(r"[^A-Za-z0-9._\- ]+")


def safe_filename(name: str) -> str:
    # strip directory components (path traversal) for both POSIX and Windows separators,
    # so a Windows-style upload name is handled the same way on a Linux host
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    base = _SAFE_NAME.sub("_", base).strip(" .")
    if not base:
        raise IngestionError("file name is empty after sanitising")
    return base[:150]


def validate_file(filename: str, data: bytes, settings: Settings | None = None) -> ValidatedFile:
    s = settings or get_settings()
    name = safe_filename(filename)
    ext = Path(name).suffix.lower()
    if ext not in s.allowed_ext_set:
        raise IngestionError(f"'{name}': unsupported file type '{ext or 'none'}'. "
                             f"Allowed: {', '.join(sorted(s.allowed_ext_set))}")
    if not data:
        raise IngestionError(f"'{name}' is empty")
    limit = s.max_upload_mb * 1024 * 1024
    if len(data) > limit:
        raise IngestionError(f"'{name}' is {len(data) / 1e6:.1f} MB; the limit is {s.max_upload_mb} MB")
    if ext == ".pdf" and not data[:1024].lstrip().startswith(b"%PDF"):
        raise IngestionError(f"'{name}' does not look like a PDF (missing %PDF header)")
    if ext == ".docx" and not data.startswith(b"PK"):
        raise IngestionError(f"'{name}' does not look like a DOCX (not a zip container)")
    if ext in (".txt", ".csv"):
        try:
            data.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                data.decode("cp1252")
            except UnicodeDecodeError as e:
                raise IngestionError(f"'{name}' is not readable text: {e}") from e
    return ValidatedFile(filename=name, extension=ext, data=data, sha256=hashlib.sha256(data).hexdigest())


def load_folder(folder: Path, settings: Settings | None = None) -> tuple[list[ValidatedFile], list[str]]:
    """Validate every file in a folder. Returns (accepted files, error messages)."""
    ok, errors = [], []
    for p in sorted(folder.iterdir()):
        if not p.is_file() or p.name.startswith("."):
            continue
        try:
            ok.append(validate_file(p.name, p.read_bytes(), settings))
        except IngestionError as e:
            errors.append(str(e))
    return ok, errors
