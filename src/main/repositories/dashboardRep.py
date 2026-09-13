from sqlalchemy import func, or_
from sqlalchemy.orm import Session, aliased

from src.main.model.models import (
    alertas,
    asignaciones_iot,
    componentes,
    configuracion_control,
    configuracion_notificaciones,
    configuracion_umbrales,
    cultivo_modelo,
    cultivos,
    dispositivos,
    fuentes_agua,
    humedad_ambiente,
    humedad_suelo,
    logs_sistema,
    modelos_ml,
    plantas,
    predicciones_ml,
    riego,
    telemetria_tanque,
    temperatura_ambiente,
    temperatura_suelo,
    tipos_alerta,
    tipos_componente,
    tipos_metrica,
    umbrales_planta,
    usuarios,
)


EXCLUDED_UMBRAL_METRICS = ["NIVEL_AGUA", "BAT_PCT", "CAUDAL"]


def queryComponentContextMapsComponentes(db: Session, component_ids):
    return db.query(componentes).filter(componentes.id.in_(component_ids)).all()


def queryComponentContextMapsTiposComponente(db: Session, tipo_component_ids):
    return (
        db.query(tipos_componente)
        .filter(tipos_componente.id.in_(tipo_component_ids))
        .all()
    )


def queryComponentContextMapsTiposMetrica(db: Session, tipo_metrica_ids):
    return db.query(tipos_metrica).filter(tipos_metrica.id.in_(tipo_metrica_ids)).all()


def queryObtenerDatosDashboardUsuario(db: Session, userId):
    return db.query(usuarios).filter(usuarios.id_usuario == userId).first()


def queryObtenerDatosDashboardDbCultivos(db: Session, userId):
    return (
        db.query(cultivos)
        .filter(cultivos.id_usuario == userId, cultivos.estado == "activo")
        .all()
    )


def queryObtenerDatosDashboardPlantas(db: Session, planta_ids):
    return db.query(plantas).filter(plantas.id_planta.in_(planta_ids)).all()


def queryObtenerDatosDashboardFuentesAgua(db: Session, fuente_ids):
    return db.query(fuentes_agua).filter(fuentes_agua.id.in_(fuente_ids)).all()


def queryObtenerDatosDashboardUmbralesPlanta(db: Session, planta_ids):
    return (
        db.query(umbrales_planta)
        .filter(umbrales_planta.id_planta.in_(planta_ids))
        .all()
    )


def queryObtenerDatosDashboardConfiguracionControl(db: Session, userId, cultivo_ids):
    return (
        db.query(configuracion_control)
        .filter(
            configuracion_control.id_usuario == userId,
            configuracion_control.id_cultivo.in_(cultivo_ids),
        )
        .all()
    )


def queryObtenerDatosDashboardConfiguracionUmbrales(db: Session, userId, cultivo_ids):
    return (
        db.query(configuracion_umbrales)
        .join(tipos_metrica, configuracion_umbrales.id_tipo_metrica == tipos_metrica.id)
        .filter(
            configuracion_umbrales.id_usuario == userId,
            configuracion_umbrales.id_cultivo.in_(cultivo_ids),
            ~tipos_metrica.codigo.in_(EXCLUDED_UMBRAL_METRICS),
        )
        .all()
    )


def queryObtenerDatosDashboardAsigsAll(db: Session, userId, cultivo_ids):
    return (
        db.query(asignaciones_iot)
        .filter(
            asignaciones_iot.id_usuario == userId,
            asignaciones_iot.id_cultivo.in_(cultivo_ids),
        )
        .all()
    )


def queryObtenerDatosDashboardDispositivos(db: Session, device_ids):
    return (
        db.query(dispositivos).filter(dispositivos.id_dispositivo.in_(device_ids)).all()
    )


def _query_latest_per_assignment(db: Session, model, asig_ids, require_valido: bool = True):
    if not asig_ids:
        return []
    if db.bind and db.bind.dialect.name == "postgresql":
        query = db.query(model).filter(model.id_asignacion.in_(asig_ids))
        if require_valido and hasattr(model, "valido"):
            query = query.filter(model.valido == True)
        return (
            query.distinct(model.id_asignacion)
            .order_by(model.id_asignacion, model.fecha.desc())
            .all()
        )

    rn = func.row_number().over(
        partition_by=model.id_asignacion,
        order_by=model.fecha.desc(),
    ).label("rn")
    filters = [model.id_asignacion.in_(asig_ids)]
    if require_valido and hasattr(model, "valido"):
        filters.append(model.valido == True)
    subq = db.query(model, rn).filter(*filters).subquery()
    alias = aliased(model, subq)
    return db.query(alias).filter(subq.c.rn == 1).all()


