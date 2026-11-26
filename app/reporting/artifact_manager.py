"""Saves every artifact locally (artifacts/runs/<slug>/) and to Supabase Storage + artifacts table."""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.database.repositories import Repository
from app.database.supabase_client import StorageError

log = logging.getLogger("forgeai.artifacts")
MIME = {".json": "application/json", ".md": "text/markdown", ".csv": "text/csv", ".pdf": "application/pdf",
        ".jsonl": "application/x-ndjson", ".txt": "text/plain"}


class ArtifactManager:
    def __init__(self, slug: str, project_id: str, run_id: str | None, repo: Repository | None):
        self.dir = get_settings().artifacts_dir / "runs" / slug
        self.dir.mkdir(parents=True, exist_ok=True)
        self.slug, self.project_id, self.run_id, self.repo = slug, project_id, run_id, repo

    def path(self, name: str) -> Path:
        return self.dir / name

    def write_json(self, name: str, obj: Any, kind: str | None = None, upload: bool = True) -> Path:
        data = json.dumps(obj, ensure_ascii=False, indent=2, default=str).encode("utf-8")
        return self.write_bytes(name, data, kind or Path(name).stem, upload)

    def write_text(self, name: str, text: str, kind: str | None = None, upload: bool = True) -> Path:
        return self.write_bytes(name, text.encode("utf-8"), kind or Path(name).stem, upload)

    def write_bytes(self, name: str, data: bytes, kind: str, upload: bool = True) -> Path:
        p = self.path(name)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        if upload and self.repo is not None:
            sha = hashlib.sha256(data).hexdigest()
            remote = f"{self.project_id}/{self.run_id or 'project'}/{name}"
            try:
                path = self.repo.db.upload(get_settings().supabase_deliverables_bucket, remote, data,
                                           MIME.get(p.suffix, "application/octet-stream"))
                self.repo.save_artifact(self.project_id, self.run_id, kind, name, path, sha, len(data))
            except StorageError as e:
                log.warning("artifact upload failed for %s: %s", name, e)
        return p

    def read_json(self, name: str) -> Any:
        p = self.path(name)
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def exists(self, name: str) -> bool:
        return self.path(name).exists()
