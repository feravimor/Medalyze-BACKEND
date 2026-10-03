# ARQ-01 · Tabla «clase del diagrama de clases → módulo»

> Entregable de la tarjeta ARQ-01. Cruza cada clase de
> `Medalyze_Diagrama_Clases_Calculo_Costos.puml` contra los 12 módulos
> definidos en la especificación de la tarjeta. Acompaña al diagrama
> `ARQ-01-capas-y-modulos.puml`.
>
> Criterio de aceptación verificado: **toda clase del diagrama de clases
> tiene lugar asignado** (columnas "Capa" y "Ubicación en domain/costeo").

## Cómo leer esta tabla

- **Capa** seguida en la tarjeta: `domain/costeo` (Python puro) → `application`
  (casos de uso e interfaces de repositorio) → `infrastructure` → `api`.
- **Ubicación en domain/costeo** — todo el dominio vive dentro de un único
  paquete `domain/costeo/`, tal como lo nombra la propia especificación de
  ARQ-01; la subcarpeta indica el agrupamiento interno.
- **Módulo(s) de api/application** — qué módulo(s) de los 12 listados en la
  tarjeta exponen o consumen esa clase.

## Paquete 0 · Tipos de valor y enumeraciones

| Clase | Capa | Ubicación en domain/costeo | Módulo(s) que la usan |
|---|---|---|---|
| `Dinero` | Dominio | `domain/costeo/valores.py` | Transversal: `gastos`, `equipos`, `capacidad`, `tratamientos`, `costeo` |
| `Minutos` | Dominio | `domain/costeo/valores.py` | `capacidad`, `tratamientos`, `costeo` |
| `Porcentaje` | Dominio | `domain/costeo/valores.py` | `capacidad`, `tratamientos`, `costeo` |
| `MesCalendario` | Dominio | `domain/costeo/valores.py` | `mensuales` |
| `Periodicidad` (enum) | Dominio | `domain/costeo/enums.py` | `gastos` |
| `SemaforoMargen` (enum) | Dominio | `domain/costeo/enums.py` | `costeo` |
| `PasoCalculo` (enum) | Dominio | `domain/costeo/enums.py` | `costeo` |
| `CodigoBloqueo` (enum) | Dominio | `domain/costeo/enums.py` | Transversal: todo módulo que dispare un bloqueo (`capacidad`, `gastos`, `insumos`, `mensuales`, `tratamientos`, `costeo`) |

## Paquete 1–2 · Gastos y equipos

| Clase | Capa | Ubicación en domain/costeo | Módulo(s) que la usan |
|---|---|---|---|
| `GastoRegistrado` | Dominio | `domain/costeo/gastos.py` | `gastos` |
| `Equipo` | Dominio | `domain/costeo/equipos.py` | `equipos` |

## Paquete 3–4 · Costos indirectos y capacidad

| Clase | Capa | Ubicación en domain/costeo | Módulo(s) que la usan |
|---|---|---|---|
| `CostosIndirectosMensuales` | Dominio | `domain/costeo/capacidad.py` | `capacidad` (lee de `gastos` y `equipos`) |
| `CalculadoraCostosIndirectos` | Dominio | `domain/costeo/capacidad.py` | `capacidad` |
| `ConfiguracionConsultorio` | Dominio | `domain/costeo/capacidad.py` | `capacidad` |
| `CapacidadMensual` | Dominio | `domain/costeo/capacidad.py` | `capacidad` |

## Paquete 5 · Tratamiento y tiempo

| Clase | Capa | Ubicación en domain/costeo | Módulo(s) que la usan |
|---|---|---|---|
| `Tratamiento` | Dominio | `domain/costeo/tratamientos.py` | `tratamientos` |
| `CostoTiempo` | Dominio | `domain/costeo/tratamientos.py` | `tratamientos`, `costeo` |

## Paquete 6 · Materiales (Strategy + Null Object)

| Clase | Capa | Ubicación en domain/costeo | Módulo(s) que la usan |
|---|---|---|---|
| `MetodoMateriales` (interfaz) | Dominio | `domain/costeo/materiales.py` | `tratamientos`, `costeo` |
| `PromedioMisMeses` | Dominio | `domain/costeo/materiales.py` | `mensuales`, `costeo` |
| `ImporteRapido` | Dominio | `domain/costeo/materiales.py` | `tratamientos`, `costeo` |
| `RecetaInsumos` | Dominio | `domain/costeo/materiales.py` | `insumos`, `tratamientos`, `costeo` |
| `MetodoNoElegido` | Dominio | `domain/costeo/materiales.py` | `tratamientos`, `costeo` |
| `LineaInsumo` | Dominio | `domain/costeo/materiales.py` | `insumos`, `tratamientos` |
| `RegistroMensualMateriales` | Dominio | `domain/costeo/materiales.py` | `mensuales` |
| `CostoMateriales` | Dominio | `domain/costeo/materiales.py` | `tratamientos`, `costeo` |

## Paquete 7 · Precio

| Clase | Capa | Ubicación en domain/costeo | Módulo(s) que la usan |
|---|---|---|---|
| `PoliticaRedondeo` | Dominio | `domain/costeo/precio.py` | `costeo` |
| `CalculadoraPrecio` | Dominio | `domain/costeo/precio.py` | `costeo` |
| `ResultadoPrecio` | Dominio | `domain/costeo/precio.py` | `costeo` |

## Paquete 8 · Orquestación y guardado