def queryUltimaLecturaHumedadSuelo(db: Session, asig_ids):
    return _query_latest_per_assignment(db, humedad_suelo, asig_ids, require_valido=True)


def queryUltimaLecturaHumedadAmbiente(db: Session, asig_ids):
    return _query_latest_per_assignment(db, humedad_ambiente, asig_ids, require_valido=True)


def queryUltimaLecturaTemperaturaSuelo(db: Session, asig_ids):
    return _query_latest_per_assignment(db, temperatura_suelo, asig_ids, require_valido=True)


def queryUltimaLecturaTemperaturaAmbiente(db: Session, asig_ids):
    return _query_latest_per_assignment(db, temperatura_ambiente, asig_ids, require_valido=True)


def queryUltimaTelemetriaTanque(db: Session, asig_ids):
    return _query_latest_per_assignment(db, telemetria_tanque, asig_ids, require_valido=False)


def queryHistorialAgregadoHumedadSuelo(db: Session, asig_ids, fechaLimite7d):
    if not asig_ids:
        return []
    metric_expr = func.coalesce(humedad_suelo.ema, humedad_suelo.valor)
    if db.bind and db.bind.dialect.name == "postgresql":
        bucket_expr = func.date_trunc("hour", humedad_suelo.fecha)
    else:
        bucket_expr = func.strftime("%Y-%m-%d %H:00:00", humedad_suelo.fecha)
    return (
        db.query(
            humedad_suelo.id_asignacion,
            bucket_expr.label("fecha"),
            func.avg(metric_expr).label("valor"),
        )
        .filter(
            humedad_suelo.id_asignacion.in_(asig_ids),
            humedad_suelo.valido == True,
            humedad_suelo.fecha >= fechaLimite7d,
        )
        .group_by(humedad_suelo.id_asignacion, bucket_expr)
        .order_by(bucket_expr.asc())
        .all()
    )


def queryHistorialAgregadoHumedadAmbiente(db: Session, asig_ids, fechaLimite7d):
    if not asig_ids:
        return []
    metric_expr = func.coalesce(humedad_ambiente.ema, humedad_ambiente.valor)
    if db.bind and db.bind.dialect.name == "postgresql":
        bucket_expr = func.date_trunc("hour", humedad_ambiente.fecha)
    else:
        bucket_expr = func.strftime("%Y-%m-%d %H:00:00", humedad_ambiente.fecha)
    return (
        db.query(
            humedad_ambiente.id_asignacion,
            bucket_expr.label("fecha"),
            func.avg(metric_expr).label("valor"),
        )
        .filter(
            humedad_ambiente.id_asignacion.in_(asig_ids),
            humedad_ambiente.valido == True,
            humedad_ambiente.fecha >= fechaLimite7d,
        )
        .group_by(humedad_ambiente.id_asignacion, bucket_expr)
        .order_by(bucket_expr.asc())
        .all()
    )


def queryHistorialAgregadoTemperaturaSuelo(db: Session, asig_ids, fechaLimite7d):
    if not asig_ids:
        return []
    metric_expr = func.coalesce(temperatura_suelo.ema, temperatura_suelo.temperatura, temperatura_suelo.valor)
    if db.bind and db.bind.dialect.name == "postgresql":
        bucket_expr = func.date_trunc("hour", temperatura_suelo.fecha)
    else:
        bucket_expr = func.strftime("%Y-%m-%d %H:00:00", temperatura_suelo.fecha)
    return (
        db.query(
            temperatura_suelo.id_asignacion,
            bucket_expr.label("fecha"),
            func.avg(metric_expr).label("valor"),
        )
        .filter(
            temperatura_suelo.id_asignacion.in_(asig_ids),
            temperatura_suelo.valido == True,
            temperatura_suelo.fecha >= fechaLimite7d,
        )
        .group_by(temperatura_suelo.id_asignacion, bucket_expr)
        .order_by(bucket_expr.asc())
        .all()
    )


