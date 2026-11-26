"""Agent studio + generic chat runner."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import User, current_user, get_factory
from app.core.llm_service import LLMService
from app.runtime.agent_loader import load_agent
from app.runtime.chat_engine import AgentRuntime, ChatSession

router = APIRouter(prefix="/agents", tags=["agents"])
_SESSIONS: dict[tuple[str, str, str], ChatSession] = {}
_RUNTIMES: dict[tuple[str, int], AgentRuntime] = {}


def _owned_agent(agent_id: str, user: User) -> dict:
    repo = get_factory().repo
    rows = [a for a in repo.list_agents() if a["id"] == agent_id]
    if not rows:
        raise HTTPException(404, "agent not found")
    try:
        repo.assert_owner(rows[0]["project_id"], user.id)
    except PermissionError as e:
        raise HTTPException(404, "agent not found") from e
    return rows[0]


@router.get("")
def list_agents(user: User = Depends(current_user)):
    repo = get_factory().repo
    owned = {p["id"]: p["name"] for p in repo.list_projects(user.id)}
    return [{**a, "project_name": owned[a["project_id"]]} for a in repo.list_agents() if a["project_id"] in owned]


@router.get("/{agent_id}/versions")
def versions(agent_id: str, user: User = Depends(current_user)):
    _owned_agent(agent_id, user)
    return get_factory().repo.agent_versions(agent_id)


class ChatIn(BaseModel):
    question: str
    session_id: str = "default"
    version: int | None = None


@router.post("/{agent_id}/chat")
def chat(agent_id: str, body: ChatIn, user: User = Depends(current_user)):
    row = _owned_agent(agent_id, user)
    version = body.version or row.get("final_version") or row["latest_version"]
    vers = {v["version"]: v for v in get_factory().repo.agent_versions(agent_id)}
    if version not in vers:
        raise HTTPException(404, f"version {version} not found")
    key = (agent_id, version)
    if key not in _RUNTIMES:
        _RUNTIMES[key] = AgentRuntime(load_agent(vers[version]["definition"]), LLMService.from_settings())
    rt = _RUNTIMES[key]
    # sessions are keyed by user + agent + session id, so history never crosses agents or projects
    skey = (user.id, agent_id, body.session_id)
    sess = _SESSIONS.setdefault(skey, rt.new_session())
    return rt.ask(body.question, sess).model_dump(mode="json")


@router.delete("/{agent_id}/chat/{session_id}")
def reset(agent_id: str, session_id: str, user: User = Depends(current_user)):
    _SESSIONS.pop((user.id, agent_id, session_id), None)
    return {"ok": True}
