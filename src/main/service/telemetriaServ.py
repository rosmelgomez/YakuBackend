from typing import List

from fastapi import HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.main.dtos.telemetriaDto import RiegoDatosModel, TelemetriaTanqueModel
from src.main.model.models import (
    telemetria_tanque,
)
from src.main.repositories import sessionRep as session_repository
from src.main.repositories import telemetriaRep as data_repository
from src.main.repositories import telemetriaRep as telemetria_repository


def verificar_acceso_asignaciones(
    db: Session, asignacion_ids: List[int], current_user
) -> None:
    for asig_id in asignacion_ids:
        # Buscar asignación activa
        asig = data_repository.queryVerificarAccesoAsignacionesAsig(db, asig_id)

        if asig:
            # 1. Validación de Propiedad (solo si no es administrador)
            if current_user.id_rol != 1 and asig.id_usuario != current_user.id_usuario:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"No tienes permiso para interactuar con la asignación '{asig_id}'",
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Asignación IoT con ID '{asig_id}' no encontrada o inactiva.",
            )


def guardar_datos_riegoServ(
    data: RiegoDatosModel, db: Session = None, current_user=None
):
    verificar_acceso_asignaciones(
        db,
        [
            data.humedad_suelo.id_asignacion,
            data.humedad_ambiente.id_asignacion,
            data.temperatura_ambiente.id_asignacion,
            data.temperatura_suelo.id_asignacion,
        ],
        current_user,
    )

    try:
        telemetria_repository.crear_datos_riego(db, data)
        return {"status": "ok", "message": "Datos de riego guardados correctamente"}
    except SQLAlchemyError as exc:
        session_repository.rollback(db)
        raise HTTPException(
            status_code=500, detail="Error al guardar los datos de riego"
        ) from exc


def obtener_humedad_sueloServ(
    id_usuario: int | None = None, db: Session = None, current_user=None
):
    if current_user.id_rol != 1:
        id_usuario = current_user.id_usuario

    if id_usuario is not None:
        user_assignments = data_repository.queryObtenerHumedadSueloUserAssignments(
            db, id_usuario
        )
        return data_repository.queryObtenerHumedadSueloResultado(db, user_assignments)

    return telemetria_repository.listar_humedad_suelo(db)


def obtener_humedad_ambienteServ(db: Session = None, current_user=None):
    if current_user.id_rol != 1:
        user_assignments = data_repository.queryObtenerHumedadAmbienteUserAssignments(
            db, current_user
        )
        return data_repository.queryObtenerHumedadAmbienteResultado(
            db, user_assignments
        )

    return telemetria_repository.listar_humedad_ambiente(db)


def obtener_temperatura_ambienteServ(db: Session = None, current_user=None):
    if current_user.id_rol != 1:
        user_assignments = (
            data_repository.queryObtenerTemperaturaAmbienteUserAssignments(
                db, current_user
            )
        )
        return data_repository.queryObtenerTemperaturaAmbienteResultado(
            db, user_assignments
        )

    return telemetria_repository.listar_temperatura_ambiente(db)


def obtener_temperatura_sueloServ(db: Session = None, current_user=None):
    if current_user.id_rol != 1:
        user_assignments = data_repository.queryObtenerTemperaturaSueloUserAssignments(
            db, current_user
        )
        return data_repository.queryObtenerTemperaturaSueloResultado(
            db, user_assignments
        )

    return telemetria_repository.listar_temperatura_suelo(db)


def guardar_control_aguaServ(
    data: TelemetriaTanqueModel, db: Session = None, current_user=None
):
    verificar_acceso_asignaciones(db, [data.id_asignacion], current_user)

    try:
        registro = crear_telemetria_tanque(
            db=db,
            id_asignacion=data.id_asignacion,
            distancia_cm=data.distancia_cm,
            estado_bomba=data.estado_bomba,
            valvula_abierta=data.valvula_abierta,
            motivo_cierre=data.motivo_cierre,
            duracion_objetivo_seg=data.duracion_objetivo_seg,
            tiempo_ejecutado_seg=data.tiempo_ejecutado_seg,
            litros_riego=data.litros_riego,
            litros_acumulados=data.litros_acumulados,
            caudal_l_min=data.caudal_l_min,
            pulsos_riego=data.pulsos_riego,
            pulsos_por_litro=data.pulsos_por_litro,
            metodo_medicion=data.metodo_medicion,
            fecha=data.fecha,
        )
        return {
            "status": "ok",
            "message": "Telemetría de tanque guardada correctamente",
            "id": registro.id,
            "nivel_agua_cm": registro.nivel_agua_cm,
            "porcentaje_nivel": registro.porcentaje_nivel,
        }
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail="Error interno del servidor"
        ) from exc
    except SQLAlchemyError as exc:
        session_repository.rollback(db)
        raise HTTPException(
            status_code=500, detail="Error al guardar la telemetría del tanque"
        ) from exc