def queryHistorialAgregadoTemperaturaAmbiente(db: Session, asig_ids, fechaLimite7d):
    if not asig_ids:
        return []
    metric_expr = func.coalesce(temperatura_ambiente.ema, temperatura_ambiente.temperatura, temperatura_ambiente.valor)
    if db.bind and db.bind.dialect.name == "postgresql":
        bucket_expr = func.date_trunc("hour", temperatura_ambiente.fecha)
    else:
        bucket_expr = func.strftime("%Y-%m-%d %H:00:00", temperatura_ambiente.fecha)
    return (
        db.query(
            temperatura_ambiente.id_asignacion,
            bucket_expr.label("fecha"),
            func.avg(metric_expr).label("valor"),
        )
        .filter(
            temperatura_ambiente.id_asignacion.in_(asig_ids),
            temperatura_ambiente.valido == True,
            temperatura_ambiente.fecha >= fechaLimite7d,
        )
        .group_by(temperatura_ambiente.id_asignacion, bucket_expr)
        .order_by(bucket_expr.asc())
        .all()
    )


def queryObtenerDatosDashboardHumedadSuelo(db: Session, asig_ids, fechaLimite7d):
    return (
        db.query(humedad_suelo)
        .filter(
            humedad_suelo.id_asignacion.in_(asig_ids),
            humedad_suelo.valido == True,
            humedad_suelo.fecha >= fechaLimite7d,
        )
        .order_by(humedad_suelo.fecha.desc())
        .all()
    )


def queryObtenerDatosDashboardHumedadAmbiente(db: Session, asig_ids, fechaLimite7d):
    return (
        db.query(humedad_ambiente)
        .filter(
            humedad_ambiente.id_asignacion.in_(asig_ids),
            humedad_ambiente.valido == True,
            humedad_ambiente.fecha >= fechaLimite7d,
        )
        .order_by(humedad_ambiente.fecha.desc())
        .all()
    )


def queryObtenerDatosDashboardTemperaturaSuelo(db: Session, asig_ids, fechaLimite7d):
    return (
        db.query(temperatura_suelo)
        .filter(
            temperatura_suelo.id_asignacion.in_(asig_ids),
            temperatura_suelo.valido == True,
            temperatura_suelo.fecha >= fechaLimite7d,
        )
        .order_by(temperatura_suelo.fecha.desc())
        .all()
    )


def queryObtenerDatosDashboardTemperaturaAmbiente(db: Session, asig_ids, fechaLimite7d):
    return (
        db.query(temperatura_ambiente)
        .filter(
            temperatura_ambiente.id_asignacion.in_(asig_ids),
            temperatura_ambiente.valido == True,
            temperatura_ambiente.fecha >= fechaLimite7d,
        )
        .order_by(temperatura_ambiente.fecha.desc())
        .all()
    )


def queryObtenerDatosDashboardTelemetriaTanque(db: Session, asig_ids):
    return (
        db.query(telemetria_tanque)
        .filter(telemetria_tanque.id_asignacion.in_(asig_ids))
        .order_by(telemetria_tanque.fecha.desc())
        .all()
    )


def queryObtenerDatosDashboardRiego(db: Session, asig_ids, fechaLimiteConsumoUtc):
    return (
        db.query(riego)
        .filter(
            riego.id_asignacion.in_(asig_ids),
            riego.fecha >= fechaLimiteConsumoUtc,
            or_(riego.estado == True, riego.cantidad_agua_litros > 0),
        )
        .all()
    )


def queryObtenerDatosDashboardTiposMetrica(db: Session):
    return (
        db.query(tipos_metrica)
        .filter(
            tipos_metrica.codigo.in_(("HUM_SUELO", "HUM_AMB", "TEMP_AMB", "TEMP_SUELO"))
        )
        .all()
    )


def queryObtenerDatosDashboardTiposMetrica2(db: Session, metricas_config_ids):
    return (
        db.query(tipos_metrica).filter(tipos_metrica.id.in_(metricas_config_ids)).all()
    )


def queryObtenerDatosAlertasUsuario(db: Session, userId):
    return db.query(usuarios).filter(usuarios.id_usuario == userId).first()


