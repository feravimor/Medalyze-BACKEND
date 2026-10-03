from fastapi.testclient import TestClient

from app.main import app


def test_health_no_consulta_base_de_datos() -> None:
    respuesta = TestClient(app).get("/api/v1/health")
    assert respuesta.status_code == 200
    assert respuesta.json()["estado"] == "ok"
