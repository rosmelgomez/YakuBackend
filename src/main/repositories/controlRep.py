from datetime import datetime

from sqlalchemy.orm import Session

from src.main.model.models import (
    asignaciones_iot,
    componentes,
    configuracion_control,
    configuracion_tanque,
    configuracion_umbrales,
    cultivo_modelo,
    dispositivos,
    humedad_ambiente,
    humedad_suelo,
    logs_sistema,
    modelos_ml,
    predicciones_ml,
    programacion_riego,
    riego,
    roles,
    telemetria_tanque,
    temperatura_ambiente,
    temperatura_suelo,
    tipos_componente,
    tipos_dispositivo,
    usuarios,
    cultivos,
)


def queryObtenerDatosControlUsuario(db: Session, userId):
    return db.query(usuarios).filter(usuarios.id_usuario == userId).first()


def queryObtenerDatosControlRol(db: Session, user_rol_id):
    return db.query(roles).filter(roles.id_rol == user_rol_id).first()


def queryObtenerDatosControlAsigs(db: Session, userId, idCultivo):
    return (
        db.query(asignaciones_iot)
        .filter(
            asignaciones_iot.id_usuario == userId,
            asignaciones_iot.id_cultivo == idCultivo,
        )
        .all()
    )


def queryObtenerDatosControlConfigT(db: Session, a):
    return (
        db.query(configuracion_tanque)
        .filter(configuracion_tanque.id_asignacion == a.id)
        .first()
    )


def queryObtenerDatosControlDev(db: Session, a):
    return (
        db.query(dispositivos)
        .filter(dispositivos.id_dispositivo == a.id_dispositivo)
        .first()
    )


def queryObtenerDatosControlConfigC(db: Session, userId, idCultivo):
    return (
        db.query(configuracion_control)
        .filter(
            configuracion_control.id_usuario == userId,
            configuracion_control.id_cultivo == idCultivo,
        )
        .first()
    )


def queryObtenerDatosControlUsrMod(db: Session, userId, idCultivo):
    return (
        db.query(cultivo_modelo)
        .filter(
            cultivo_modelo.id_usuario == userId, cultivo_modelo.id_cultivo == idCultivo
        )
        .order_by(cultivo_modelo.fecha_asignacion.desc())
        .first()
    )


def queryObtenerDatosControlDefaultModel(db: Session):
    return db.query(modelos_ml).filter(modelos_ml.es_default == True).first()


def queryObtenerDatosControlDefaultModel2(db: Session):
    return db.query(modelos_ml).order_by(modelos_ml.id_modelo.asc()).first()


def queryObtenerDatosControlProgramaciones(db: Session, userId, id_bomba):
    return (
        db.query(programacion_riego)
        .filter(
            programacion_riego.id_usuario == userId,
            programacion_riego.id_asignacion == id_bomba,
        )
        .order_by(programacion_riego.hora_inicio.asc())
        .all()
    )


def queryObtenerDatosControlSysLogs(db: Session, userId):
    return (
        db.query(logs_sistema)
        .filter(logs_sistema.id_usuario == userId)
        .order_by(logs_sistema.fecha.desc())
        .limit(20)
        .all()
    )


def queryObtenerDatosControlUltimaPred(db: Session, userId, idCultivo):
    return (
        db.query(predicciones_ml)
        .filter(
            predicciones_ml.id_usuario == userId,
            predicciones_ml.id_cultivo == idCultivo,
        )
        .order_by(predicciones_ml.fecha.desc())
        .first()
    )


def queryObtenerDatosControlModelo(db: Session, ultima_pred):
    return (
        db.query(modelos_ml)
        .filter(modelos_ml.id_modelo == ultima_pred.id_modelo)
        .first()
    )


def queryObtenerDatosControlCultivo(db: Session, idCultivo):
    return db.query(cultivos).filter(cultivos.id == idCultivo).first()