def queryObtenerDatosAlertasUmbralesRaw(db: Session, userId, idCultivo):
    return (
        db.query(configuracion_umbrales)
        .join(tipos_metrica, configuracion_umbrales.id_tipo_metrica == tipos_metrica.id)
        .filter(
            configuracion_umbrales.id_usuario == userId,
            configuracion_umbrales.id_cultivo == idCultivo,
            ~tipos_metrica.codigo.in_(EXCLUDED_UMBRAL_METRICS),
        )
        .order_by(configuracion_umbrales.id.asc())
        .all()
    )


def queryObtenerDatosAlertasCultivoDb(db: Session, idCultivo):
    return db.query(cultivos).filter(cultivos.id_cultivo == idCultivo).first()


def queryObtenerDatosAlertasUmbralesRecomendados(db: Session, id_planta):
    return (
        db.query(umbrales_planta).filter(umbrales_planta.id_planta == id_planta).all()
    )


def queryObtenerDatosAlertasTipos(db: Session):
    return (
        db.query(tipos_metrica)
        .filter(~tipos_metrica.codigo.in_(EXCLUDED_UMBRAL_METRICS))
        .order_by(tipos_metrica.id.asc())
        .all()
    )


def queryObtenerDatosAlertasUmbralesRaw2(db: Session, userId, idCultivo):
    return (
        db.query(configuracion_umbrales)
        .join(tipos_metrica, configuracion_umbrales.id_tipo_metrica == tipos_metrica.id)
        .filter(
            configuracion_umbrales.id_usuario == userId,
            configuracion_umbrales.id_cultivo == idCultivo,
            ~tipos_metrica.codigo.in_(EXCLUDED_UMBRAL_METRICS),
        )
        .order_by(configuracion_umbrales.id.asc())
        .all()
    )


def queryObtenerDatosAlertasTiposMetrica(db: Session, tipo_metrica_ids):
    return db.query(tipos_metrica).filter(tipos_metrica.id.in_(tipo_metrica_ids)).all()


def queryObtenerDatosAlertasAlertasActivasRaw(db: Session, idCultivo, userId):
    return (
        db.query(alertas)
        .join(asignaciones_iot, alertas.id_asignacion == asignaciones_iot.id)
        .join(tipos_alerta, alertas.id_tipo_alerta == tipos_alerta.id)
        .filter(
            alertas.estado.in_(("pendiente", "activa")),
            alertas.id_tipo_metrica.is_(None),
            tipos_alerta.activo.is_(True),
            asignaciones_iot.id_cultivo == idCultivo,
            asignaciones_iot.id_usuario == userId,
        )
        .order_by(alertas.fecha.desc())
        .all()
    )


def queryObtenerDatosAlertasTiposAlerta(db: Session, alertas_activas_tipo_ids):
    return (
        db.query(tipos_alerta)
        .filter(tipos_alerta.id.in_(alertas_activas_tipo_ids))
        .all()
    )


def queryObtenerDatosAlertasTiposMetrica2(db: Session, alertas_activas_metrica_ids):
    return (
        db.query(tipos_metrica)
        .filter(tipos_metrica.id.in_(alertas_activas_metrica_ids))
        .all()
    )


def queryObtenerDatosAlertasAsignacionesIot(db: Session, alertas_activas_asig_ids):
    return (
        db.query(asignaciones_iot)
        .filter(asignaciones_iot.id.in_(alertas_activas_asig_ids))
        .all()
    )


def queryObtenerDatosAlertasHistorialRaw(db: Session, idCultivo, userId):
    return (
        db.query(alertas)
        .join(asignaciones_iot, alertas.id_asignacion == asignaciones_iot.id)
        .join(tipos_alerta, alertas.id_tipo_alerta == tipos_alerta.id)
        .filter(
            alertas.estado == "resuelta",
            alertas.id_tipo_metrica.is_(None),
            tipos_alerta.activo.is_(True),
            asignaciones_iot.id_cultivo == idCultivo,
            asignaciones_iot.id_usuario == userId,
        )
        .order_by(alertas.fecha.desc())
        .limit(20)
        .all()
    )


def queryObtenerDatosAlertasTiposAlerta2(db: Session, historial_tipo_ids):
    return db.query(tipos_alerta).filter(tipos_alerta.id.in_(historial_tipo_ids)).all()


