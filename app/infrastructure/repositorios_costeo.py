from decimal import Decimal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.domain.costeo.periodicidad import equivalente_mensual


class _RepositorioSQLAlchemy:
    def __init__(self, sesion: Session) -> None:
        self.sesion = sesion


class RepositorioGastosSQLAlchemy(_RepositorioSQLAlchemy):
    def totales_mensuales(self, organizacion: UUID) -> tuple[Decimal, Decimal]:
        """Devuelve (fijos, variables) por mes, con la fracción exacta de cada periodicidad."""
        filas = (
            self.sesion.execute(
                text("""
                    SELECT g.categoria::text categoria, g.importe_pagado_por_periodo importe,
                           g.codigo_periodicidad periodicidad
                    FROM gasto_registrado g
                    WHERE g.identificador_organizacion=:organizacion AND g.activo
                      AND g.fecha_inicio_vigencia<=current_date
                      AND (g.fecha_fin_vigencia IS NULL OR g.fecha_fin_vigencia>=current_date)
                """),
                {"organizacion": organizacion},
            )
            .mappings()
            .all()
        )
        fijos = Decimal(0)
        variables = Decimal(0)
        for fila in filas:
            mensual = equivalente_mensual(Decimal(fila["importe"]), fila["periodicidad"])
            if fila["categoria"] == "FIJO":
                fijos += mensual
            else:
                variables += mensual
        return fijos, variables


class RepositorioEquiposSQLAlchemy(_RepositorioSQLAlchemy):
    def depreciacion_mensual(self, organizacion: UUID) -> Decimal:
        """Suma la depreciación de los equipos ACTIVOS cuya vida útil sigue vigente (HU-09 CA1)."""
        valor = self.sesion.scalar(
            text("""
                SELECT coalesce(sum(depreciacion_mensual),0)
                FROM equipo_o_instalacion_depreciable
                WHERE identificador_organizacion=:organizacion AND estado='ACTIVO'
                  AND (fecha_alta_en_servicio IS NULL OR (
                        fecha_alta_en_servicio<=current_date
                        AND extract(year FROM age(current_date, fecha_alta_en_servicio))*12
                          + extract(month FROM age(current_date, fecha_alta_en_servicio))
                            < vida_util_anios*12))
            """),
            {"organizacion": organizacion},
        )
        return Decimal(valor or 0)


class RepositorioConfiguracionSQLAlchemy(_RepositorioSQLAlchemy):
    def capacidad_vigente(self, organizacion: UUID) -> dict | None:
        fila = (
            self.sesion.execute(
                text("""
                    SELECT dias_por_semana,horas_por_dia,porcentaje_ocupacion
                    FROM perfil_capacidad_atencion
                    WHERE identificador_organizacion=:organizacion AND fecha_fin_vigencia IS NULL
                """),
                {"organizacion": organizacion},
            )
            .mappings()
            .first()
        )
        return dict(fila) if fila else None

    def organizacion(self, identificador: UUID) -> dict:
        fila = (
            self.sesion.execute(
                text("""
                    SELECT multiplo_redondeo,espaciado_por_defecto
                    FROM organizacion_consultorio WHERE identificador=:identificador
                """),
                {"identificador": identificador},
            )
            .mappings()
            .one()
        )
        return dict(fila)


class RepositorioTratamientosSQLAlchemy(_RepositorioSQLAlchemy):
    def obtener_con_configuracion(
        self, organizacion: UUID, tratamiento: UUID
    ) -> tuple[dict, dict] | None:
        fila_tratamiento = (
            self.sesion.execute(
                text("""
                    SELECT * FROM tratamiento
                    WHERE identificador=:tratamiento AND identificador_organizacion=:organizacion
                """),
                {"tratamiento": tratamiento, "organizacion": organizacion},
            )
            .mappings()
            .first()
        )
        if fila_tratamiento is None:
            return None
        fila_configuracion = (
            self.sesion.execute(
                text("""
                    SELECT * FROM version_configuracion_tratamiento
                    WHERE identificador=:version
                """),
                {"version": fila_tratamiento["identificador_version_vigente"]},
            )
            .mappings()
            .first()
        )
        if fila_configuracion is None:
            return None
        return dict(fila_tratamiento), dict(fila_configuracion)


class RepositorioHojasCostosSQLAlchemy(_RepositorioSQLAlchemy):
    def detalle(self, organizacion: UUID, hoja: UUID) -> dict | None:
        fila = (
            self.sesion.execute(
                text("""
                    SELECT * FROM hoja_costos_tratamiento
                    WHERE identificador=:hoja AND identificador_organizacion=:organizacion
                """),
                {"hoja": hoja, "organizacion": organizacion},
            )
            .mappings()
            .first()
        )
        return dict(fila) if fila else None


class RepositorioInsumosSQLAlchemy(_RepositorioSQLAlchemy):
    def precio_unitario_vigente(self, organizacion: UUID, insumo: UUID) -> Decimal | None:
        valor = self.sesion.scalar(
            text("""
                SELECT precio.costo_unitario
                FROM insumo_clinico insumo
                JOIN LATERAL (
                  SELECT costo_unitario FROM precio_historico_insumo
                  WHERE identificador_insumo=insumo.identificador
                    AND fecha_inicio_vigencia<=current_date
                  ORDER BY fecha_inicio_vigencia DESC,fecha_hora_creacion DESC LIMIT 1
                ) precio ON true
                WHERE insumo.identificador=:insumo
                  AND insumo.identificador_organizacion=:organizacion
                  AND insumo.fecha_hora_archivado IS NULL
            """),
            {"insumo": insumo, "organizacion": organizacion},
        )
        return Decimal(valor) if valor is not None else None


class RepositorioPeriodosMensualesSQLAlchemy(_RepositorioSQLAlchemy):
    def periodos_elegibles(self, organizacion: UUID, limite: int = 3) -> list[dict]:
        filas = (
            self.sesion.execute(
                text("""
                    SELECT p.identificador,p.mes,v.consumo_materiales,v.tratamientos_atendidos
                    FROM periodo_mensual_consumo p
                    JOIN version_periodo_mensual_consumo v
                      ON v.identificador=p.identificador_version_vigente
                    WHERE p.identificador_organizacion=:organizacion AND p.mes<=current_date
                      AND v.tipo_movimiento<>'ANULACION' AND v.tratamientos_atendidos>0
                    ORDER BY p.mes DESC LIMIT :limite
                """),
                {"organizacion": organizacion, "limite": limite},
            )
            .mappings()
            .all()
        )
        return [dict(fila) for fila in filas]
