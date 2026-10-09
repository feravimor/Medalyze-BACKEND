import logging
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from psycopg import errors as errores_pg
from sqlalchemy.exc import DataError, IntegrityError

from app.api.router import router
from app.core.config import obtener_configuracion
from app.core.errores import ErrorAplicacion

configuracion = obtener_configuracion()
logging.basicConfig(
    level=configuracion.log_level, format='{"nivel":"%(levelname)s","mensaje":"%(message)s"}'
)

app = FastAPI(
    title="Medalyze API",
    version="1.0.0",
    openapi_url="/api/v1/openapi.json",
    docs_url="/api/v1/docs",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=configuracion.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "If-Match", "Idempotency-Key", "X-Request-ID"],
)
app.include_router(router, prefix="/api/v1")


@app.middleware("http")
async def agregar_request_id(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(ErrorAplicacion)
async def manejar_error_aplicacion(request: Request, error: ErrorAplicacion) -> JSONResponse:
    detalle = {
        "codigo": error.codigo,
        "mensaje": error.mensaje,
        "campos": error.campos,
        "bloqueos": error.bloqueos,
        "request_id": getattr(request.state, "request_id", None),
    }
    if error.revision_actual is not None:
        detalle["revision_actual"] = error.revision_actual
    return JSONResponse(status_code=error.estado_http, content={"detalle": detalle})


@app.exception_handler(RequestValidationError)
async def manejar_validacion(request: Request, error: RequestValidationError) -> JSONResponse:
    campos = [
        {"campo": ".".join(str(x) for x in item["loc"] if x != "body"), "mensaje": item["msg"]}
        for item in error.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={
            "detalle": {
                "codigo": "ERROR_VALIDACION",
                "mensaje": "Revisa los datos enviados.",
                "campos": campos,
                "bloqueos": [],
                "request_id": getattr(request.state, "request_id", None),
            }
        },
    )


def _error_validacion(request: Request, mensaje: str) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "detalle": {
                "codigo": "ERROR_VALIDACION",
                "mensaje": mensaje,
                "campos": [],
                "bloqueos": [],
                "request_id": getattr(request.state, "request_id", None),
            }
        },
    )


@app.exception_handler(IntegrityError)
async def manejar_integridad(request: Request, error: IntegrityError) -> JSONResponse:
    if isinstance(error.orig, errores_pg.ForeignKeyViolation):
        return _error_validacion(request, "Una de las referencias enviadas no existe.")
    if isinstance(error.orig, (errores_pg.CheckViolation, errores_pg.NotNullViolation)):
        return _error_validacion(request, "Revisa los datos enviados.")
    return await manejar_error_interno(request, error)


@app.exception_handler(DataError)
async def manejar_dato_invalido(request: Request, error: DataError) -> JSONResponse:
    return _error_validacion(request, "Revisa los datos enviados.")


@app.exception_handler(Exception)
async def manejar_error_interno(request: Request, error: Exception) -> JSONResponse:
    logging.exception("error_interno request_id=%s", getattr(request.state, "request_id", None))
    return JSONResponse(
        status_code=500,
        content={
            "detalle": {
                "codigo": "ERROR_INTERNO",
                "mensaje": "Ocurrió un error interno.",
                "campos": [],
                "bloqueos": [],
                "request_id": getattr(request.state, "request_id", None),
            }
        },
    )
