from collections import defaultdict, deque
from threading import Lock
from time import monotonic

from app.core.errores import ErrorAplicacion

_ventanas: dict[str, deque[float]] = defaultdict(deque)
_bloqueo = Lock()


def limitar_intentos(clave: str, limite: int = 60, ventana_segundos: int = 60) -> None:
    """Limita abusos básicos de autenticación por proceso y origen.

    La autenticación y la revocación siguen siendo persistentes en PostgreSQL; este límite sólo
    reduce ataques rápidos y debe complementarse con un limitador distribuido en producción.
    """
    ahora = monotonic()
    with _bloqueo:
        intentos = _ventanas[clave]
        while intentos and ahora - intentos[0] >= ventana_segundos:
            intentos.popleft()
        if len(intentos) >= limite:
            raise ErrorAplicacion(
                "DEMASIADAS_SOLICITUDES",
                "Demasiadas solicitudes. Intenta de nuevo más tarde.",
                429,
            )
        intentos.append(ahora)