def queryObtenerDatosControlUltimaSesion(db: Session, userId, idCultivo):
    return (
        db.query(riego)
        .join(asignaciones_iot, riego.id_asignacion == asignaciones_iot.id)
        .filter(
            riego.id_usuario == userId,
            asignaciones_iot.id_cultivo == idCultivo,
            riego.estado == True,
        )
        .order_by(riego.fecha_fin.desc().nullslast(), riego.fecha.desc())
        .first()
    )


def queryObtenerDatosControlSesionPausada(db: Session, id_bomba):
    return (
        db.query(riego)
        .filter(
            riego.id_asignacion == id_bomba,
            riego.estado == False,
            riego.motivo_cierre.like("pausado_%"),
        )
        .order_by(riego.id.desc())
        .first()
    )


def queryObtenerDatosControlSesionActiva(db: Session, id_bomba):
    return (
        db.query(riego)
        .filter(
            riego.id_asignacion == id_bomba,
            riego.estado == False,
            riego.motivo_cierre.is_(None) | ~riego.motivo_cierre.like("pausado_%"),
        )
        .order_by(riego.id.desc())
        .first()
    )


def queryObtenerDatosControlDev2(db: Session, a):
    return (
        db.query(dispositivos)
        .filter(dispositivos.id_dispositivo == a.id_dispositivo)
        .first()
    )


def queryObtenerDatosControlTipo(db: Session, dev):
    return (
        db.query(tipos_dispositivo).filter(tipos_dispositivo.id == dev.id_tipo).first()
    )


def queryObtenerDatosControlComp(db: Session, a2):
    return db.query(componentes).filter(componentes.id == a2.id_componente).first()


def queryObtenerDatosControlTipoComp(db: Session, comp):
    return (
        db.query(tipos_componente)
        .filter(tipos_componente.id == comp.id_tipo_componente)
        .first()
    )


def queryEstablecerModoOperacionAsig(db: Session, id_bomba):
    return db.query(asignaciones_iot).filter(asignaciones_iot.id == id_bomba).first()


def queryEstablecerModoOperacionCultivoModelo(db: Session, userId, idCultivo):
    return (
        db.query(cultivo_modelo)
        .filter(
            cultivo_modelo.id_usuario == userId, cultivo_modelo.id_cultivo == idCultivo
        )
        .update({"activo": False})
    )


def queryEstablecerModoOperacionProgramacionRiego(db: Session, userId, id_bomba):
    return (
        db.query(programacion_riego)
        .filter(
            programacion_riego.id_usuario == userId,
            programacion_riego.id_asignacion == id_bomba,
        )
        .update({"activo": False})
    )


def queryEstablecerModoOperacionUsrMod(db: Session, userId, idCultivo):
    return (
        db.query(cultivo_modelo)
        .filter(
            cultivo_modelo.id_usuario == userId, cultivo_modelo.id_cultivo == idCultivo
        )
        .order_by(cultivo_modelo.fecha_asignacion.desc())
        .first()
    )


def queryEstablecerModoOperacionPrimerModelo(db: Session):
    return db.query(modelos_ml).order_by(modelos_ml.id_modelo.asc()).first()


def queryEstablecerModoOperacionAsig2(db: Session, id_bomba):
    return db.query(asignaciones_iot).filter(asignaciones_iot.id == id_bomba).first()


def queryEstablecerModoOperacionSensorAsigs(db: Session, idCultivo):
    return (
        db.query(asignaciones_iot)
        .join(dispositivos)
        .filter(asignaciones_iot.id_cultivo == idCultivo, dispositivos.id_tipo == 1)
        .all()
    )


def queryEstablecerModoOperacionHSuelo(db: Session, sensor_asig_ids):
    return (
        db.query(humedad_suelo)
        .filter(humedad_suelo.id_asignacion.in_(sensor_asig_ids))
        .order_by(humedad_suelo.id.desc())
        .first()
    )


def queryEstablecerModoOperacionHAmb(db: Session, sensor_asig_ids):
    return (
        db.query(humedad_ambiente)
        .filter(humedad_ambiente.id_asignacion.in_(sensor_asig_ids))
        .order_by(humedad_ambiente.id.desc())
        .first()
    )


