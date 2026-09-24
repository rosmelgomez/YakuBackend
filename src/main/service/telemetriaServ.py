import logging
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

logger = logging.getLogger(__name__)


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
            id_riego=data.id_riego,
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


from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from src.main.dtos.telemetriaDto import RiegoDatosModel
from src.main.repositories import irrigationRep as irrigation_repository
from src.main.repositories.telemetriaRep import _to_utc_naive
from src.main.service.irrigationServ import (
    TRANSIENT_STOP_REASONS,
    complete_irrigation_session,
    get_max_relay_seconds,
    get_ml_cooldown_minutes,
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
    id_riego: int | None = None,
) -> telemetria_tanque:
    asig = data_repository.queryCrearTelemetriaTanqueAsig(db, id_asignacion)
    if not asig:
        raise ValueError(f"No existe la asignación con id {id_asignacion} en el sistema.")

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

    try:
        metodo_registrado = measurement_method(asig, fuente)
    except ValueError:
        if metodo_medicion in ("proximidad", "flujometro"):
            metodo_registrado = metodo_medicion
        elif distancia_cm is not None:
            metodo_registrado = "proximidad"
        elif (
            litros_riego is not None
            or caudal_l_min is not None
            or pulsos_riego is not None
        ):
            metodo_registrado = "flujometro"
        else:
            raise
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

    valvula_reportada = False if valvula_abierta is None else valvula_abierta
    bomba_encendida = estado_bomba == "ON"
    if conexion_directa:
        valvula_reportada = bomba_encendida
    if config is not None:
        config.bomba_encendida = estado_bomba == "ON"
        if conexion_directa:
            config.valvula_abierta = config.bomba_encendida
        elif valvula_abierta is not None:
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
    #
    # NOTA: antes esta funcion decidia si un mensaje era "inicio", "continuacion"
    # o "cierre" comparando bomba_encendida contra el 'bomba_anterior' leido del
    # ULTIMO registro de telemetria_tanque. Ese heuristico es fragil frente a
    # mensajes fuera de orden o perdidos (tipico en WiFi/MQTT de un ESP32) y
    # podia terminar cerrando una sesion sin haber abierto nunca su ejecucion,
    # perdiendo el litros_riego reportado (quedaba 0.0 en 'riego' aunque el
    # dispositivo si hubiera medido consumo real). Ahora se consulta
    # directamente si existe una sesion 'riego' activa/pausada para esta
    # asignacion (fuente de verdad) y se actua segun ese estado real, sin
    # depender de la transicion inferida del mensaje anterior.
    event_asig = control_asig or asig
    if event_asig:
        from src.main.model.models import riego
        from src.main.service.irrigationServ import (
            is_paused_session,
            start_new_execution,
        )

        riego_activo = data_repository.queryCrearTelemetriaTanqueRiegoActivo3(
            db, event_asig
        )

        # El firmware de flujo (>= 1.0.12) devuelve el id de la sesion que abrio
        # su ciclo. Si no es la sesion en curso, el reporte pertenece a un ciclo
        # que el servidor ya cerro (tipico al reconectar tras perder la red: el
        # equipo siguio regando con su cronometro y entrega ahora sus litros y
        # segundos reales). Se aplica a ESA sesion y no se toca la actual: ni
        # se cierra con litros ajenos ni se crea una sesion retroactiva.
        reporte_de_otro_ciclo = bool(
            conexion_directa
            and id_riego
            and (riego_activo is None or riego_activo.id != id_riego)
        )
        if reporte_de_otro_ciclo:
            from src.main.repositories import irrigationRep as irrigation_rep
            from src.main.service.irrigationServ import reconcile_closed_session

            sesion_reportada = irrigation_rep.queryRiegoReportadoPorDispositivo(
                db, id_riego, event_asig.id_usuario
            )
            if sesion_reportada is not None and sesion_reportada.estado:
                reconcile_closed_session(
                    db, sesion_reportada, litros_riego, tiempo_ejecutado_seg
                )
                logger.info(
                    "[TANQUE] Reporte tardio del ciclo %s aplicado (litros=%s, seg=%s).",
                    id_riego,
                    litros_riego,
                    tiempo_ejecutado_seg,
                )
            session_repository.commit(db)
            session_repository.refresh(db, registro)
            return registro

        bloqueado_por_cooldown = False
        if riego_activo is None:
            # Estos bloques solo REGISTRAN en 'riego' lo que la telemetria ya
            # reporta (bomba encendida o un cierre sin sesion previa), no
            # deciden si regar. Pero si se les deja crear una sesion nueva sin
            # mas, cualquier cosa que encienda el dispositivo (un toggle
            # repetido, un reintento, etc.) queda registrada como
            # "automatico_ml" sin que haya pasado el cooldown configurado --
            # exactamente el patron que generaba decenas de riegos seguidos
            # ignorando el cooldown. El riego automatico debe ser
            # exclusivamente decision de ML (ver
            # schedulerServ.check_ml_cooldown_and_irrigate), asi que aqui se
            # verifica el mismo cooldown antes de registrar un ciclo nuevo
            # (real o retroactivo).
            from src.main.repositories import mqttRep as mqtt_rep

            cooldown_minutos = get_ml_cooldown_minutes(
                db, event_asig.id_usuario, event_asig.id_cultivo
            )
            tiempo_cooldown = datetime.now(timezone.utc).replace(
                tzinfo=None
            ) - timedelta(minutes=cooldown_minutos)
            riego_reciente = mqtt_rep.queryProcesarMensajeRiegoReciente(
                db, event_asig.id_cultivo, event_asig.id_usuario, tiempo_cooldown
            )
            if riego_reciente:
                bloqueado_por_cooldown = True
                logger.warning(
                    "[TANQUE] Asignacion %s reporta actividad de riego sin haber "
                    "cumplido el cooldown ML (ultimo riego automatico_ml "
                    "finalizado %s, cooldown %s min); no se registra como "
                    "nuevo ciclo automatico.",
                    event_asig.id,
                    riego_reciente.fecha_fin,
                    cooldown_minutos,
                )

        if bloqueado_por_cooldown:
            pass
        elif bomba_encendida:
            if riego_activo is None:
                # Inicio real de un nuevo ciclo de riego.
                tipo = "automatico_ml"
                id_modelo = None
                id_pred = None

                usr_mod = data_repository.queryCrearTelemetriaTanqueUsrMod(
                    db, event_asig
                )
                if usr_mod:
                    id_modelo = usr_mod.id_modelo
                    import datetime as dt

                    hace_5_min = datetime.now(timezone.utc).replace(
                        tzinfo=None
                    ) - dt.timedelta(minutes=5)
                    pred = data_repository.queryCrearTelemetriaTanquePred(
                        db, hace_5_min, event_asig
                    )
                    if pred:
                        id_pred = pred.id_prediccion

                # No se usa duracion_objetivo_seg aqui: el firmware le suma
                # +60s de margen de seguridad a lo pedido antes de reportarlo
                # (ver esp32-sensor-flujo.ino, variable duracionMs -- "la
                # aplicacion controla el cronometro y envia OFF al
                # terminar"), asi que ese valor SIEMPRE viene inflado 1
                # minuto respecto a lo configurado. get_max_relay_seconds ya
                # es la fuente de verdad de cuanto se planeo regar.
                planned_seconds = get_max_relay_seconds(
                    db, event_asig.id_usuario, event_asig.id_cultivo
                )
                now_start = datetime.now(timezone.utc).replace(tzinfo=None)
                riego_activo = riego(
                    id_asignacion=event_asig.id,
                    id_usuario=event_asig.id_usuario,
                    id_modelo=id_modelo,
                    id_prediccion=id_pred,
                    tipo_riego=tipo,
                    duracion_segundos=planned_seconds,
                    segundos_acumulados=int(tiempo_ejecutado_seg or 0),
                    cantidad_agua_litros=0.0,
                    estado=False,  # En progreso (activo)
                    fecha_inicio=now_start,
                    fecha_fin=None,
                    fecha=now_start,
                )
                session_repository.add(db, riego_activo)
                session_repository.flush(db)
                start_new_execution(db, riego_activo, now_start)

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

            elif is_paused_session(riego_activo):
                # Reanudacion de una sesion previamente pausada.
                riego_activo.motivo_cierre = None
                riego_activo.fecha = datetime.now(timezone.utc).replace(tzinfo=None)
                session_repository.add(db, riego_activo)
                session_repository.flush(db)
                start_new_execution(db, riego_activo, riego_activo.fecha)

            else:
                # Continuacion normal de un ciclo ya abierto: sincronizar
                # progreso y el litros_riego mas reciente reportado.
                ejecucion_abierta = (
                    data_repository.queryCrearTelemetriaTanqueEjecucionAbierta2(
                        db, riego_activo
                    )
                )
                if ejecucion_abierta is None:
                    # Hay sesion activa pero sin ejecucion abierta: una
                    # anterior se cerro sin que se abriera una nueva. Abrir
                    # una ahora para no perder este reporte de litros.
                    logger.warning(
                        "[TANQUE] Sesion 'riego' %s activa sin ejecucion abierta "
                        "en 'ejecuciones_riego'; se abre una nueva (litros_riego=%s).",
                        riego_activo.id,
                        litros_riego,
                    )
                    start_new_execution(
                        db, riego_activo, datetime.now(timezone.utc).replace(tzinfo=None)
                    )
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
                # duracion_objetivo_seg NO se usa para actualizar
                # duracion_segundos: ver nota en la rama de "inicio real" mas
                # arriba -- el firmware siempre le suma +60s de margen antes
                # de reportarlo, y usarlo aqui inflaba el cronometro que ve
                # el usuario en 1 minuto (ej. 5 min configurados -> 6 min
                # mostrados). La duracion planeada se fija una sola vez al
                # crear la sesion y no debe cambiar durante el ciclo.
                if tiempo_ejecutado_seg is not None and tiempo_ejecutado_seg >= 0:
                    # tiempo_ejecutado_seg es lo corrido en el tramo ACTUAL
                    # (el firmware lo reinicia en cada ON). Hay que sumarle lo
                    # de los tramos ya cerrados (pausas previas); si no, al
                    # reanudar un riego el cronometro volvia a 0 y el backend
                    # creia que faltaba mas tiempo del real.
                    previos = int(
                        irrigation_repository.queryCompleteIrrigationSessionEjecucionRiego(
                            db, riego_activo
                        )
                        or 0
                    )
                    total = previos + int(tiempo_ejecutado_seg)
                    planned = int(riego_activo.duracion_segundos or total)
                    riego_activo.segundos_acumulados = (
                        min(total, planned) if planned > 0 else total
                    )
                    riego_activo.fecha = now_sync
                session_repository.add(db, riego_activo)

        elif not (conexion_directa and motivo_cierre == "sin_flujo"):
            # bomba_encendida == False: cierre de ciclo.
            if riego_activo and not is_paused_session(riego_activo):
                now_close = datetime.now(timezone.utc).replace(tzinfo=None)
                # Ultimo progreso sincronizado desde el equipo, antes de que el
                # tiempo_ejecutado_seg de este mensaje lo reemplace (tras un
                # reinicio viene en 0).
                segundos_sincronizados = int(riego_activo.segundos_acumulados or 0)
                # Igual que en las ramas anteriores: no se usa
                # duracion_objetivo_seg para tocar duracion_segundos (viene
                # inflado +60s por el margen de seguridad del firmware).
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
                # El firmware de flujo SIEMPRE manda motivo en un cierre real
                # (tiempo_maximo, usuario, desactivacion...). "sistema" = el
                # dispositivo reporto la valvula cerrada sin motivo: es su
                # estado de reposo, no el aviso de un ciclo terminado. Dos
                # casos segun cuanto lleva la sesion:
                #  - Recien creada y sin agua: la orden ON nunca llego a
                #    abrir el rele. No hubo riego -> se descarta la sesion
                #    (solo se registran riegos realmente ejecutados).
                #  - Con tiempo corrido: el ESP32 se reinicio a mitad de un
                #    riego real (corte de luz) y perdio su estado. Se pausa
                #    como desconexion para retomarla desde donde quedo
                #    (deviceHealthServ la reanuda al estar en linea).
                if conexion_directa and reason == "sistema":
                    inicio_ref = riego_activo.fecha_inicio or riego_activo.fecha or now_close
                    sesion_recien_creada = (now_close - inicio_ref).total_seconds() < 60
                    if sesion_recien_creada and not litros:
                        logger.warning(
                            "[TANQUE] Riego %s descartado: el actuador reporto la "
                            "valvula cerrada sin haberla abierto (orden ON perdida).",
                            riego_activo.id,
                        )
                        session_repository.delete(db, riego_activo)
                    else:
                        # Tras reiniciarse, el ESP32 reporta tiempo/litros en 0
                        # (contadores de RAM reseteados): pasarlos pisaria lo
                        # real. Litros: se conservan los ultimos reportados en
                        # la ejecucion. Segundos: los ultimos que reporto el
                        # equipo en este tramo, NO el reloj de pared, que
                        # seguiria contando todo el tiempo sin conexion aunque
                        # la valvula (normalmente cerrada) no estuvo abierta.
                        previos = int(
                            irrigation_repository.queryCompleteIrrigationSessionEjecucionRiego(
                                db, riego_activo
                            )
                            or 0
                        )
                        segundos_tramo = max(segundos_sincronizados - previos, 0)
                        pause_irrigation_session(
                            db,
                            riego_activo,
                            "desconexion_riego",
                            now_close,
                            executed_seconds_override=segundos_tramo,
                        )
                elif reason in TRANSIENT_STOP_REASONS:
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
            elif conexion_directa and litros_riego:
                # Firmware que solo publica el mensaje de cierre, sin aviso de
                # inicio de ciclo (p.ej. esp32-sensor-flujo v1.0.9 o anterior:
                # no marca 'pendiente=true' mientras riega, solo al cerrar).
                # Nunca hubo forma de abrir una sesion 'riego' de antemano.
                # En vez de descartar el litraje ya medido por el sensor, se
                # registra aqui una sesion retroactiva ya completada con ese
                # consumo, para que no desaparezca del dashboard.
                logger.warning(
                    "[TANQUE] Mensaje de cierre (OFF) sin sesion 'riego' previa "
                    "para asignacion %s; se registra una sesion retroactiva con "
                    "litros_riego=%s (firmware sin aviso de inicio de ciclo).",
                    event_asig.id,
                    litros_riego,
                )
                from src.main.model.models import ejecucion_riego

                now_close = datetime.now(timezone.utc).replace(tzinfo=None)
                # tiempo_ejecutado_seg (elapsed real) es preferido; solo si
                # falta se recurre a duracion_objetivo_seg como estimacion, y
                # a ese hay que restarle los +60s de margen de seguridad que
                # el firmware le suma antes de reportarlo (ver notas arriba).
                duracion_objetivo_sin_margen = (
                    max(0, int(duracion_objetivo_seg) - 60)
                    if duracion_objetivo_seg
                    else 0
                )
                duracion = int(tiempo_ejecutado_seg or duracion_objetivo_sin_margen or 0)
                duracion = max(duracion, 1)
                fecha_inicio_estimada = now_close - timedelta(seconds=duracion)
                reason = motivo_cierre or "sistema"

                riego_retro = riego(
                    id_asignacion=event_asig.id,
                    id_usuario=event_asig.id_usuario,
                    tipo_riego="automatico_ml",
                    duracion_segundos=duracion,
                    segundos_acumulados=duracion,
                    cantidad_agua_litros=litros_riego,
                    motivo_cierre=reason,
                    estado=True,
                    fecha_inicio=fecha_inicio_estimada,
                    fecha_fin=now_close,
                    fecha=now_close,
                )
                session_repository.add(db, riego_retro)
                session_repository.flush(db)

                ejecucion_retro = ejecucion_riego(
                    id_riego=riego_retro.id,
                    fecha_inicio=fecha_inicio_estimada,
                    fecha_fin=now_close,
                    metodo_medicion=metodo_registrado,
                    duracion_segundos=duracion,
                    cantidad_agua_litros=litros_riego,
                    motivo_cierre=reason,
                )
                session_repository.add(db, ejecucion_retro)

    session_repository.commit(db)
    session_repository.refresh(db, registro)
    return registro
