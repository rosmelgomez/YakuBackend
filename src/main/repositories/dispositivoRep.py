from sqlalchemy.orm import Session

from src.main.model.models import (
    almacenes,
    asignaciones_iot,
    componentes,
    configuracion_tanque,
    cultivo_modelo,
    cultivos,
    dispositivos,
    humedad_ambiente,
    humedad_suelo,
    temperatura_ambiente,
    temperatura_suelo,
    tipos_componente,
    tipos_dispositivo,
    tipos_metrica,
    usuarios,
)


def queryListarDispositivosResultado(db: Session, id_usuario):
    return (
        db.query(dispositivos)
        .join(asignaciones_iot)
        .filter(
            asignaciones_iot.id_usuario == id_usuario,
            dispositivos.en_almacen == False,
        )
        .distinct()
        .all()
    )


def queryListarDispositivosResultado2(db: Session):
    return db.query(dispositivos).all()


def queryListarMisDispositivosResultado(db: Session, current_user):
    return (
        db.query(dispositivos)
        .join(asignaciones_iot)
        .filter(
            asignaciones_iot.id_usuario == current_user.id_usuario,
            dispositivos.en_almacen == False,
        )
        .distinct()
        .all()
    )


def queryListarTiposDispositivoResultado(db: Session):
    return db.query(tipos_dispositivo).all()


def queryDeviceType(db: Session, type_id: int):
    return db.get(tipos_dispositivo, type_id)


def queryListarTiposMetricaResultado(db: Session):
    return db.query(tipos_metrica).order_by(tipos_metrica.id.asc()).all()


def queryListarTiposComponenteResultado(db: Session):
    return db.query(tipos_componente).all()


def queryListarComponentesResultado(db: Session):
    return db.query(componentes).order_by(componentes.id.asc()).all()


def queryObtenerSiguienteClientIdItems(db: Session):
    return (
        db.query(dispositivos.client_id_mqtt)
        .filter(dispositivos.client_id_mqtt.like("ESP32_Yaku_%"))
        .all()
    )


def queryActivarDispositivoDispositivo(db: Session, dispositivo_id):
    return (
        db.query(dispositivos)
        .filter(dispositivos.id_dispositivo == dispositivo_id)
        .first()
    )


def queryDesactivarDispositivoDispositivo(db: Session, dispositivo_id):
    return (
        db.query(dispositivos)
        .filter(dispositivos.id_dispositivo == dispositivo_id)
        .first()
    )


def queryActualizarFuncionamientoUsuarioDispositivo(db: Session, dispositivo_id):
    return (
        db.query(dispositivos)
        .filter(dispositivos.id_dispositivo == dispositivo_id)
        .first()
    )


def queryActualizarFuncionamientoUsuarioAsigQuery(db: Session, dispositivo_id):
    return db.query(asignaciones_iot).filter(
        asignaciones_iot.id_dispositivo == dispositivo_id
    )


def queryActualizarFuncionamientoUsuarioAsigQuery2(asig_query, current_user):
    return asig_query.filter(asignaciones_iot.id_usuario == current_user.id_usuario)


def queryActualizarFuncionamientoUsuarioAsigs(asig_query):
    return asig_query.all()


def queryActualizarFuncionamientoUsuarioSensorActivo(db: Session, cultivos_ids):
    return (
        db.query(asignaciones_iot)
        .join(dispositivos)
        .filter(
            asignaciones_iot.id_cultivo.in_(cultivos_ids),
            dispositivos.id_tipo == 1,
            asignaciones_iot.activo == True,
        )
        .first()
    )


def queryActualizarFuncionamientoUsuarioUsrMod(db: Session, asig):
    return (
        db.query(cultivo_modelo)
        .filter(
            cultivo_modelo.id_usuario == asig.id_usuario,
            cultivo_modelo.id_cultivo == asig.id_cultivo,
            cultivo_modelo.activo == True,
        )
        .first()
    )


def queryActualizarFuncionamientoUsuarioSensorAsigs(db: Session, asig):
    return (
        db.query(asignaciones_iot)
        .join(dispositivos)
        .filter(
            asignaciones_iot.id_cultivo == asig.id_cultivo, dispositivos.id_tipo == 1
        )
        .all()
    )


def queryActualizarFuncionamientoUsuarioHSuelo(db: Session, sensor_asig_ids):
    return (
        db.query(humedad_suelo)
        .filter(humedad_suelo.id_asignacion.in_(sensor_asig_ids))
        .order_by(humedad_suelo.id.desc())
        .first()
    )


