"""Shared API dependencies: auth, factory instance, ownership checks, background jobs."""
from __future__ import annotations

import threading
import traceback
import uuid
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Callable

from fastapi import Depends, Header, HTTPException

from app.core.orchestrator import Factory
from app.database.repositories import Repository
from app.database.supabase_client import StorageError, get_backend

LOCAL_USER = {"id": "00000000-0000-0000-0000-000000000001", "email": "local-operator"}


@lru_cache
def get_factory() -> Factory:
    return Factory(Repository(get_backend()))


@dataclass
class User:
    id: str
    email: str


def current_user(authorization: str | None = Header(None)) -> User:
    """Supabase Auth bearer token (validated server-side). Local backend: single local operator."""
    db = get_backend()
    if getattr(db, "name", "") != "supabase":
        return User(**LOCAL_USER)
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "missing bearer token")
    try:
        u = db.verify_user_token(authorization.split(" ", 1)[1])  # type: ignore[attr-defined]
    except StorageError as e:
        raise HTTPException(401, str(e)) from e
    get_factory().repo.ensure_profile(u["id"], u["email"] or "")
    return User(id=u["id"], email=u["email"] or "")


def owned_run(run_id: str, user: User = Depends(current_user)):
    f = get_factory()
    try:
        run, am = f.load(run_id)
    except KeyError as e:
        raise HTTPException(404, "run not found") from e
    try:
        f.repo.assert_owner(run.project_id, user.id)
    except PermissionError as e:
        raise HTTPException(404, "run not found") from e
    return run, am, user


# ------------------------------------------------------------------ background jobs
@dataclass
class Job:
    id: str
    kind: str
    run_id: str
    status: str = "running"
    messages: list[str] = field(default_factory=list)
    result: dict | None = None
    error: str | None = None


JOBS: dict[str, Job] = {}
_RUN_LOCKS: dict[str, threading.Lock] = {}


def job_active(run_id: str) -> bool:
    """True while a background job for this run is running in this server process."""
    lock = _RUN_LOCKS.get(run_id)
    return bool(lock and lock.locked())


def start_job(kind: str, run_id: str, fn: Callable[[Callable[[str], None]], dict]) -> Job:
    lock = _RUN_LOCKS.setdefault(run_id, threading.Lock())
    if not lock.acquire(blocking=False):
        raise HTTPException(409, "another job is already running for this run")
    job = Job(id=str(uuid.uuid4()), kind=kind, run_id=run_id)
    JOBS[job.id] = job

    def target():
        try:
            job.result = fn(lambda m: (job.messages.append(m), job.messages.__delitem__(slice(0, -200))))
            job.status = "completed"
        except Exception as e:  # noqa: BLE001
            job.status = "failed"
            job.error = f"{type(e).__name__}: {e}"
            job.messages.append(traceback.format_exc()[-1500:])
        finally:
            lock.release()

    threading.Thread(target=target, daemon=True, name=f"{kind}-{run_id[:8]}").start()
    return job
