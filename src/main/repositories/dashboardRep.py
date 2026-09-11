from sqlalchemy.orm import Session

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
        .filter(
            configuracion_umbrales.id_usuario == userId,
            configuracion_umbrales.id_cultivo.in_(cultivo_ids),
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
            riego.estado == True,
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
        .filter(
            configuracion_umbrales.id_usuario == userId,
            configuracion_umbrales.id_cultivo == idCultivo,
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
    return db.query(tipos_metrica).order_by(tipos_metrica.id.asc()).all()


def queryObtenerDatosAlertasUmbralesRaw2(db: Session, userId, idCultivo):
    return (
        db.query(configuracion_umbrales)
        .filter(
            configuracion_umbrales.id_usuario == userId,
            configuracion_umbrales.id_cultivo == idCultivo,
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
        .filter(
            alertas.estado.in_(("pendiente", "activa")),
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
        .filter(
            alertas.estado == "resuelta",
            asignaciones_iot.id_cultivo == idCultivo,
            asignaciones_iot.id_usuario == userId,
        )
        .order_by(alertas.fecha.desc())
        .limit(10)
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
        .filter(
            configuracion_umbrales.id_usuario == userId,
            configuracion_umbrales.id_cultivo == idCultivo,
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
        .filter(tipos_alerta.activo == True)
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
