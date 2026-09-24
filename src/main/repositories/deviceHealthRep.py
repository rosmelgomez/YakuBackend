from sqlalchemy.orm import Session

from src.main.model.models import (
    asignaciones_iot,
    configuracion_tanque,
    dispositivos,
    riego,
    tipos_dispositivo,
)

# Solo el firmware de flujometro (conexion directa) reporta cada ~1s mientras
# riega; el de tanque (ultrasonico) publica solo al inicio y al fin del ciclo,
# asi que su silencio durante un riego es normal y no indica desconexion.
METODO_REPORTE_CONTINUO = "flujometro"


def queryTouchDeviceByAssignmentAssignment(db: Session, assignment_id):
    return (
        db.query(asignaciones_iot).filter(asignaciones_iot.id == assignment_id).first()
    )


def queryRiegosPausadosPorDesconexionReconectados(db: Session, online_cutoff):
    """Riegos pausados por desconexion cuyo actuador volvio a reportar
    (ultimo_ping reciente y posterior al momento de la pausa)."""
    return (
        db.query(riego, asignaciones_iot)
        .join(asignaciones_iot, asignaciones_iot.id == riego.id_asignacion)
        .join(dispositivos, dispositivos.id_dispositivo == asignaciones_iot.id_dispositivo)
        .join(tipos_dispositivo, tipos_dispositivo.id == dispositivos.id_tipo)
        .filter(
            tipos_dispositivo.metodo_medicion == METODO_REPORTE_CONTINUO,
            riego.estado == False,  # noqa: E712
            riego.motivo_cierre.like("pausado_desconexion_riego%"),
            asignaciones_iot.activo == True,  # noqa: E712
            dispositivos.ultimo_ping.isnot(None),
            dispositivos.ultimo_ping >= online_cutoff,
            dispositivos.ultimo_ping > riego.fecha,
        )
        .all()
    )


def queryStaleActuatorDevicesWithActiveSession(db: Session, cutoff):
    """Actuadores (flujometro/proximidad) que dejaron de reportar antes de
    `cutoff` Y que ademas tienen un riego realmente en curso (estado=False)
    en alguna de sus asignaciones activas. A diferencia del chequeo general
    de dispositivos "stale", este NO se aplica a actuadores inactivos (estan
    legitimamente en silencio cuando no estan regando)."""
    return (
        db.query(dispositivos)
        .join(asignaciones_iot)
        .join(tipos_dispositivo, tipos_dispositivo.id == dispositivos.id_tipo)
        .join(riego, riego.id_asignacion == asignaciones_iot.id)
        .filter(
            tipos_dispositivo.metodo_medicion == METODO_REPORTE_CONTINUO,
            asignaciones_iot.activo == True,
            dispositivos.ultimo_ping.isnot(None),
            dispositivos.ultimo_ping < cutoff,
            riego.estado == False,
            # El tramo actual debe llevar mas que el timeout: un riego recien
            # iniciado sobre un actuador que estaba inactivo tiene un ping
            # viejo antes de que el dispositivo alcance a responder al ON.
            riego.fecha < cutoff,
            # Excluir los ya pausados: si no, cada 10s se re-pausaba el mismo
            # riego y se reenviaba la notificacion de desconexion en bucle.
            riego.motivo_cierre.is_(None) | ~riego.motivo_cierre.like("pausado_%"),
        )
        .distinct()
        .all()
    )


def queryShutdownActuatorStateConfig(db: Session, assignment):
    return (
        db.query(configuracion_tanque)
        .filter(configuracion_tanque.id_asignacion == assignment.id)
        .first()
    )


def queryShutdownActuatorStateActiveSession(db: Session, assignment):
    return (
        db.query(riego)
        .filter(riego.id_asignacion == assignment.id, riego.estado == False)
        .first()
    )


def queryDeactivateCropActuatorsActuatorAssignments(db: Session, user_id, crop_id):
    return (
        db.query(asignaciones_iot)
        .join(dispositivos)
        .filter(
            asignaciones_iot.id_usuario == user_id,
            asignaciones_iot.id_cultivo == crop_id,
            asignaciones_iot.activo == True,
        )
        .all()
    )


def querySyncDeviceHealthStaleDevices(db: Session, cutoff):
    return (
        db.query(dispositivos)
        .join(asignaciones_iot)
        .filter(
            asignaciones_iot.activo == True,
            dispositivos.ultimo_ping.isnot(None),
            dispositivos.ultimo_ping < cutoff,
        )
        .distinct()
        .all()
    )
