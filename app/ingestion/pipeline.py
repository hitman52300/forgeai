"""Reusable ingestion pipeline: validate -> extract -> chunk -> embed -> store.

Raw files are kept in `data/uploads/<project_id>/` (needed for re-chunking and
for the CSV lookup tool) and uploaded to Supabase Storage. Document metadata
and versions go to the repository; vectors go to ChromaDB.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from app.config import get_settings
from app.core.schemas import DocumentRecord, RetrievalConfig
from app.database.repositories import Repository
from app.database.supabase_client import StorageError
from app.ingestion.chunker import chunk_document
from app.ingestion.loader import IngestionError, ValidatedFile, validate_file
from app.ingestion.parser import ParsedDocument, parse
from app.ingestion.vector_store import VectorStore, collection_name

log = logging.getLogger("forgeai.ingestion")

CONTENT_TYPES = {".pdf": "application/pdf", ".txt": "text/plain", ".csv": "text/csv",
                 ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}


@dataclass
class IngestionReport:
    project_id: str
    collection: str
    documents: list[DocumentRecord] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)
    changes: list[dict] = field(default_factory=list)  # {filename, change_type, old_hash, new_hash}

    def manifest(self) -> dict:
        return {"project_id": self.project_id, "collection": self.collection,
                "documents": [d.model_dump(exclude={"preview"}) for d in self.documents],
                "errors": self.errors, "duplicates": self.duplicates, "changes": self.changes}


def uploads_dir(project_id: str) -> Path:
    s = get_settings()
    p = s.path(s.uploads_dir) / project_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def _state_file(project_id: str) -> Path:
    return uploads_dir(project_id) / "_index_state.json"


def _remote():
    """Supabase backend when configured: the index state and raw files are mirrored to Storage so a stateless
    server (e.g. a restarted container) can restore them."""
    try:
        from app.database.supabase_client import get_backend
        b = get_backend()
        return b if getattr(b, "name", "") == "supabase" else None
    except Exception:  # noqa: BLE001
        return None


def load_state(project_id: str) -> dict:
    f = _state_file(project_id)
    if not f.exists() and (r := _remote()) is not None:
        try:
            f.write_bytes(r.download(get_settings().supabase_documents_bucket, f"{project_id}/_index_state.json"))
        except Exception:  # noqa: BLE001  (no remote state yet)
            pass
    state = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {"documents": {}, "collections": {}}
    if isinstance(state.get("collections"), list):  # older format
        state["collections"] = {}
    return state


def save_state(project_id: str, state: dict) -> None:
    data = json.dumps(state, indent=1)
    _state_file(project_id).write_text(data, encoding="utf-8")
    if (r := _remote()) is not None:
        try:
            r.upload(get_settings().supabase_documents_bucket, f"{project_id}/_index_state.json", data.encode(),
                     "application/json")
        except Exception as e:  # noqa: BLE001
            log.warning("index state not mirrored to storage: %s", e)


def raw_file(project_id: str, filename: str, info: dict) -> Path:
    """Local path of an ingested original file, downloading it from Supabase Storage if it is not on disk
    (stored paths are machine-specific, so the uploads folder of this machine is used)."""
    p = Path(info["path"])
    if not p.exists():
        p = uploads_dir(project_id) / filename
    if not p.exists() and info.get("storage_path") and (r := _remote()) is not None:
        bucket, _, key = info["storage_path"].partition("/")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(r.download(bucket, key))
    return p


class KnowledgeBase:
    def __init__(self, project_id: str, repo: Repository | None = None):
        self.project_id = project_id
        self.repo = repo

    # ------------------------------------------------------------------ ingest
    def ingest(self, files: list[tuple[str, bytes]], cfg: RetrievalConfig, *, sync_removed: bool = False) -> IngestionReport:
        """Ingest uploaded (filename, bytes). With sync_removed, files missing from
        `files` are treated as removed (used by regression mode)."""
        col = collection_name(self.project_id, cfg.chunk_size, cfg.chunk_overlap)
        report = IngestionReport(self.project_id, col)
        state = load_state(self.project_id)
        known: dict = state["documents"]
        seen_hashes: dict[str, str] = {}
        store = VectorStore(col)
        incoming_names = set()

        for name, data in files:
            try:
                vf = validate_file(name, data)
            except IngestionError as e:
                report.errors.append(str(e))
                continue
            incoming_names.add(vf.filename)
            if vf.sha256 in seen_hashes:
                report.duplicates.append(f"'{vf.filename}' is identical to '{seen_hashes[vf.sha256]}' and was skipped")
                continue
            seen_hashes[vf.sha256] = vf.filename
            prev = known.get(vf.filename)
            if prev and prev["hash"] == vf.sha256:
                change = "unchanged"
            elif prev:
                change = "modified"
            else:
                change = "added"
            try:
                parsed = parse(vf)
            except IngestionError as e:
                report.errors.append(str(e))
                continue
            doc_id = prev["document_id"] if prev else None
            version = (prev["version"] + (0 if change == "unchanged" else 1)) if prev else 1
            rec = self._index(vf, parsed, cfg, store, doc_id, version, replace_hash=prev["hash"] if prev and change == "modified" else None)
            rec_change = {"filename": vf.filename, "change_type": change,
                          "old_hash": prev["hash"] if prev else None, "new_hash": vf.sha256}
            report.changes.append(rec_change)
            report.documents.append(rec)
            known[vf.filename] = {"document_id": rec.document_id, "hash": vf.sha256, "version": version,
                                  "file_type": rec.file_type, "path": str(self._raw_path(vf.filename)),
                                  "storage_path": rec.storage_path}
            if self.repo:
                self.repo.upsert_document(rec, change)

        if sync_removed:
            for fname in list(known):
                if fname not in incoming_names:
                    info = known.pop(fname)
                    store.delete_document(info["document_id"])
                    report.changes.append({"filename": fname, "change_type": "removed",
                                           "old_hash": info["hash"], "new_hash": None})
                    if self.repo:
                        rec = DocumentRecord(document_id=info["document_id"], project_id=self.project_id,
                                             filename=fname, file_type=info["file_type"], size_bytes=0,
                                             content_hash=info["hash"], version=info["version"] + 1,
                                             status="removed")
                        self.repo.upsert_document(rec, "removed")
        state["collections"][col] = {"chunk_size": cfg.chunk_size, "chunk_overlap": cfg.chunk_overlap,
                                     "separators": cfg.separators}
        state["documents"] = known
        save_state(self.project_id, state)
        # keep every other index of this project (other chunking configs) in sync with the change
        changed = [c for c in report.changes if c["change_type"] in ("added", "modified", "removed")]
        for other, ocfg in state["collections"].items():
            if other == col or not changed:
                continue
            ostore = VectorStore(other)
            rc = RetrievalConfig(chunk_size=ocfg["chunk_size"], chunk_overlap=ocfg["chunk_overlap"],
                                 separators=ocfg.get("separators") or RetrievalConfig().separators)
            for ch in changed:
                if ch["old_hash"]:
                    ostore.delete_hash(ch["old_hash"])
                if ch["change_type"] != "removed":
                    info = known[ch["filename"]]
                    vf = validate_file(ch["filename"], raw_file(self.project_id, ch["filename"], info).read_bytes())
                    ostore.upsert(chunk_document(parse(vf), info["document_id"], vf.sha256, rc, other))
        return report

    def _raw_path(self, filename: str) -> Path:
        return uploads_dir(self.project_id) / filename

    def _index(self, vf: ValidatedFile, parsed: ParsedDocument, cfg: RetrievalConfig, store: VectorStore,
               doc_id: str | None, version: int, replace_hash: str | None) -> DocumentRecord:
        self._raw_path(vf.filename).write_bytes(vf.data)
        storage_path = None
        if self.repo:
            try:
                storage_path = self.repo.db.upload(get_settings().supabase_documents_bucket,
                                                   f"{self.project_id}/{vf.sha256[:12]}_{vf.filename}", vf.data,
                                                   CONTENT_TYPES.get(vf.extension, "application/octet-stream"))
            except StorageError as e:
                log.warning("storage upload failed for %s: %s", vf.filename, e)
        rec = DocumentRecord(project_id=self.project_id, filename=vf.filename, file_type=parsed.file_type,
                             size_bytes=vf.size, content_hash=vf.sha256, version=version,
                             page_count=parsed.page_count, row_count=parsed.row_count, columns=parsed.columns,
                             storage_path=storage_path, preview=parsed.full_text[:1500])
        if doc_id:
            rec.document_id = doc_id
        if replace_hash:
            store.delete_hash(replace_hash)
        chunks = chunk_document(parsed, rec.document_id, vf.sha256, cfg, store.name)
        store.upsert(chunks)  # chunk ids are content-derived, so unchanged files are idempotent
        rec.chunk_count = len(chunks)
        return rec

    # ------------------------------------------------------------------ re-index with a new config
    def ensure_index(self, cfg: RetrievalConfig) -> str:
        """Make sure a collection exists for cfg's chunking (used by the optimizer and runtime)."""
        col = collection_name(self.project_id, cfg.chunk_size, cfg.chunk_overlap)
        store = VectorStore(col)
        state = load_state(self.project_id)
        if store.count() == 0 and state["documents"]:
            for fname, info in state["documents"].items():
                data = raw_file(self.project_id, fname, info).read_bytes()
                vf = validate_file(fname, data)
                parsed = parse(vf)
                store.upsert(chunk_document(parsed, info["document_id"], vf.sha256, cfg, col))
        if col not in state["collections"]:
            state["collections"][col] = {"chunk_size": cfg.chunk_size, "chunk_overlap": cfg.chunk_overlap,
                                         "separators": cfg.separators}
            save_state(self.project_id, state)
        return col

    def documents(self) -> dict:
        return load_state(self.project_id)["documents"]

    def csv_files(self) -> list[Path]:
        return [raw_file(self.project_id, f, i) for f, i in self.documents().items() if i["file_type"] == "csv"]