def queryEstablecerModoOperacionTAmb(db: Session, sensor_asig_ids):
    return (
        db.query(temperatura_ambiente)
        .filter(temperatura_ambiente.id_asignacion.in_(sensor_asig_ids))
        .order_by(temperatura_ambiente.id.desc())
        .first()
    )


def queryEstablecerModoOperacionTSuelo(db: Session, sensor_asig_ids):
    return (
        db.query(temperatura_suelo)
        .filter(temperatura_suelo.id_asignacion.in_(sensor_asig_ids))
        .order_by(temperatura_suelo.id.desc())
        .first()
    )


def queryEstablecerModoOperacionProgramacionRiego2(db: Session, userId, id_bomba):
    return (
        db.query(programacion_riego)
        .filter(
            programacion_riego.id_usuario == userId,
            programacion_riego.id_asignacion == id_bomba,
        )
        .update({"activo": True})
    )


def queryEstablecerModoOperacionAsig3(db: Session, id_bomba):
    return db.query(asignaciones_iot).filter(asignaciones_iot.id == id_bomba).first()


def queryConmutarBombaManualAsig(db: Session, idBomba):
    return db.query(asignaciones_iot).filter(asignaciones_iot.id == idBomba).first()


def queryConmutarValvulaManualAsig(db: Session, idBomba):
    return db.query(asignaciones_iot).filter(asignaciones_iot.id == idBomba).first()


def queryConmutarValvulaManualConfig(db: Session, asig):
    return (
        db.query(configuracion_tanque)
        .filter(configuracion_tanque.id_asignacion == asig.id)
        .first()
    )


def queryActualizarTiempoMaximoReleConfig(db: Session, userId, idCultivo):
    return (
        db.query(configuracion_control)
        .filter(
            configuracion_control.id_usuario == userId,
            configuracion_control.id_cultivo == idCultivo,
        )
        .first()
    )


def queryCrearHorarioRiegoAsig(db: Session, idBomba):
    return db.query(asignaciones_iot).filter(asignaciones_iot.id == idBomba).first()


def queryActualizarHorarioRiegoHorario(db: Session, id_horario, userId):
    return (
        db.query(programacion_riego)
        .filter(
            programacion_riego.id == id_horario, programacion_riego.id_usuario == userId
        )
        .first()
    )


def queryConmutarHorarioRiegoHorario(db: Session, id_horario, userId):
    return (
        db.query(programacion_riego)
        .filter(
            programacion_riego.id == id_horario, programacion_riego.id_usuario == userId
        )
        .first()
    )


def queryEliminarHorarioRiegoHorario(db: Session, id_horario, userId):
    return (
        db.query(programacion_riego)
        .filter(
            programacion_riego.id == id_horario, programacion_riego.id_usuario == userId
        )
        .first()
    )


def queryConmutarBombaPorTelemetriaTelemetria(db: Session, id_telemetria):
    return (
        db.query(telemetria_tanque)
        .filter(telemetria_tanque.id == id_telemetria)
        .first()
    )


def queryConmutarBombaPorTelemetriaAsig(db: Session, telemetria):
    return (
        db.query(asignaciones_iot)
        .filter(asignaciones_iot.id == telemetria.id_asignacion)
        .first()
    )


def queryConmutarBombaPorTelemetriaPumpAssignment(db: Session, userId, asig):
    return (
        db.query(asignaciones_iot)
        .join(
            configuracion_tanque,
            configuracion_tanque.id_asignacion == asignaciones_iot.id,
        )
        .filter(
            asignaciones_iot.id_dispositivo == asig.id_dispositivo,
            asignaciones_iot.id_usuario == userId,
        )
        .first()
    )


def queryActualizarUmbralesRiegoConfiguracionUmbrales(
    db: Session, u, userId, id_cultivo
):
    return (
        db.query(configuracion_umbrales)
        .filter(
            configuracion_umbrales.id == u.id,
            configuracion_umbrales.id_usuario == userId,
            configuracion_umbrales.id_cultivo == id_cultivo,
        )
        .update(
            {
                "valor_minimo": u.min,
                "valor_maximo": u.max,
                "actualizado_en": datetime.now(),
            }
        )
    )