def queryObtenerDatosAlertasTiposMetrica3(db: Session, historial_metrica_ids):
    return (
        db.query(tipos_metrica)
        .filter(tipos_metrica.id.in_(historial_metrica_ids))
        .all()
    )


def queryObtenerDatosHistoricoUsuario(db: Session, userId):
    return db.query(usuarios).filter(usuarios.id_usuario == userId).first()


def queryObtenerDatosHistoricoAsigs(db: Session, userId, idCultivo):
    return (
        db.query(asignaciones_iot)
        .filter(
            asignaciones_iot.id_usuario == userId,
            asignaciones_iot.id_cultivo == idCultivo,
        )
        .all()
    )


def queryObtenerDatosHistoricoHumedadSuelo(
    db: Session, asignaciones_ids, fechaLimiteUtc
):
    return (
        db.query(humedad_suelo)
        .filter(
            humedad_suelo.id_asignacion.in_(asignaciones_ids),
            humedad_suelo.valido == True,
            humedad_suelo.fecha >= fechaLimiteUtc,
        )
        .all()
    )


def queryObtenerDatosHistoricoHumedadAmbiente(
    db: Session, asignaciones_ids, fechaLimiteUtc
):
    return (
        db.query(humedad_ambiente)
        .filter(
            humedad_ambiente.id_asignacion.in_(asignaciones_ids),
            humedad_ambiente.valido == True,
            humedad_ambiente.fecha >= fechaLimiteUtc,
        )
        .all()
    )


def queryObtenerDatosHistoricoTemperaturaSuelo(
    db: Session, asignaciones_ids, fechaLimiteUtc
):
    return (
        db.query(temperatura_suelo)
        .filter(
            temperatura_suelo.id_asignacion.in_(asignaciones_ids),
            temperatura_suelo.valido == True,
            temperatura_suelo.fecha >= fechaLimiteUtc,
        )
        .all()
    )


def queryObtenerDatosHistoricoTemperaturaAmbiente(
    db: Session, asignaciones_ids, fechaLimiteUtc
):
    return (
        db.query(temperatura_ambiente)
        .filter(
            temperatura_ambiente.id_asignacion.in_(asignaciones_ids),
            temperatura_ambiente.valido == True,
            temperatura_ambiente.fecha >= fechaLimiteUtc,
        )
        .all()
    )


def queryHistoricoAgregadoMetrica(
    db: Session, model, asig_ids, fechaLimiteUtc, is_hourly: bool, user_tz_str: str = "UTC"
):
    if not asig_ids:
        return []

    if hasattr(model, "temperatura"):
        val_expr = func.coalesce(model.ema, model.temperatura, model.valor)
    else:
        val_expr = func.coalesce(model.ema, model.valor)

    if db.bind and db.bind.dialect.name == "postgresql":
        local_ts = func.timezone(user_tz_str, func.timezone("UTC", model.fecha))
        format_mask = "YYYY-MM-DD HH24:00" if is_hourly else "YYYY-MM-DD"
        group_expr = func.to_char(local_ts, format_mask)
    else:
        group_expr = func.strftime(
            "%Y-%m-%d %H:00" if is_hourly else "%Y-%m-%d", model.fecha
        )

    return (
        db.query(
            model.id_asignacion,
            group_expr.label("bucket"),
            func.avg(val_expr).label("avg_val"),
            func.min(val_expr).label("min_val"),
            func.max(val_expr).label("max_val"),
            func.sum(val_expr).label("sum_val"),
            func.count(model.id).label("count_val"),
        )
        .filter(
            model.id_asignacion.in_(asig_ids),
            model.valido == True,
            model.fecha >= fechaLimiteUtc,
        )
        .group_by(model.id_asignacion, group_expr)
        .order_by(group_expr.asc())
        .all()
    )


def queryObtenerDatosHistoricoRiegosRecientes(
    db: Session, fechaLimiteUtc, asignaciones_ids
):
    return (
        db.query(riego)
        .filter(
            riego.estado == True,
            riego.fecha >= fechaLimiteUtc,
            riego.id_asignacion.in_(asignaciones_ids),
        )
        .order_by(riego.fecha.desc())
        .all()
    )


