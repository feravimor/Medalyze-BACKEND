import tomllib
from pathlib import Path

import yaml


def test_stack_de_persistencia_permanece_sincrono_y_fijado() -> None:
    proyecto = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    dependencias = set(proyecto["project"]["dependencies"])
    assert "fastapi==0.141.1" in dependencias
    assert "sqlalchemy==2.0.43" in dependencias
    assert "psycopg[binary]==3.2.9" in dependencias
    assert "alembic==1.16.5" in dependencias
    assert not any("asyncpg" in dependencia for dependencia in dependencias)


def test_suscripcion_no_inventa_endpoints_backend() -> None:
    contrato = yaml.safe_load(Path("docs/api/openapi.yaml").read_text(encoding="utf-8"))
    assert not any("suscrip" in ruta.lower() for ruta in contrato["paths"])


def test_migraciones_iniciales_existen() -> None:
    assert Path("migrations/versions/0001_esquema_inicial.py").is_file()
    assert Path("migrations/versions/0002_catalogos_iniciales.py").is_file()