def queryActualizarFuncionamientoUsuarioHAmb(db: Session, sensor_asig_ids):
    return (
        db.query(humedad_ambiente)
        .filter(humedad_ambiente.id_asignacion.in_(sensor_asig_ids))
        .order_by(humedad_ambiente.id.desc())
        .first()
    )


def queryActualizarFuncionamientoUsuarioTAmb(db: Session, sensor_asig_ids):
    return (
        db.query(temperatura_ambiente)
        .filter(temperatura_ambiente.id_asignacion.in_(sensor_asig_ids))
        .order_by(temperatura_ambiente.id.desc())
        .first()
    )


def queryActualizarFuncionamientoUsuarioTSuelo(db: Session, sensor_asig_ids):
    return (
        db.query(temperatura_suelo)
        .filter(temperatura_suelo.id_asignacion.in_(sensor_asig_ids))
        .order_by(temperatura_suelo.id.desc())
        .first()
    )


def queryEstablecerFuncionamientoDispositivoLegacyDispositivo(
    db: Session, dispositivo_id
):
    return (
        db.query(dispositivos)
        .filter(dispositivos.id_dispositivo == dispositivo_id)
        .first()
    )


def queryListarDispositivosDeUsuarioUsuarioObj(db: Session, id_user):
    return db.query(usuarios).filter(usuarios.id_usuario == id_user).first()


def queryListarDispositivosDeUsuarioDevs(db: Session, id_user):
    return (
        db.query(dispositivos)
        .join(asignaciones_iot)
        .filter(
            asignaciones_iot.id_usuario == id_user,
            dispositivos.en_almacen == False,
        )
        .distinct()
        .order_by(dispositivos.id_dispositivo)
        .all()
    )


def queryListarDispositivosDeUsuarioAsigs(db: Session, d):
    return (
        db.query(asignaciones_iot)
        .filter(
            asignaciones_iot.id_dispositivo == d.id_dispositivo,
            asignaciones_iot.id_componente != None,
        )
        .order_by(asignaciones_iot.id)
        .all()
    )


def queryObtenerConfigDispositivosUsuarioUsuarioObj(db: Session, id_user):
    return db.query(usuarios).filter(usuarios.id_usuario == id_user).first()


def queryObtenerConfigDispositivosUsuarioDevs(db: Session, id_user):
    return (
        db.query(dispositivos)
        .join(asignaciones_iot)
        .filter(
            asignaciones_iot.id_usuario == id_user,
            dispositivos.en_almacen == False,
        )
        .distinct()
        .order_by(dispositivos.id_dispositivo)
        .all()
    )


def queryObtenerConfigDispositivosUsuarioAsigs(db: Session, d):
    return (
        db.query(asignaciones_iot)
        .filter(
            asignaciones_iot.id_dispositivo == d.id_dispositivo,
            asignaciones_iot.id_componente != None,
        )
        .order_by(asignaciones_iot.id)
        .all()
    )


def queryProcesarActivacionDispositivoDispositivo(db: Session, dispositivo_id):
    return (
        db.query(dispositivos)
        .filter(dispositivos.id_dispositivo == dispositivo_id)
        .first()
    )


def queryProcesarActivacionDispositivoAsigQuery(db: Session, dispositivo_id):
    return db.query(asignaciones_iot).filter(
        asignaciones_iot.id_dispositivo == dispositivo_id
    )


def queryProcesarActivacionDispositivoAsigQuery2(asig_query, current_user):
    return asig_query.filter(asignaciones_iot.id_usuario == current_user.id_usuario)


def queryProcesarActivacionDispositivoAsigs(asig_query):
    return asig_query.all()


def queryListarStockDisponiblesResultado(db: Session):
    return db.query(dispositivos).filter(dispositivos.estado == "disponible").all()


def queryAsignarDispositivoACultivoDev(db: Session, dispositivo_id):
    return (
        db.query(dispositivos)
        .filter(dispositivos.id_dispositivo == dispositivo_id)
        .first()
    )


def queryAsignarDispositivoACultivoCult(db: Session, id_cultivo, id_usuario):
    return (
        db.query(cultivos)
        .filter(cultivos.id_cultivo == id_cultivo, cultivos.id_usuario == id_usuario)
        .first()
    )


def queryLiberarDispositivoAStockDev(db: Session, dispositivo_id):
    return (
        db.query(dispositivos)
        .filter(dispositivos.id_dispositivo == dispositivo_id)
        .first()
    )


def queryLiberarDispositivoAStockPrimerAlmacen(db: Session):
    return db.query(almacenes).order_by(almacenes.id.asc()).first()


def queryLiberarDispositivoAStockAsigs(db: Session, dispositivo_id):
    return (
        db.query(asignaciones_iot)
        .filter(asignaciones_iot.id_dispositivo == dispositivo_id)
        .all()
    )


