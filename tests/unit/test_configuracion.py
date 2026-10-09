import pytest
from pydantic import ValidationError

from app.core.config import SECRETO_DE_DESARROLLO, Configuracion


def _crear(monkeypatch: pytest.MonkeyPatch, **entorno: str) -> Configuracion:
    for clave in ("CORS_ORIGINS", "APP_ENV", "JWT_SECRET"):
        monkeypatch.delenv(clave, raising=False)
    for clave, valor in entorno.items():
        monkeypatch.setenv(clave, valor)
    return Configuracion(_env_file=None)  # type: ignore[call-arg]


def test_cors_acepta_texto_plano_como_lo_define_el_ci(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _crear(monkeypatch, CORS_ORIGINS="http://localhost:5173").cors_origins == [
        "http://localhost:5173"
    ]


def test_cors_acepta_varios_origenes_separados_por_comas(monkeypatch: pytest.MonkeyPatch) -> None:
    config = _crear(monkeypatch, CORS_ORIGINS="http://a.mx, http://b.mx")
    assert config.cors_origins == ["http://a.mx", "http://b.mx"]


def test_cors_acepta_lista_json(monkeypatch: pytest.MonkeyPatch) -> None:
    config = _crear(monkeypatch, CORS_ORIGINS='["http://a.mx","http://b.mx"]')
    assert config.cors_origins == ["http://a.mx", "http://b.mx"]


def test_secreto_publico_se_acepta_en_local(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _crear(monkeypatch).jwt_secret == SECRETO_DE_DESARROLLO


def test_secreto_publico_se_rechaza_fuera_de_local(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        _crear(monkeypatch, APP_ENV="production")


def test_secreto_propio_se_acepta_en_produccion(monkeypatch: pytest.MonkeyPatch) -> None:
    config = _crear(monkeypatch, APP_ENV="production", JWT_SECRET="x" * 40)
    assert config.jwt_secret == "x" * 40
