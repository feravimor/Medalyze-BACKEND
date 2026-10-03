# ARQ-01 - Trazabilidad de clases del motor a módulos

Fuente: `Medalyze_Diagrama_Clases_Calculo_Costos.puml`. La tabla asigna cada tipo del motor a una capa y a uno o más de los 12 módulos de ARQ-01. Las entidades de identidad y catálogos que no pertenecen al motor se derivan del modelo PostgreSQL en sus tickets de implementación.

## Tipos de valor y enumeraciones

| Clase | Capa y ubicación propuesta | Módulos consumidores |
|---|---|---|
| `Dinero`, `Minutos`, `Porcentaje`, `MesCalendario` | `domain/costeo/valores.py` | capacidad, gastos, equipos, insumos, mensuales, tratamientos, costeo |
| `Periodicidad`, `CategoriaGasto` | `domain/costeo/enums.py` | gastos |
| `EstadoEquipo`, `MotivoExclusion` | `domain/costeo/enums.py` | equipos, costeo |
| `EstadoTratamiento`, `EstadoRegistro`, `TipoRegistro` | `domain/costeo/enums.py` | tratamientos, mensuales, costeo |
| `MadurezBase` | `domain/costeo/enums.py` | mensuales, costeo |
| `SemaforoMargen`, `PasoCalculo`, `CodigoBloqueo` | `domain/costeo/enums.py` | costeo y módulos que originan bloqueos |

## Gastos, equipos y capacidad

| Clase | Capa y ubicación propuesta | Módulos consumidores |
|---|---|---|
| `GastoRegistrado` | `domain/costeo/gastos.py` | gastos, costeo |
| `Equipo` | `domain/costeo/equipos.py` | equipos, costeo |
| `CostosIndirectosMensuales`, `CalculadoraCostosIndirectos` | `domain/costeo/costos_indirectos.py` | gastos, equipos, capacidad, costeo |
| `ConfiguracionConsultorio`, `CapacidadMensual` | `domain/costeo/capacidad.py` | capacidad, costeo |

## Tratamiento, materiales y precio

| Clase | Capa y ubicación propuesta | Módulos consumidores |
|---|---|---|
| `Tratamiento`, `CostoTiempo` | `domain/costeo/tratamientos.py` | tratamientos, costeo |
| `MetodoMateriales`, `PromedioMisMeses`, `ImporteRapido`, `RecetaInsumos`, `MetodoNoElegido` | `domain/costeo/materiales.py` | insumos, mensuales, tratamientos, costeo |
| `LineaInsumo`, `RegistroMensualMateriales`, `CostoMateriales` | `domain/costeo/materiales.py` | insumos, mensuales, tratamientos, costeo |
| `PoliticaRedondeo`, `CalculadoraPrecio`, `ResultadoPrecio` | `domain/costeo/precio.py` | costeo |

## Orquestación y persistencia

| Clase | Capa y ubicación propuesta | Módulos consumidores |
|---|---|---|
| `SistemaCosteo`, `Bloqueo`, `ResultadoCalculo`, `CalculoCompleto`, `Borrador`, `HojaCostosTratamiento` | `domain/costeo/orquestacion.py` | costeo, tratamientos |
| `EmitirHojaCostosTratamiento` | `application/costeo/emitir_hoja_costos.py` | costeo |
| `RepositorioGastos` | `application/gastos/puertos.py` | gastos, costeo |
| `RepositorioEquipos` | `application/equipos/puertos.py` | equipos, costeo |
| `RepositorioConfiguracion` | `application/capacidad/puertos.py` | capacidad, costeo |
| `RepositorioTratamientos` | `application/tratamientos/puertos.py` | tratamientos, costeo |
| `RepositorioHojasCostos` | `application/costeo/puertos.py` | costeo |

## Módulos fuera del diagrama del motor

| Módulo | Fuente de sus modelos |
|---|---|
| autenticacion | Usuario, membresía y token de actualización del modelo PostgreSQL |
| cuenta | Usuario y organización del modelo PostgreSQL |
| onboarding | Preferencias, especialidades y progreso del modelo PostgreSQL |
| plantillas | Plantillas y materiales sugeridos del modelo PostgreSQL |
| inicio | Proyección de lectura sobre capacidad, tratamientos y costeo |

## Reglas verificables

- El dominio no importa FastAPI, SQLAlchemy, Pydantic ni PostgreSQL.
- `EmitirHojaCostosTratamiento` coordina una única transacción para calcular y guardar.
- Los adaptadores SQLAlchemy implementan puertos definidos por `application`.
- `SET LOCAL app.organizacion_id` se ejecuta en la misma conexión y transacción antes de consultar datos protegidos.
- El cotejo final debe comparar automáticamente todos los nombres declarados en el `.puml` contra esta tabla antes de aprobar el PR.