def queryLiberarDispositivoAStockComp(db: Session, asig):
    return db.query(componentes).filter(componentes.id == asig.id_componente).first()


def queryCalibrarSensorRemotoDispositivo(db: Session, dispositivo_id):
    return (
        db.query(dispositivos)
        .filter(dispositivos.id_dispositivo == dispositivo_id)
        .first()
    )


def queryCalibrarSensorRemotoAsig(db: Session, dispositivo_id, current_user):
    return (
        db.query(asignaciones_iot)
        .filter(
            asignaciones_iot.id_dispositivo == dispositivo_id,
            asignaciones_iot.id_usuario == current_user.id_usuario,
        )
        .first()
    )


def queryCalibrarSensorRemotoAsigPorPin(db: Session, dispositivo_id, pin_gpio):
    return (
        db.query(asignaciones_iot)
        .filter(
            asignaciones_iot.id_dispositivo == dispositivo_id,
            asignaciones_iot.pin_gpio == pin_gpio,
        )
        .order_by(asignaciones_iot.activo.desc(), asignaciones_iot.id.desc())
        .first()
    )


def queryRegistrarDispositivoExistenteMac(db: Session, payload):
    return (
        db.query(dispositivos)
        .filter(dispositivos.mac_address == payload.mac_address)
        .first()
    )


def queryRegistrarDispositivoExistenteMqtt(db: Session, payload):
    return (
        db.query(dispositivos)
        .filter(dispositivos.client_id_mqtt == payload.client_id_mqtt)
        .first()
    )


def queryRegistrarComponenteExistente(db: Session, payload):
    return (
        db.query(componentes)
        .filter(componentes.numero_serie == payload.numero_serie)
        .first()
    )


def queryCambiarEstadoDispositivoStockDev(db: Session, dispositivo_id):
    return (
        db.query(dispositivos)
        .filter(dispositivos.id_dispositivo == dispositivo_id)
        .first()
    )


def queryCambiarEstadoComponenteStockComp(db: Session, componente_id):
    return db.query(componentes).filter(componentes.id == componente_id).first()


def queryAsignarComponenteDispositivoComp(db: Session, payload):
    return db.query(componentes).filter(componentes.id == payload.id_componente).first()


def queryAsignarComponenteDispositivoExistingAsig(db: Session, comp, payload):
    return (
        db.query(asignaciones_iot)
        .filter(
            asignaciones_iot.id_componente == comp.id,
            asignaciones_iot.id_dispositivo == payload.id_dispositivo,
        )
        .first()
    )


def queryAsignarComponenteDispositivoDev(db: Session, payload):
    return (
        db.query(dispositivos)
        .filter(dispositivos.id_dispositivo == payload.id_dispositivo)
        .first()
    )


def queryAsignarComponenteDispositivoBaseAsig(db: Session, payload):
    return (
        db.query(asignaciones_iot)
        .filter(asignaciones_iot.id_dispositivo == payload.id_dispositivo)
        .first()
    )


def queryAsignarComponenteDispositivoConfig(db: Session, existing_asig):
    return (
        db.query(configuracion_tanque)
        .filter(configuracion_tanque.id_asignacion == existing_asig.id)
        .first()
    )


def queryLiberarComponenteDispositivoComp(db: Session, componente_id):
    return db.query(componentes).filter(componentes.id == componente_id).first()


def queryLiberarComponenteDispositivoAsigs(db: Session, componente_id):
    return (
        db.query(asignaciones_iot)
        .filter(asignaciones_iot.id_componente == componente_id)
        .all()
    )


def queryLiberarComponenteDispositivoFirstDevice(db: Session, asigs):
    return (
        db.query(dispositivos)
        .filter(dispositivos.id_dispositivo == asigs[0].id_dispositivo)
        .first()
    )


def queryLiberarComponenteDispositivoPrimerAlmacen(db: Session):
    return db.query(almacenes).order_by(almacenes.id.asc()).first()


def queryActualizarAsignacionComponenteAsig(db: Session, asignacion_id):
    return (
        db.query(asignaciones_iot)
        .filter(asignaciones_iot.id == asignacion_id)
        .first()
    )


def queryObtenerDetalleDispositivoDispositivo(db: Session, dispositivo_id):
    return (
        db.query(dispositivos)
        .filter(dispositivos.id_dispositivo == dispositivo_id)
        .first()
    )


def queryConfiguracionTanquePorAsignacion(db: Session, asig_id: int):
    return (
        db.query(configuracion_tanque)
        .filter(configuracion_tanque.id_asignacion == asig_id)
        .first()
    )
