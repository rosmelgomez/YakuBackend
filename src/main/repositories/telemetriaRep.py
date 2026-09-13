"""Persistencia de las lecturas de sensores y telemetría."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from src.main.dtos.telemetriaDto import RiegoDatosModel
from src.main.model.models import (
    asignaciones_iot,
    configuracion_tanque,
    cultivo_modelo,
    humedad_ambiente,
    humedad_suelo,
    predicciones_ml,
    telemetria_tanque,
    temperatura_ambiente,
    temperatura_suelo,
)


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _to_utc_naive(fecha: datetime | None) -> datetime:
    if fecha is None:
        return _utc_now_naive()
    if fecha.tzinfo is None:
        return fecha
    return fecha.astimezone(timezone.utc).replace(tzinfo=None)


def crear_humedad_suelo(
    db: Session,
    id_asignacion: int,
    valor: float | None,
    porcentaje: float | None,
    ema: float | None = None,
    desviacion: float | None = None,
    valido: bool | None = True,
    fecha: datetime | None = None,
) -> humedad_suelo:
    registro = humedad_suelo(
        id_asignacion=id_asignacion,
        valor=valor,
        porcentaje=porcentaje,
        ema=ema,
        desviacion=desviacion,
        valido=valido if valido is not None else True,
        fecha=_to_utc_naive(fecha),
    )
    db.add(registro)
    db.commit()
    db.refresh(registro)
    return registro


def crear_humedad_ambiente(
    db: Session,
    id_asignacion: int,
    valor: float | None,
    porcentaje: float | None,
    ema: float | None = None,
    desviacion: float | None = None,
    valido: bool | None = True,
    fecha: datetime | None = None,
) -> humedad_ambiente:
    registro = humedad_ambiente(
        id_asignacion=id_asignacion,
        valor=valor,
        porcentaje=porcentaje,
        ema=ema,
        desviacion=desviacion,
        valido=valido if valido is not None else True,
        fecha=_to_utc_naive(fecha),
    )
    db.add(registro)
    db.commit()
    db.refresh(registro)
    return registro


def crear_temperatura_ambiente(
    db: Session,
    id_asignacion: int,
    valor: float | None,
    temperatura: float | None,
    ema: float | None = None,
    desviacion: float | None = None,
    valido: bool | None = True,
    fecha: datetime | None = None,
) -> temperatura_ambiente:
    registro = temperatura_ambiente(
        id_asignacion=id_asignacion,
        valor=valor,
        temperatura=temperatura,
        ema=ema,
        desviacion=desviacion,
        valido=valido if valido is not None else True,
        fecha=_to_utc_naive(fecha),
    )
    db.add(registro)
    db.commit()
    db.refresh(registro)
    return registro


def crear_temperatura_suelo(
    db: Session,
    id_asignacion: int,
    valor: float | None,
    temperatura: float | None,
    ema: float | None = None,
    desviacion: float | None = None,
    valido: bool | None = True,
    fecha: datetime | None = None,
) -> temperatura_suelo:
    registro = temperatura_suelo(
        id_asignacion=id_asignacion,
        valor=valor,
        temperatura=temperatura,
        ema=ema,
        desviacion=desviacion,
        valido=valido if valido is not None else True,
        fecha=_to_utc_naive(fecha),
    )
    db.add(registro)
    db.commit()
    db.refresh(registro)
    return registro


def crear_datos_riego(
    db: Session,
    data: RiegoDatosModel,
) -> None:
    # Obtener los IDs de asignación entrantes
    ids = {
        data.humedad_suelo.id_asignacion,
        data.humedad_ambiente.id_asignacion,
        data.temperatura_ambiente.id_asignacion,
        data.temperatura_suelo.id_asignacion,
    }
    # Consultar cuáles de estos IDs realmente existen en asignaciones_iot
    valid_ids = {
        r[0]
        for r in db.query(asignaciones_iot.id)
        .filter(asignaciones_iot.id.in_(ids))
        .all()
    }

    if data.humedad_suelo.id_asignacion in valid_ids:
        crear_humedad_suelo(
            db,
            id_asignacion=data.humedad_suelo.id_asignacion,
            valor=data.humedad_suelo.valor,
            porcentaje=data.humedad_suelo.porcentaje,
            ema=data.humedad_suelo.ema,
            desviacion=data.humedad_suelo.desviacion,
            valido=data.humedad_suelo.valido,
            fecha=data.humedad_suelo.fecha,
        )
    if data.humedad_ambiente.id_asignacion in valid_ids:
        crear_humedad_ambiente(
            db,
            id_asignacion=data.humedad_ambiente.id_asignacion,
            valor=data.humedad_ambiente.valor,
            porcentaje=data.humedad_ambiente.porcentaje,
            ema=data.humedad_ambiente.ema,
            desviacion=data.humedad_ambiente.desviacion,
            valido=data.humedad_ambiente.valido,
            fecha=data.humedad_ambiente.fecha,
        )
    if data.temperatura_ambiente.id_asignacion in valid_ids:
        crear_temperatura_ambiente(
            db,
            id_asignacion=data.temperatura_ambiente.id_asignacion,
            valor=data.temperatura_ambiente.valor,
            temperatura=data.temperatura_ambiente.temperatura,
            ema=data.temperatura_ambiente.ema,
            desviacion=data.temperatura_ambiente.desviacion,
            valido=data.temperatura_ambiente.valido,
            fecha=data.temperatura_ambiente.fecha,
        )
    if data.temperatura_suelo.id_asignacion in valid_ids:
        crear_temperatura_suelo(
            db,
            id_asignacion=data.temperatura_suelo.id_asignacion,
            valor=data.temperatura_suelo.valor,
            temperatura=data.temperatura_suelo.temperatura,
            ema=data.temperatura_suelo.ema,
            desviacion=data.temperatura_suelo.desviacion,
            valido=data.temperatura_suelo.valido,
            fecha=data.temperatura_suelo.fecha,
        )


def listar_humedad_suelo(db: Session) -> list[humedad_suelo]:
    return db.query(humedad_suelo).order_by(humedad_suelo.id.desc()).all()


def listar_humedad_ambiente(db: Session) -> list[humedad_ambiente]:
    return db.query(humedad_ambiente).order_by(humedad_ambiente.id.desc()).all()


def listar_temperatura_ambiente(db: Session) -> list[temperatura_ambiente]:
    return db.query(temperatura_ambiente).order_by(temperatura_ambiente.id.desc()).all()


def listar_temperatura_suelo(db: Session) -> list[temperatura_suelo]:
    return db.query(temperatura_suelo).order_by(temperatura_suelo.id.desc()).all()


def listar_telemetria_tanque(db: Session) -> list[telemetria_tanque]:
    return db.query(telemetria_tanque).order_by(telemetria_tanque.id.desc()).all()


import datetime as dt

from sqlalchemy.orm import Session

from src.main.model.models import (
    ejecucion_riego,
    fuentes_agua,
    humedad_ambiente,
    humedad_suelo,
    riego,
    telemetria_tanque,
    temperatura_ambiente,
    temperatura_suelo,
)


def queryVerificarAccesoAsignacionesAsig(db: Session, asig_id):
    return (
        db.query(asignaciones_iot)
        .filter(asignaciones_iot.id == asig_id, asignaciones_iot.activo == True)
        .first()
    )


def queryObtenerHumedadSueloUserAssignments(db: Session, id_usuario):
    return (
        db.query(asignaciones_iot.id)
        .filter(asignaciones_iot.id_usuario == id_usuario)
        .subquery()
    )


def queryObtenerHumedadSueloResultado(db: Session, user_assignments):
    return (
        db.query(humedad_suelo)
        .filter(humedad_suelo.id_asignacion.in_(user_assignments))
        .order_by(humedad_suelo.id.desc())
        .all()
    )


def queryObtenerHumedadAmbienteUserAssignments(db: Session, current_user):
    return (
        db.query(asignaciones_iot.id)
        .filter(asignaciones_iot.id_usuario == current_user.id_usuario)
        .subquery()
    )


def queryObtenerHumedadAmbienteResultado(db: Session, user_assignments):
    return (
        db.query(humedad_ambiente)
        .filter(humedad_ambiente.id_asignacion.in_(user_assignments))
        .order_by(humedad_ambiente.id.desc())
        .all()
    )


def queryObtenerTemperaturaAmbienteUserAssignments(db: Session, current_user):
    return (
        db.query(asignaciones_iot.id)
        .filter(asignaciones_iot.id_usuario == current_user.id_usuario)
        .subquery()
    )


def queryObtenerTemperaturaAmbienteResultado(db: Session, user_assignments):
    return (
        db.query(temperatura_ambiente)
        .filter(temperatura_ambiente.id_asignacion.in_(user_assignments))
        .order_by(temperatura_ambiente.id.desc())
        .all()
    )


def queryObtenerTemperaturaSueloUserAssignments(db: Session, current_user):
    return (
        db.query(asignaciones_iot.id)
        .filter(asignaciones_iot.id_usuario == current_user.id_usuario)
        .subquery()
    )


def queryObtenerTemperaturaSueloResultado(db: Session, user_assignments):
    return (
        db.query(temperatura_suelo)
        .filter(temperatura_suelo.id_asignacion.in_(user_assignments))
        .order_by(temperatura_suelo.id.desc())
        .all()
    )


def queryObtenerControlAguaUserAssignments(db: Session, current_user):
    return (
        db.query(asignaciones_iot.id)
        .filter(asignaciones_iot.id_usuario == current_user.id_usuario)
        .subquery()
    )


def queryObtenerControlAguaResultado(db: Session, user_assignments):
    return (
        db.query(telemetria_tanque)
        .filter(telemetria_tanque.id_asignacion.in_(user_assignments))
        .order_by(telemetria_tanque.id.desc())
        .all()
    )


def queryCrearTelemetriaTanqueAsig(db: Session, id_asignacion):
    return (
        db.query(asignaciones_iot).filter(asignaciones_iot.id == id_asignacion).first()
    )


def queryCrearTelemetriaTanqueFuente(db: Session, asig):
    return db.query(fuentes_agua).filter(fuentes_agua.id == asig.id_fuente_agua).first()


def queryCrearTelemetriaTanqueOtroAsig(db: Session, asig):
    return (
        db.query(asignaciones_iot)
        .filter(
            asignaciones_iot.id_dispositivo == asig.id_dispositivo,
            asignaciones_iot.id_fuente_agua != None,
        )
        .first()
    )


def queryCrearTelemetriaTanqueFuente2(db: Session, otro_asig):
    return (
        db.query(fuentes_agua)
        .filter(fuentes_agua.id == otro_asig.id_fuente_agua)
        .first()
    )


def queryCrearTelemetriaTanqueConfig(db: Session, asig):
    return (
        db.query(configuracion_tanque)
        .filter(configuracion_tanque.id_asignacion == asig.id)
        .first()
    )


def queryCrearTelemetriaTanqueControlAsig(db: Session, asig):
    return (
        db.query(asignaciones_iot)
        .join(
            configuracion_tanque,
            configuracion_tanque.id_asignacion == asignaciones_iot.id,
        )
        .filter(asignaciones_iot.id_dispositivo == asig.id_dispositivo)
        .first()
    )


def queryCrearTelemetriaTanqueConfig2(db: Session, control_asig):
    return (
        db.query(configuracion_tanque)
        .filter(configuracion_tanque.id_asignacion == control_asig.id)
        .first()
    )


def queryCrearTelemetriaTanqueUltimoRegistro(db: Session, id_asignacion):
    return (
        db.query(telemetria_tanque)
        .filter(telemetria_tanque.id_asignacion == id_asignacion)
        .order_by(telemetria_tanque.id.desc())
        .first()
    )


def queryCrearTelemetriaTanqueUsrMod(db: Session, event_asig):
    return (
        db.query(cultivo_modelo)
        .filter(
            cultivo_modelo.id_usuario == event_asig.id_usuario,
            cultivo_modelo.id_cultivo == event_asig.id_cultivo,
            cultivo_modelo.activo == True,
        )
        .first()
    )


def queryCrearTelemetriaTanquePred(db: Session, hace_5_min, event_asig):
    return (
        db.query(predicciones_ml)
        .filter(
            predicciones_ml.id_usuario == event_asig.id_usuario,
            predicciones_ml.fecha >= hace_5_min,
            predicciones_ml.recomendacion == "regar",
        )
        .order_by(predicciones_ml.id_prediccion.desc())
        .first()
    )


def queryCrearTelemetriaTanqueRiegoActivo(db: Session, event_asig):
    return (
        db.query(riego)
        .filter(riego.id_asignacion == event_asig.id, riego.estado == False)
        .order_by(riego.id.desc())
        .first()
    )


def queryCrearTelemetriaTanqueEjecucionAbierta(db: Session, riego_activo):
    return (
        db.query(ejecucion_riego)
        .filter(
            ejecucion_riego.id_riego == riego_activo.id,
            ejecucion_riego.fecha_fin.is_(None),
        )
        .order_by(ejecucion_riego.id.desc())
        .first()
    )


def queryCrearTelemetriaTanqueRiegoActivo2(db: Session, event_asig):
    return (
        db.query(riego)
        .filter(riego.id_asignacion == event_asig.id, riego.estado == False)
        .order_by(riego.id.desc())
        .first()
    )


def queryCrearTelemetriaTanqueEjecucionAbierta2(db: Session, riego_activo):
    return (
        db.query(ejecucion_riego)
        .filter(
            ejecucion_riego.id_riego == riego_activo.id,
            ejecucion_riego.fecha_fin.is_(None),
        )
        .order_by(ejecucion_riego.id.desc())
        .first()
    )


def queryCrearTelemetriaTanqueRiegoActivo3(db: Session, event_asig):
    return (
        db.query(riego)
        .filter(riego.id_asignacion == event_asig.id, riego.estado == False)
        .order_by(riego.id.desc())
        .first()
    )


def queryCrearTelemetriaTanqueTelInicio(db: Session, id_asignacion, riego_activo):
    return (
        db.query(telemetria_tanque)
        .filter(
            telemetria_tanque.id_asignacion == id_asignacion,
            telemetria_tanque.bomba_encendida == True,
            telemetria_tanque.fecha >= riego_activo.fecha - dt.timedelta(seconds=5),
        )
        .order_by(telemetria_tanque.id.asc())
        .first()
    )