def queryObtenerDatosMlUsrMod(db: Session, userId, idCultivo):
    return (
        db.query(cultivo_modelo)
        .filter(
            cultivo_modelo.id_usuario == userId, cultivo_modelo.id_cultivo == idCultivo
        )
        .order_by(cultivo_modelo.fecha_asignacion.desc())
        .first()
    )


def queryObtenerDatosMlDefaultModel(db: Session):
    return db.query(modelos_ml).filter(modelos_ml.es_default == True).first()


def queryObtenerDatosMlDefaultModel2(db: Session):
    return db.query(modelos_ml).order_by(modelos_ml.id_modelo.asc()).first()


def queryObtenerDatosMlModeloActivo(db: Session, usr_mod):
    return (
        db.query(modelos_ml).filter(modelos_ml.id_modelo == usr_mod.id_modelo).first()
    )


def queryObtenerDatosMlAsigs(db: Session, userId, idCultivo):
    return (
        db.query(asignaciones_iot)
        .filter(
            asignaciones_iot.id_usuario == userId,
            asignaciones_iot.id_cultivo == idCultivo,
        )
        .all()
    )


def queryObtenerDatosMlHumSuelo(db: Session, ids_asig):
    return (
        db.query(humedad_suelo)
        .filter(humedad_suelo.id_asignacion.in_(ids_asig), humedad_suelo.valido == True)
        .order_by(humedad_suelo.fecha.desc())
        .limit(15)
        .all()
    )


def queryObtenerDatosMlHumAmb(db: Session, ids_asig):
    return (
        db.query(humedad_ambiente)
        .filter(
            humedad_ambiente.id_asignacion.in_(ids_asig),
            humedad_ambiente.valido == True,
        )
        .order_by(humedad_ambiente.fecha.desc())
        .limit(15)
        .all()
    )


def queryObtenerDatosMlTempSuelo(db: Session, ids_asig):
    return (
        db.query(temperatura_suelo)
        .filter(
            temperatura_suelo.id_asignacion.in_(ids_asig),
            temperatura_suelo.valido == True,
        )
        .order_by(temperatura_suelo.fecha.desc())
        .limit(15)
        .all()
    )


def queryObtenerDatosMlTempAmb(db: Session, ids_asig):
    return (
        db.query(temperatura_ambiente)
        .filter(
            temperatura_ambiente.id_asignacion.in_(ids_asig),
            temperatura_ambiente.valido == True,
        )
        .order_by(temperatura_ambiente.fecha.desc())
        .limit(15)
        .all()
    )


def queryObtenerDatosMlUsuario(db: Session, userId):
    return db.query(usuarios).filter(usuarios.id_usuario == userId).first()


def queryObtenerDatosMlUmbrales(db: Session, userId, idCultivo):
    return (
        db.query(configuracion_umbrales)
        .join(tipos_metrica, configuracion_umbrales.id_tipo_metrica == tipos_metrica.id)
        .filter(
            configuracion_umbrales.id_usuario == userId,
            configuracion_umbrales.id_cultivo == idCultivo,
            ~tipos_metrica.codigo.in_(EXCLUDED_UMBRAL_METRICS),
        )
        .all()
    )


def queryObtenerDatosMlTipoM(db: Session, u):
    return db.query(tipos_metrica).filter(tipos_metrica.id == u.id_tipo_metrica).first()


def queryObtenerDatosMlPreds(db: Session, userId, idCultivo):
    return (
        db.query(predicciones_ml)
        .filter(
            predicciones_ml.id_usuario == userId,
            predicciones_ml.id_cultivo == idCultivo,
        )
        .order_by(predicciones_ml.fecha.desc())
        .limit(15)
        .all()
    )


def queryObtenerDatosMlR(db: Session, p):
    return db.query(riego).filter(riego.id_prediccion == p.id_prediccion).first()


def queryObtenerDatosMlCultivoDb(db: Session, idCultivo):
    return db.query(cultivos).filter(cultivos.id_cultivo == idCultivo).first()


def queryObtenerDatosMlModelosDb(db: Session):
    return db.query(modelos_ml).all()


def queryObtenerDatosMlRiegosAll(db: Session, ids_asig):
    return (
        db.query(riego)
        .filter(riego.id_asignacion.in_(ids_asig))
        .order_by(riego.fecha.asc())
        .all()
    )