| Clase | Capa | Ubicación en domain/costeo | Módulo(s) que la usan |
|---|---|---|---|
| `SistemaCosteo` (Facade) | Dominio | `domain/costeo/orquestacion.py` | `costeo` |
| `Bloqueo` | Dominio | `domain/costeo/orquestacion.py` | `costeo` (y transversal, ver `CodigoBloqueo`) |
| `ResultadoCalculo` (abstracta) | Dominio | `domain/costeo/orquestacion.py` | `costeo` |
| `CalculoCompleto` | Dominio | `domain/costeo/orquestacion.py` | `costeo` |
| `Borrador` | Dominio | `domain/costeo/orquestacion.py` | `costeo` |
| `HojaCostosTratamiento` | Dominio | `domain/costeo/orquestacion.py` | `costeo`, `tratamientos` |
| `EmitirHojaCostosTratamiento` (caso de uso) | **Application** | *(no vive en domain; coordina el dominio)* → `application/costeo/emitir_hoja_costos.py` | `costeo` |
| `RepositorioGastos` (interfaz) | **Application** | → `application/gastos/puertos.py` | `gastos` |
| `RepositorioEquipos` (interfaz) | **Application** | → `application/equipos/puertos.py` | `equipos` |
| `RepositorioConfiguracion` (interfaz) | **Application** | → `application/capacidad/puertos.py` | `capacidad` |
| `RepositorioTratamientos` (interfaz) | **Application** | → `application/tratamientos/puertos.py` | `tratamientos` |
| `RepositorioHojasCostos` (interfaz) | **Application** | → `application/costeo/puertos.py` | `costeo` |

## Paquete 9 · Enumeraciones adicionales (corrección de auditoría)

> Estas 7 enumeraciones existen en el diagrama de clases pero se habían
> omitido de la tabla original. Se agregan aquí tras la revisión cruzada.

| Clase | Capa | Ubicación en domain/costeo | Módulo(s) que la usan |
|---|---|---|---|
| `CategoriaGasto` (enum) | Dominio | `domain/costeo/enums.py` | `gastos` (valores: `FIJO`, `VARIABLE`) |
| `EstadoEquipo` (enum) | Dominio | `domain/costeo/enums.py` | `equipos` (activo / archivado) |
| `EstadoTratamiento` (enum) | Dominio | `domain/costeo/enums.py` | `tratamientos` (valores: `BORRADOR`, `CALCULADO`, `CAMBIOS_POR_REVISAR`) |
| `EstadoRegistro` (enum) | Dominio | `domain/costeo/enums.py` | `mensuales` (valores: `VIGENTE`, `ANULADO`, `SUSTITUIDO`) |
| `TipoRegistro` (enum) | Dominio | `domain/costeo/enums.py` | `mensuales` (valores: `CAPTURA_INICIAL`, `CORRECCION`, `ANULACION`, `RESTAURACION`) |
| `MotivoExclusion` (enum) | Dominio | `domain/costeo/materiales.py` | `mensuales`, `costeo` — por qué un mes no entra al promedio ponderado del Método A |
| `MadurezBase` (enum) | Dominio | `domain/costeo/orquestacion.py` | `costeo` — madurez de la base de datos histórica usada en un cálculo (de `SIN_DATOS` a `CONSOLIDADA_CON_REGISTROS_NATIVOS`) |

## Módulos de la especificación sin clases propias en este diagrama

La tarjeta lista 12 módulos; el diagrama de clases del motor de costos solo
cubre 7 de ellos directamente (`gastos`, `equipos`, `capacidad`, `insumos`,
`mensuales`, `tratamientos`, `costeo`). Los siguientes **no tienen clases
en este diagrama porque pertenecen a otro dominio** (identidad y catálogos,
no cálculo financiero) — sus entidades se definirán a partir del modelo de
base de datos (`medalyze-base-de-datos.puml`) cuando se trabajen sus propias
tarjetas:

| Módulo | Por qué no aparece aquí | De dónde saldrán sus clases |
|---|---|---|
| `autenticacion` | Identidad de usuario, no cálculo de costos | Tabla `usuario_plataforma` |
| `cuenta` | Perfil y organización, no cálculo de costos | Tablas `usuario_plataforma`, `organizacion_consultorio` |
| `onboarding` | Flujo de bienvenida, no cálculo de costos | Tabla `preferencias_onboarding_usuario` |
| `plantillas` | Catálogo de referencia, no cálculo de costos | Tablas `plantilla_tratamiento`, `material_sugerido_plantilla` |
| `inicio` | Agregación de KPIs de otros módulos, sin entidad propia | Lectura combinada de varios módulos (ver `GET /inicio/resumen` en ARQ-03) |

## Confirmación de los otros 2 criterios de aceptación de ARQ-01

- **HU-20 · CA3 — "Emitir una hoja de costos es una sola transacción":**
  queda modelado en `EmitirHojaCostosTratamiento` (capa application), que
  coordina `SistemaCosteo.calcular(...)` y, si el resultado es
  `CalculoCompleto`, guarda la `HojaCostosTratamiento` a través de
  `RepositorioHojasCostos` — ambas operaciones dentro de la misma
  transacción de base de datos (ver también BE-01: "Una transacción por
  request de escritura").
- **HU-31 — "El aislamiento por organización queda definido en BD y en la
  aplicación":** en la aplicación, cada request ejecuta
  `SET LOCAL app.organizacion_id` (capa `infrastructure/seguridad`, según
  la propia especificación de ARQ-01); en la base de datos, se refuerza con
  RLS sobre `identificador_organizacion` en cada tabla (ver BE-01 y
  `medalyze-base-de-datos.puml`). Son dos capas de defensa independientes,
  no una sola.
