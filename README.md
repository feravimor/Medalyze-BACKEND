# Medalyze Backend

API v1 de Medalyze construida con FastAPI y PostgreSQL 16. Este repositorio materializa el contrato ARQ-03 y los tickets BE-01 a BE-10 sobre la arquitectura definida en ADR-001.

## Estado

`Candidato técnico para revisión`. El código es ejecutable y contiene el flujo completo del MVP, pero la aprobación del contrato, seguridad y fórmulas corresponde al proceso de Pull Request del equipo.

## Inicio rápido

```bash
cp .env.example .env
docker compose up --build
```

- Swagger: `http://localhost:8000/api/v1/docs`
- Salud: `http://localhost:8000/api/v1/health`
- Disponibilidad: `http://localhost:8000/api/v1/ready`

La migración inicial carga únicamente catálogos técnicos. No carga plantillas de
tratamiento ni las expone como contenido clínico aprobado. Para una demostración
local, después de aplicar las migraciones, carga explícitamente las plantillas
sintéticas con:

```bash
LOAD_DEMO_DATA=true python scripts/cargar_datos_demo.py
```

`LOAD_DEMO_DATA` vale `false` por defecto y la configuración rechaza activarlo
con `APP_ENV=production`. `db/seed_demo.sql` contiene datos no aprobados,
incluida la plantilla de ejemplo “Profilaxis dental”.

El contenedor de API ejecuta `alembic upgrade head` antes de iniciar. Para reconstruir la base:

```bash
make db-reset
```

Ejecución local sin Docker, con PostgreSQL ya disponible:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

## Arquitectura

```text
app/
├── api/               # FastAPI, dependencias, esquemas y routers
├── application/       # Coordinación y utilidades de casos de uso
├── domain/costeo/     # Motor puro, sin frameworks
├── infrastructure/    # Idempotencia y adaptadores técnicos
└── core/              # Configuración, BD, seguridad y errores
```

Dependencias de código: `api -> application -> domain`; `infrastructure` implementa detalles requeridos por capas internas. El dominio no importa FastAPI, SQLAlchemy, Pydantic ni PostgreSQL.

## Cobertura de tickets

| Ticket | Implementación principal |
|---|---|
| ARQ-03 | `docs/api/openapi.yaml`, convenciones y verificación estructural |
| BE-01 | Docker, Compose, PostgreSQL 16, Makefile, health/ready y GitHub Actions |
| BE-02 | `db/schema.sql`, `db/seed.sql`, migraciones Alembic, 14 enums, 26 entidades del modelo y tabla técnica de idempotencia |
| BE-03 | Autenticación, renovación/cierre de sesión, usuario actual, perfil, organización, especialidades y permisos |
| BE-04 | Capacidad, gastos, equipos, depreciación, resumen indirecto y datos sintéticos |
| BE-05 | Insumos, unidades, precios históricos, archivo/restauración y conflictos |
| BE-06 | Periodos mensuales, correcciones, anulación/restauración y promedio de materiales |
| BE-07 | Plantillas, importación, tratamientos, configuración, archivo/restauración y materiales sugeridos |
| BE-08 | Vista previa y cálculo persistido con `Decimal`, idempotencia, revisión y bloqueos |
| BE-09 | Hojas de costos e historial inmutable con aislamiento por organización |
| BE-10 | Resumen de inicio y agregados requeridos por la interfaz |

El paquete también incluye la evidencia técnica de CAL-01 a CAL-07: tipos de valor, bloqueos, fórmulas, siete puertos, adaptadores SQLAlchemy, banco de escenarios, pruebas basadas en propiedades y cobertura del dominio superior al 90 %.

## Decisiones defensivas inspiradas en Code Complete

- Contratos explícitos mediante Pydantic y OpenAPI.
- Nombres de negocio consistentes en español.
- Funciones pequeñas, responsabilidades separadas y dominio aislado.
- Validación en el límite HTTP y restricciones adicionales en PostgreSQL.
- Operaciones financieras con `Decimal`.
- Errores de aplicación estables, sin trazas en respuestas.
- Escrituras dentro de una transacción y snapshots inmutables.
- Pruebas del motor, límites arquitectónicos, contrato y salud.
- Idempotencia para las dos operaciones exigidas por ARQ-03.
- SQLAlchemy 2.0.43 síncrono con psycopg 3.2.9.
- Alembic 1.16.5 como proceso reproducible de esquema y catálogos.

## Diferencia documental localizada

La tarjeta BE-02 menciona 22 tablas, mientras que `medalyze-base-de-datos.puml` contiene 26 entidades. Se implementaron las 26 para no eliminar plantillas, recetas ni las colecciones de snapshots. Además se añadió `solicitud_idempotente`, necesaria para aplicar `Idempotency-Key`. Esta diferencia debe aprobarse en el PR de BE-02.

## Decisiones pendientes de aprobación

- El contrato candidato entrega el refresh token en JSON. Antes de producción debe aprobarse la variante con cookie `HttpOnly`, `Secure`, `SameSite` y CSRF.
- La retención de `Idempotency-Key` se fijó provisionalmente en 24 horas.
- `medalyze_app` y su contraseña son credenciales exclusivas del entorno local/CI. En despliegue deben aprovisionarse fuera del repositorio mediante el gestor de secretos de la plataforma.

## Suscripción

`/cuenta/suscripcion` pertenece al frontend como pantalla informativa del MVP. Este backend no implementa planes, cobros, pasarela de pagos, renovación ni cancelación de suscripciones. Agregar esas capacidades requiere un ticket y un contrato posteriores; no se inventan endpoints dentro de ARQ-03.

## Verificación

```bash
pip install -e '.[dev]'
ruff check .
mypy app
python scripts/verificar_openapi.py
pytest
```

`main` debe protegerse en GitHub: sólo PR, CI en verde y al menos una revisión.
