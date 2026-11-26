"""Low-level persistence backends.

`TableBackend` is the minimal contract (insert / update / select / storage).
`SupabaseBackend` talks to Supabase Postgres + Storage with the service-role key
(server-side only; ownership is enforced in the API layer and by RLS for any
direct client access).  `LocalBackend` keeps the same tables as JSON files so
unit tests and offline development work without network access.
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from app.config import Settings, get_settings


class StorageError(RuntimeError):
    pass


class TableBackend(Protocol):
    name: str

    def insert(self, table: str, row: dict[str, Any]) -> dict[str, Any]: ...
    def update(self, table: str, row_id: str, patch: dict[str, Any]) -> dict[str, Any]: ...
    def select(self, table: str, filters: dict[str, Any] | None = None, order: str | None = None,
               limit: int | None = None) -> list[dict[str, Any]]: ...
    def upload(self, bucket: str, path: str, data: bytes, content_type: str) -> str: ...
    def download(self, bucket: str, path: str) -> bytes: ...


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class LocalBackend:
    name = "local"

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _file(self, table: str) -> Path:
        return self.root / f"{table}.json"

    def _load(self, table: str) -> list[dict[str, Any]]:
        f = self._file(table)
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else []

    def _save(self, table: str, rows: list[dict[str, Any]]) -> None:
        tmp = self._file(table).with_suffix(".tmp")
        tmp.write_text(json.dumps(rows, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        tmp.replace(self._file(table))

    def insert(self, table, row):
        with self._lock:
            rows = self._load(table)
            row = {"id": str(uuid.uuid4()), "created_at": _now(), **row}
            rows.append(row)
            self._save(table, rows)
            return row

    def update(self, table, row_id, patch):
        if table in ("evaluation_results", "approval_records"):
            raise StorageError(f"{table} is append-only")
        with self._lock:
            rows = self._load(table)
            for r in rows:
                if r["id"] == row_id:
                    r.update(patch)
                    r["updated_at"] = _now()
                    self._save(table, rows)
                    return r
        raise StorageError(f"{table}/{row_id} not found")

    def select(self, table, filters=None, order=None, limit=None):
        rows = self._load(table)
        for k, v in (filters or {}).items():
            rows = [r for r in rows if r.get(k) == v]
        if order:
            desc = order.startswith("-")
            key = order.lstrip("-")
            rows.sort(key=lambda r: (r.get(key) is None, r.get(key)), reverse=desc)
        return rows[:limit] if limit else rows

    def upload(self, bucket, path, data, content_type):
        p = self.root / "storage" / bucket / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return f"{bucket}/{path}"

    def download(self, bucket, path):
        return (self.root / "storage" / bucket / path).read_bytes()


class SupabaseBackend:
    name = "supabase"

    def __init__(self, settings: Settings):
        if not settings.supabase_url or not settings.supabase_service_role_key or \
                settings.supabase_service_role_key.startswith("PASTE_"):
            raise StorageError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY are not configured in .env")
        from supabase import create_client  # imported lazily: optional at test time
        self.client = create_client(settings.supabase_url, settings.supabase_service_role_key)

    def insert(self, table, row):
        try:
            res = self.client.table(table).insert(_jsonable(row)).execute()
        except Exception as e:  # noqa: BLE001
            raise StorageError(f"insert into {table} failed: {e}") from e
        return res.data[0]

    def update(self, table, row_id, patch):
        patch = {**_jsonable(patch), "updated_at": _now()} if table not in _NO_UPDATED_AT else _jsonable(patch)
        try:
            res = self.client.table(table).update(patch).eq("id", row_id).execute()
        except Exception as e:  # noqa: BLE001
            raise StorageError(f"update {table} failed: {e}") from e
        if not res.data:
            raise StorageError(f"{table}/{row_id} not found")
        return res.data[0]

    def select(self, table, filters=None, order=None, limit=None):
        q = self.client.table(table).select("*")
        for k, v in (filters or {}).items():
            q = q.eq(k, v)
        if order:
            q = q.order(order.lstrip("-"), desc=order.startswith("-"))
        if limit:
            q = q.limit(limit)
        try:
            return q.execute().data
        except Exception as e:  # noqa: BLE001
            raise StorageError(f"select from {table} failed: {e}") from e

    def upload(self, bucket, path, data, content_type):
        try:
            self.client.storage.from_(bucket).upload(path, data, {"content-type": content_type, "upsert": "true"})
        except Exception as e:  # noqa: BLE001
            raise StorageError(f"upload to {bucket}/{path} failed: {e}") from e
        return f"{bucket}/{path}"

    def download(self, bucket, path):
        return self.client.storage.from_(bucket).download(path)

    def verify_user_token(self, token: str) -> dict[str, Any]:
        res = self.client.auth.get_user(token)
        if not res or not res.user:
            raise StorageError("invalid access token")
        return {"id": res.user.id, "email": res.user.email}

    def find_user_by_email(self, email: str) -> dict[str, Any] | None:
        page = self.client.auth.admin.list_users()
        for u in page:
            if (u.email or "").lower() == email.lower():
                return {"id": u.id, "email": u.email}
        return None


# tables that have no updated_at column
_NO_UPDATED_AT = {"document_versions", "requirements", "agent_versions", "evaluation_datasets", "evaluation_cases",
                  "failure_records", "scorecards", "optimization_iterations", "change_logs", "regression_runs",
                  "baseline_comparisons", "artifacts", "audit_logs", "tool_registry", "profiles"}


def _jsonable(obj: Any) -> Any:
    return json.loads(json.dumps(obj, default=str))


_backend: TableBackend | None = None


def get_backend(settings: Settings | None = None) -> TableBackend:
    global _backend
    if _backend is None:
        s = settings or get_settings()
        _backend = SupabaseBackend(s) if s.storage_backend == "supabase" else LocalBackend(s.path(s.local_db_dir))
    return _backend


def set_backend(backend: TableBackend | None) -> None:
    global _backend
    _backend = backend
