import hashlib
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
SNAPSHOT = RAIZ / "db/schema_0001.sql"
MIGRACION = RAIZ / "migrations/versions/0001_esquema_inicial.py"


def test_migracion_0001_usa_el_snapshot_historico_y_no_el_schema_vivo() -> None:
    fuente = MIGRACION.read_text(encoding="utf-8")
    contenido = SNAPSHOT.read_bytes()

    assert "schema_0001.sql" in fuente
    assert "schema.sql" not in fuente
    assert hashlib.sha1(contenido).hexdigest() == "7725d8ca269ba219fa4713eb653b876df0c68e12"
    assert b"aceptacion_aviso_privacidad" not in contenido
