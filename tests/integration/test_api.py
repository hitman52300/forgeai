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