def obtener_control_aguaServ(db: Session = None, current_user=None):
    if current_user.id_rol != 1:
        user_assignments = data_repository.queryObtenerControlAguaUserAssignments(
            db, current_user
        )
        return data_repository.queryObtenerControlAguaResultado(db, user_assignments)

    return telemetria_repository.listar_telemetria_tanque(db)


from datetime import datetime, timezone

from sqlalchemy.orm import Session

from src.main.dtos.telemetriaDto import RiegoDatosModel
from src.main.repositories.telemetriaRep import _to_utc_naive
from src.main.service.irrigationServ import (
    TRANSIENT_STOP_REASONS,
    complete_irrigation_session,
    get_max_relay_seconds,
    pause_irrigation_session,
)


def crear_telemetria_tanque(
    db: Session,
    id_asignacion: int,
    distancia_cm: float | None,
    estado_bomba: str,
    valvula_abierta: bool | None = None,
    motivo_cierre: str | None = None,
    duracion_objetivo_seg: int | None = None,
    tiempo_ejecutado_seg: int | None = None,
    fecha: datetime | None = None,
    litros_riego: float | None = None,
    litros_acumulados: float | None = None,
    caudal_l_min: float | None = None,
    pulsos_riego: int | None = None,
    pulsos_por_litro: float | None = None,
    metodo_medicion: str | None = None,
) -> telemetria_tanque:
    asig = data_repository.queryCrearTelemetriaTanqueAsig(db, id_asignacion)

    # 1. Obtener la fuente de agua asociada a la asignación del sensor o dispositivo
    fuente = None
    if asig and asig.id_fuente_agua is not None:
        fuente = data_repository.queryCrearTelemetriaTanqueFuente(db, asig)

    if fuente is None and asig:
        # Buscar en cualquier asignación del mismo dispositivo que tenga fuente de agua
        otro_asig = data_repository.queryCrearTelemetriaTanqueOtroAsig(db, asig)
        if otro_asig:
            fuente = data_repository.queryCrearTelemetriaTanqueFuente2(db, otro_asig)

    if fuente is None and asig and asig.cultivo is not None:
        fuente = asig.cultivo.fuente_agua
    from src.main.service.waterMeasurementServ import measurement_method

    metodo_registrado = measurement_method(asig, fuente)
    if metodo_medicion is not None and metodo_medicion != metodo_registrado:
        raise ValueError("El metodo de medicion no coincide con el actuador registrado.")
    conexion_directa = metodo_registrado == "flujometro"
    if conexion_directa and litros_riego is None:
        raise ValueError("El flujometro debe reportar litros_riego.")
    if not conexion_directa and distancia_cm is None:
        raise ValueError("El sensor de proximidad debe reportar distancia_cm.")

    altura_tanque = 30.0  # valor por defecto si no está configurado
    if fuente is not None and fuente.altura_tanque_cm is not None:
        altura_tanque = float(fuente.altura_tanque_cm)

    # Buscar configuración del tanque (actuador) del dispositivo asignado
    config = None
    control_asig = None
    if asig:
        config = data_repository.queryCrearTelemetriaTanqueConfig(db, asig)
        if config is not None:
            control_asig = asig
        else:
            control_asig = data_repository.queryCrearTelemetriaTanqueControlAsig(
                db, asig
            )
            if control_asig:
                config = data_repository.queryCrearTelemetriaTanqueConfig2(
                    db, control_asig
                )

    # Obtener estado de bomba anterior para detectar transiciones
    ultimo_registro = data_repository.queryCrearTelemetriaTanqueUltimoRegistro(
        db, id_asignacion
    )
    bomba_anterior = ultimo_registro.bomba_encendida if ultimo_registro else False

    valvula_reportada = False if valvula_abierta is None else valvula_abierta
    bomba_encendida = estado_bomba == "ON"
    if config is not None:
        config.bomba_encendida = estado_bomba == "ON"
        if valvula_abierta is not None:
            config.valvula_abierta = valvula_abierta
        session_repository.add(db, config)
        valvula_reportada = config.valvula_abierta
        bomba_encendida = config.bomba_encendida

    nivel_agua_cm = max(altura_tanque - (distancia_cm or 0.0), 0.0)
    porcentaje_nivel = max(0.0, min((nivel_agua_cm / altura_tanque) * 100.0, 100.0))

    # Determinar estado_nivel
    estado_nivel = "optimo"
    if porcentaje_nivel <= 0.0:
        estado_nivel = "sin_agua"
    elif porcentaje_nivel < 20.0:
        estado_nivel = "critico"
    elif porcentaje_nivel < 50.0:
        estado_nivel = "bajo"

    if conexion_directa:
        distancia_cm = None
        nivel_agua_cm = None
        porcentaje_nivel = None
        estado_nivel = "no_aplica"

    registro = telemetria_tanque(
        id_asignacion=id_asignacion,
        metodo_medicion=metodo_registrado,
        litros_riego=litros_riego if conexion_directa else None,
        litros_acumulados=litros_acumulados if conexion_directa else None,
        caudal_l_min=caudal_l_min if conexion_directa else None,
        pulsos_riego=pulsos_riego if conexion_directa else None,
        pulsos_por_litro=pulsos_por_litro if conexion_directa else None,
        distancia_cm=distancia_cm,
        nivel_agua_cm=nivel_agua_cm,
        porcentaje_nivel=porcentaje_nivel,
        estado_nivel=estado_nivel,
        valvula_abierta=valvula_reportada,
        bomba_encendida=bomba_encendida,
        fuente_control="automatico",
        fecha=_to_utc_naive(fecha),
    )
    session_repository.add(db, registro)
    session_repository.flush(db)

    # Lógica de registro en la tabla 'riego'
    event_asig = control_asig or asig
    if event_asig:
        from src.main.model.models import riego

        # 1. Transición de OFF a ON (Inicio de Riego)
        if bomba_encendida and not bomba_anterior:
            tipo = "manual"
            id_modelo = None
            id_pred = None

            # A. Verificar si el modo Predictivo (ML) está activo y hay predicción reciente
            usr_mod = data_repository.queryCrearTelemetriaTanqueUsrMod(db, event_asig)

            if usr_mod:
                import datetime as dt

                hace_5_min = datetime.now(timezone.utc).replace(
                    tzinfo=None
                ) - dt.timedelta(minutes=5)
                pred = data_repository.queryCrearTelemetriaTanquePred(
                    db, hace_5_min, event_asig
                )

                if pred:
                    tipo = "automatico_ml"
                    id_modelo = pred.id_modelo
                    id_pred = pred.id_prediccion

            # B. Si no es ML, verificar si coincide con un Riego Programado activo
            if tipo == "manual":
                now = datetime.now()
                current_weekday = now.weekday()
                day_attrs = [
                    "lunes",
                    "martes",
                    "miercoles",
                    "jueves",
                    "viernes",
                    "sabado",
                    "domingo",
                ]
                day_attr = day_attrs[current_weekday]

                # Buscar programaciones activas hoy para este dispositivo
                programaciones_hoy = (
                    data_repository.queryCrearTelemetriaTanqueProgramacionesHoy(
                        db, event_asig, day_attr
                    )
                )

                for pr in programaciones_hoy:
                    h_start = pr.hora_inicio
                    diff_mins = abs(
                        (now.hour * 60 + now.minute)
                        - (h_start.hour * 60 + h_start.minute)
                    )
                    if diff_mins <= 2:
                        tipo = "programado"
                        break

            riego_activo = data_repository.queryCrearTelemetriaTanqueRiegoActivo(
                db, event_asig
            )
            if riego_activo is not None and not (
                riego_activo.motivo_cierre
                and riego_activo.motivo_cierre.startswith("pausado_")
            ):
                ejecucion_abierta = (
                    data_repository.queryCrearTelemetriaTanqueEjecucionAbierta(
                        db, riego_activo
                    )
                )
                if ejecucion_abierta:
                    ejecucion_abierta.metodo_medicion = metodo_registrado
                    ejecucion_abierta.distancia_inicial_cm = distancia_cm
                    if conexion_directa and litros_riego is not None:
                        ejecucion_abierta.cantidad_agua_litros = litros_riego
                    session_repository.add(db, ejecucion_abierta)

            if riego_activo is None:
                planned_seconds = get_max_relay_seconds(
                    db,
                    event_asig.id_usuario,
                    event_asig.id_cultivo,
                )
                if duracion_objetivo_seg is not None and duracion_objetivo_seg > 0:
                    planned_seconds = int(duracion_objetivo_seg)
                now_start = datetime.now(timezone.utc).replace(tzinfo=None)
                nuevo_riego = riego(
                    id_asignacion=event_asig.id,
                    id_usuario=event_asig.id_usuario,
                    id_modelo=id_modelo,
                    id_prediccion=id_pred,
                    tipo_riego=tipo,
                    duracion_segundos=planned_seconds,
                    segundos_acumulados=0,
                    cantidad_agua_litros=0.0,
                    estado=False,  # En progreso (activo)
                    fecha_inicio=now_start,
                    fecha_fin=None,
                    fecha=now_start,
                )
                session_repository.add(db, nuevo_riego)
                session_repository.flush(db)
                from src.main.service.irrigationServ import start_new_execution

                start_new_execution(db, nuevo_riego, now_start)
            elif riego_activo.motivo_cierre and riego_activo.motivo_cierre.startswith(
                "pausado_"
            ):
                riego_activo.motivo_cierre = None
                riego_activo.fecha = datetime.now(timezone.utc).replace(tzinfo=None)
                session_repository.add(db, riego_activo)
                session_repository.flush(db)
                from src.main.service.irrigationServ import start_new_execution

                start_new_execution(db, riego_activo, riego_activo.fecha)

        elif bomba_encendida:
            riego_activo = data_repository.queryCrearTelemetriaTanqueRiegoActivo2(
                db, event_asig
            )
            if riego_activo and not (
                riego_activo.motivo_cierre
                and riego_activo.motivo_cierre.startswith("pausado_")
            ):
                ejecucion_abierta = (
                    data_repository.queryCrearTelemetriaTanqueEjecucionAbierta2(
                        db, riego_activo
                    )
                )
                if ejecucion_abierta:
                    ejecucion_abierta.metodo_medicion = metodo_registrado
                    if ejecucion_abierta.distancia_inicial_cm is None:
                        ejecucion_abierta.distancia_inicial_cm = distancia_cm
                    if conexion_directa and litros_riego is not None:
                        ejecucion_abierta.cantidad_agua_litros = litros_riego
                    session_repository.add(db, ejecucion_abierta)

                now_sync = datetime.now(timezone.utc).replace(tzinfo=None)
                if duracion_objetivo_seg is not None and duracion_objetivo_seg > 0:
                    riego_activo.duracion_segundos = max(
                        int(riego_activo.duracion_segundos or 0),
                        int(duracion_objetivo_seg),
                    )
                if tiempo_ejecutado_seg is not None and tiempo_ejecutado_seg >= 0:
                    planned = int(
                        riego_activo.duracion_segundos or tiempo_ejecutado_seg
                    )
                    riego_activo.segundos_acumulados = (
                        min(int(tiempo_ejecutado_seg), planned)
                        if planned > 0
                        else int(tiempo_ejecutado_seg)
                    )
                    riego_activo.fecha = now_sync
                session_repository.add(db, riego_activo)

        # 2. Transición de ON a OFF (Fin de Riego)
        elif not bomba_encendida and (
            bomba_anterior or motivo_cierre in TRANSIENT_STOP_REASONS
        ):
            riego_activo = data_repository.queryCrearTelemetriaTanqueRiegoActivo3(
                db, event_asig
            )

            from src.main.service.irrigationServ import is_paused_session

            if riego_activo and not is_paused_session(riego_activo):
                now_close = datetime.now(timezone.utc).replace(tzinfo=None)
                if duracion_objetivo_seg is not None and duracion_objetivo_seg > 0:
                    riego_activo.duracion_segundos = max(
                        int(riego_activo.duracion_segundos or 0),
                        int(duracion_objetivo_seg),
                    )
                if tiempo_ejecutado_seg is not None and tiempo_ejecutado_seg >= 0:
                    planned = int(
                        riego_activo.duracion_segundos or tiempo_ejecutado_seg
                    )
                    riego_activo.segundos_acumulados = (
                        min(int(tiempo_ejecutado_seg), planned)
                        if planned > 0
                        else int(tiempo_ejecutado_seg)
                    )
                    riego_activo.fecha = now_close

                # Proximidad usa el nivel inicial de la ejecucion completa.
                # El flujometro entrega directamente el volumen medido del tramo.
                litros = litros_riego if conexion_directa else None

                reason = motivo_cierre or "sistema"
                if reason in TRANSIENT_STOP_REASONS:
                    pause_irrigation_session(
                        db,
                        riego_activo,
                        reason,
                        now_close,
                        litros,
                        executed_seconds_override=tiempo_ejecutado_seg,
                    )
                else:
                    complete_irrigation_session(
                        db, riego_activo, reason, now_close, litros
                    )

    session_repository.commit(db)
    session_repository.refresh(db, registro)
    return registro
