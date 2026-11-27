"""API wiring with the local backend (no LLM calls)."""
from fastapi.testclient import TestClient

from app.main import app


def test_health_tools_and_gates():
    c = TestClient(app)
    h = c.get("/health").json()
    assert h["storage_backend"] == "local"
    names = {t["name"] for t in c.get("/tools").json()}
    assert names == {"csv_lookup", "calculator", "weather_api", "current_date"}
    assert c.get("/runs").status_code == 200
    assert c.get("/runs/does-not-exist").status_code == 404
    assert c.post("/runs/does-not-exist/execute").status_code == 404
    assert c.get("/jobs/nope").status_code == 404


def test_failed_ingestion_explains_missing_interview():
    from app.api.deps import get_factory
    rid = get_factory().start(project_name="bad upload", brief="b", files=[("a.exe", b"MZ")],
                              owner_id="00000000-0000-0000-0000-000000000001", owner_label="local-operator")
    c = TestClient(app)
    st = c.get(f"/runs/{rid}").json()
    assert st["run"]["status"] == "failed" and st["job_active"] is False
    r = c.get(f"/runs/{rid}/interview")
    assert r.status_code == 404 and "no document could be ingested" in r.json()["detail"]