def queryObtenerDatosMlHumRecords(db: Session, ids_asig):
    return (
        db.query(humedad_suelo)
        .filter(humedad_suelo.id_asignacion.in_(ids_asig), humedad_suelo.valido == True)
        .all()
    )


def queryObtenerDatosDashboardAdminUsuarios(db: Session, userId):
    return db.query(usuarios).filter(usuarios.id_usuario == userId).first()


def queryObtenerDatosDashboardAdminTotalUsuarios(db: Session):
    return db.query(usuarios).count()


def queryObtenerDatosDashboardAdminTotalDispositivos(db: Session):
    return db.query(dispositivos).count()


def queryObtenerDatosDashboardAdminTotalDispositivosActivos(db: Session):
    return db.query(dispositivos).filter(dispositivos.estado == "asignado").count()


def queryObtenerDatosDashboardAdminTotalCultivosActivos(db: Session):
    return db.query(cultivos).filter(cultivos.estado == "activo").count()


def queryObtenerDatosDashboardAdminAlertasPendientes(db: Session):
    return db.query(alertas).filter(alertas.estado.in_(("pendiente", "activa"))).count()


def queryObtenerDatosDashboardAdminDbLogs(db: Session):
    return db.query(logs_sistema).order_by(logs_sistema.fecha.desc()).limit(50).all()


def queryObtenerDatosDashboardAdminUsr(db: Session, l):
    return db.query(usuarios).filter(usuarios.id_usuario == l.id_usuario).first()


def queryObtenerDatosDashboardAdminDbPreds(db: Session):
    return (
        db.query(predicciones_ml).order_by(predicciones_ml.fecha.desc()).limit(50).all()
    )


def queryObtenerDatosDashboardAdminUsr2(db: Session, p):
    return db.query(usuarios).filter(usuarios.id_usuario == p.id_usuario).first()


def queryObtenerDatosDashboardAdminCult(db: Session, p):
    return db.query(cultivos).filter(cultivos.id_cultivo == p.id_cultivo).first()


def queryObtenerDatosDashboardAdminMod(db: Session, p):
    return db.query(modelos_ml).filter(modelos_ml.id_modelo == p.id_modelo).first()


def queryObtenerDatosDashboardAdminDbModels(db: Session):
    return db.query(modelos_ml).all()


def queryObtenerDatosDashboardAdminTotalPredModel(db: Session, m):
    return (
        db.query(predicciones_ml)
        .filter(predicciones_ml.id_modelo == m.id_modelo)
        .count()
    )


def queryObtenerDatosDashboardAdminRiegosGlobales(db: Session, inicio_de_limite):
    return (
        db.query(riego)
        .filter(riego.fecha >= inicio_de_limite, riego.estado == True)
        .all()
    )


def queryObtenerDatosDashboardAdminDbAllUsers(db: Session):
    return db.query(usuarios).all()


def queryObtenerDatosDashboardAdminDbAllCrops(db: Session):
    return db.query(cultivos).all()


def queryGetCultivosBaseRows(db: Session, current_user):
    return (
        db.query(cultivos.id_cultivo, cultivos.nombre_planta)
        .filter(
            cultivos.id_usuario == current_user.id_usuario, cultivos.estado == "activo"
        )
        .order_by(cultivos.id_cultivo.asc())
        .all()
    )


def queryGetNotifConfigTipos(db: Session):
    return (
        db.query(tipos_alerta)
        .filter(
            tipos_alerta.activo == True,
            tipos_alerta.id.notin_([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]),
            ~tipos_alerta.codigo.like("ALERT_%"),
        )
        .order_by(tipos_alerta.id.asc())
        .all()
    )


def queryGetNotifConfigPref(db: Session, current_user, t):
    return (
        db.query(configuracion_notificaciones)
        .filter(
            configuracion_notificaciones.id_usuario == current_user.id_usuario,
            configuracion_notificaciones.id_tipo_alerta == t.id,
        )
        .first()
    )


def queryUpdateNotifConfigPref(db: Session, current_user, u):
    return (
        db.query(configuracion_notificaciones)
        .filter(
            configuracion_notificaciones.id_usuario == current_user.id_usuario,
            configuracion_notificaciones.id_tipo_alerta == u.id_tipo_alerta,
        )
        .first()
    )
