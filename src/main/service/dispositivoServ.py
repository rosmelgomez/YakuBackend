import json
from src.main.core.waterSource import normalize_source_type
import logging

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.main.dtos.dispositivoDto import (
    ActualizarAsignacionComponentePayload,
    AsignarComponentePayload,
    ComponenteCreate,
    DispositivoCreate,
)
from src.main.model.models import (
    asignaciones_iot,
    componentes,
    configuracion_tanque,
    dispositivos,
)
from src.main.repositories import dispositivoRep as data_repository
from src.main.repositories import sessionRep as session_repository
from src.main.service.deviceHealthServ import (
    _is_actuator_device,
    _is_sensor_device,
    sync_device_health,
    utc_now_naive,
)
from src.main.tasks.mqttSubscriberTask import publish_mqtt_message

logger = logging.getLogger(__name__)


def listar_dispositivosServ(
    id_usuario: int | None = None, db: Session = None, current_user=None
):
    """
    Lista los dispositivos del sistema.
    """
    if current_user.id_rol != 1:
        id_usuario = current_user.id_usuario

    if id_usuario is not None:
        return data_repository.queryListarDispositivosResultado(db, id_usuario)

    return data_repository.queryListarDispositivosResultado2(db)


def listar_mis_dispositivosServ(db: Session = None, current_user=None):
    """
    Retorna la lista de dispositivos asignados únicamente al usuario autenticado actual.
    """
    return data_repository.queryListarMisDispositivosResultado(db, current_user)


def listar_tipos_dispositivoServ(db: Session = None, current_user=None):
    """Lista todos los tipos de dispositivos disponibles."""
    return data_repository.queryListarTiposDispositivoResultado(db)


def listar_tipos_metricaServ(db: Session = None, current_user=None):
    """Lista todos los tipos de métricas disponibles."""
    return data_repository.queryListarTiposMetricaResultado(db)


def listar_tipos_componenteServ(db: Session = None, current_user=None):
    """Lista todos los tipos de componentes disponibles en el catálogo."""
    return data_repository.queryListarTiposComponenteResultado(db)


def listar_componentesServ(db: Session = None, current_user=None):
    """Lista todos los componentes físicos registrados en el inventario."""
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador para realizar esta acción.",
        )
    return data_repository.queryListarComponentesResultado(db)


def obtener_siguiente_client_idServ(db: Session = None, current_user=None):
    """
    Calcula el siguiente Client ID MQTT consultando en la base de datos.
    Solo administradores.
    """
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador para realizar esta acción.",
        )

    # Obtener todos los client_id_mqtt que siguen el patron ESP32_Yaku_
    items = data_repository.queryObtenerSiguienteClientIdItems(db)

    max_num = 0
    for (client_id,) in items:
        if client_id:
            try:
                parts = client_id.split("_")
                num_str = parts[-1]
                num = int(num_str)
                if num > max_num:
                    max_num = num
            except (ValueError, IndexError):
                continue

    next_num = max_num + 1
    next_client_id = f"ESP32_Yaku_{next_num:03d}"
    return {"siguiente_client_id": next_client_id}


def activar_dispositivoServ(dispositivo_id: int, db: Session = None, current_user=None):
    dispositivo = data_repository.queryActivarDispositivoDispositivo(db, dispositivo_id)
    if dispositivo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Dispositivo no encontrado"
        )

    # Validación de Seguridad
    if current_user.id_rol != 1 and dispositivo.id_usuario != current_user.id_usuario:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para controlar este dispositivo",
        )

    topic = dispositivo.topic_sub or "yaku/valvula/comando"

    try:
        # Nunca retener ordenes en el topic de comando: el broker las
        # reentregaria en cada reconexion del equipo (un ON retenido abre la
        # valvula tras un reinicio; un OFF retenido corta el riego en curso
        # al reconectar). El payload vacio retenido borra una orden retenida
        # que haya quedado de versiones anteriores.
        publish_mqtt_message(topic, "", qos=1, retain=True)
        publish_mqtt_message(topic, "ON", qos=1, retain=False)
        return {
            "status": "ok",
            "accion": "activar",
            "topic": topic,
            "dispositivo_id": dispositivo_id,
        }
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor",
        ) from exc


def desactivar_dispositivoServ(
    dispositivo_id: int, db: Session = None, current_user=None
):
    dispositivo = data_repository.queryDesactivarDispositivoDispositivo(
        db, dispositivo_id
    )
    if dispositivo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Dispositivo no encontrado"
        )

    # Validación de Seguridad
    if current_user.id_rol != 1 and dispositivo.id_usuario != current_user.id_usuario:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para controlar este dispositivo",
        )

    topic = dispositivo.topic_sub or "yaku/valvula/comando"

    try:
        # Nunca retener ordenes en el topic de comando: el broker las
        # reentregaria en cada reconexion del equipo (un ON retenido abre la
        # valvula tras un reinicio; un OFF retenido corta el riego en curso
        # al reconectar). El payload vacio retenido borra una orden retenida
        # que haya quedado de versiones anteriores.
        publish_mqtt_message(topic, "", qos=1, retain=True)
        publish_mqtt_message(topic, "OFF", qos=1, retain=False)
        return {
            "status": "ok",
            "accion": "desactivar",
            "topic": topic,
            "dispositivo_id": dispositivo_id,
        }
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor",
        ) from exc


def actualizar_funcionamiento_usuario(
    dispositivo_id: int, activo: bool, db: Session, current_user
):
    sync_device_health(db)

    dispositivo = data_repository.queryActualizarFuncionamientoUsuarioDispositivo(
        db, dispositivo_id
    )
    if dispositivo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Dispositivo no encontrado"
        )

    # 1. Obtener todas las asignaciones para este dispositivo y el usuario
    asig_query = data_repository.queryActualizarFuncionamientoUsuarioAsigQuery(
        db, dispositivo_id
    )
    if current_user.id_rol != 1:
        asig_query = data_repository.queryActualizarFuncionamientoUsuarioAsigQuery2(
            asig_query, current_user
        )
    asigs = data_repository.queryActualizarFuncionamientoUsuarioAsigs(asig_query)

    if not asigs and current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para modificar este dispositivo o no está asignado a tu usuario.",
        )

    # 1.1 Si se intenta activar un actuador (tipo 2), validar que el sensor (tipo 1) del cultivo esté activo
    if activo and _is_actuator_device(dispositivo):
        cultivos_ids = [a.id_cultivo for a in asigs if a.id_cultivo is not None]
        if cultivos_ids:
            sensor_activo = (
                data_repository.queryActualizarFuncionamientoUsuarioSensorActivo(
                    db, cultivos_ids
                )
            )
            if not sensor_activo:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No se puede activar el dispositivo actuador: Primero debe activar el dispositivo de sensores.",
                )

    # 1.2 Si se intenta apagar un actuador (tipo 2), validar que no haya un riego activo en curso
    if not activo and _is_actuator_device(dispositivo):
        from src.main.repositories import controlRep as control_repo
        for asig in asigs:
            sesion_activa = control_repo.queryObtenerDatosControlSesionActiva(db, asig.id)
            config_t = data_repository.queryConfiguracionTanquePorAsignacion(db, asig.id)
            if sesion_activa or (config_t and config_t.bomba_encendida):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No se puede apagar el dispositivo actuador mientras hay un riego en curso. Detenga el riego primero.",
                )

    # 2. Actualizar el estado de estas asignaciones
    for asig in asigs:
        asig.activo = activo
        session_repository.add(db, asig)
    if activo:
        dispositivo.ultimo_ping = utc_now_naive()
        session_repository.add(db, dispositivo)

    # 2.1 Si se desactiva un actuador, detener cualquier riego activo o pausado y apagar bomba/válvula
    if not activo and _is_actuator_device(dispositivo):
        from src.main.service.irrigationServ import stop_irrigation
        for asig in asigs:
            try:
                stop_irrigation(db, asig, "dispositivo_desactivado", publish=True)
            except Exception as e:
                logger.warning(
                    f"Error deteniendo riego para asignacion {asig.id} al desactivar dispositivo: {e}"
                )
            config_t = data_repository.queryConfiguracionTanquePorAsignacion(db, asig.id)
            if config_t:
                config_t.bomba_encendida = False
                config_t.valvula_abierta = False
                config_t.actualizado_en = utc_now_naive()
                session_repository.add(db, config_t)

    # 2.2 Si se desactiva un dispositivo de CAPTURA (sensor), apagar tambien
    # los actuadores del mismo cultivo: sin sensor no hay datos para que la
    # IA decida regar (ver 1.1: un actuador no puede ACTIVARSE sin sensor
    # activo, asi que tampoco tiene sentido dejarlo activo sin uno). Pero si
    # el actuador tiene un riego genuinamente en curso, no se fuerza su
    # apagado a mitad de ciclo -- se deja terminar solo; una vez termine
    # quedara sin sensor, por lo que no podra reactivarse hasta que el
    # sensor vuelva a encenderse.
    if not activo and _is_sensor_device(dispositivo):
        from src.main.repositories import controlRep as control_repo
        from src.main.repositories import deviceHealthRep as device_health_repo

        for asig in asigs:
            if asig.id_cultivo is None:
                continue
            actuator_assignments = (
                device_health_repo.queryDeactivateCropActuatorsActuatorAssignments(
                    db, asig.id_usuario, asig.id_cultivo
                )
            )
            for act_asig in actuator_assignments:
                act_device = act_asig.dispositivo
                if not act_device or not _is_actuator_device(act_device):
                    continue
                sesion_activa = control_repo.queryObtenerDatosControlSesionActiva(
                    db, act_asig.id
                )
                config_t = data_repository.queryConfiguracionTanquePorAsignacion(
                    db, act_asig.id
                )
                if sesion_activa or (config_t and config_t.bomba_encendida):
                    logger.info(
                        f"[CAPTURA] No se apaga el actuador de la asignación {act_asig.id}: "
                        "hay un riego en curso."
                    )
                    continue
                act_asig.activo = False
                session_repository.add(db, act_asig)
                try:
                    act_topic = f"yaku/dispositivo/{act_device.client_id_mqtt}/config"
                    publish_mqtt_message(
                        act_topic,
                        json.dumps({"funcionamiento_activo": False}),
                        qos=1,
                        retain=True,
                    )
                except Exception as mq_err:
                    logger.info(
                        f"[MQTT WARNING] No se pudo notificar apagado en cascada a "
                        f"{act_device.client_id_mqtt}: {mq_err}"
                    )
                logger.info(
                    f"[CAPTURA] Actuador (asignación {act_asig.id}) apagado en cascada "
                    f"por desactivación del sensor {dispositivo.nombre}."
                )

    # 3. Publicar el nuevo estado vía MQTT al dispositivo para sincronización dinámica
    topic = f"yaku/dispositivo/{dispositivo.client_id_mqtt}/config"
    payload = json.dumps({"funcionamiento_activo": activo})
    try:
        publish_mqtt_message(topic, payload, qos=1, retain=True)
    except Exception as mq_err:
        logger.info(
            f"[MQTT WARNING] No se pudo notificar al dispositivo {dispositivo.client_id_mqtt} via MQTT: {mq_err}"
        )

    session_repository.commit(db)

    # 4. Si se activa un actuador, evaluar el ML de inmediato con la MISMA
    # logica centralizada (cooldown, horario, lecturas validas, bloqueo contra
    # evaluaciones simultaneas). Antes aqui habia una copia propia que no
    # respetaba el horario y rellenaba sensores faltantes con 0.0.
    if activo and _is_actuator_device(dispositivo):
        try:
            from src.main.service.schedulerServ import check_ml_cooldown_and_irrigate

            check_ml_cooldown_and_irrigate(db)
        except Exception as e:
            logger.info(f"[ML WARNING] Error al ejecutar predicción en activación: {e}")

    estado_str = "activado" if activo else "desactivado"
    return {
        "status": "ok",
        "message": f"Captura de datos y control automático {estado_str} para el dispositivo y sus vinculados",
        "dispositivo_id": dispositivo_id,
        "funcionamiento_activo": activo,
    }


def establecer_funcionamiento_dispositivoServ(
    dispositivo_id: int, estado: str, db: Session = None, current_user=None
):
    estado_lower = estado.lower()
    if estado_lower in ["activo", "active", "true", "1", "on"]:
        activo = True
    elif estado_lower in ["desactivo", "desactivado", "inactive", "false", "0", "off"]:
        activo = False
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Estado inválido. Use 'activo' o 'desactivado'.",
        )

    return actualizar_funcionamiento_usuario(
        dispositivo_id=dispositivo_id,
        activo=activo,
        db=db,
        current_user=current_user,
    )


def activar_bomba_legacyServ(
    dispositivo_id: int, db: Session = None, current_user=None
):
    return activar_dispositivoServ(
        dispositivo_id=dispositivo_id, db=db, current_user=current_user
    )


def desactivar_bomba_legacyServ(
    dispositivo_id: int, db: Session = None, current_user=None
):
    return desactivar_dispositivoServ(
        dispositivo_id=dispositivo_id, db=db, current_user=current_user
    )


def establecer_funcionamiento_dispositivo_legacyServ(
    dispositivo_id: int,
    activo: bool | None = None,
    db: Session = None,
    current_user=None,
):
    if activo is None:
        dispositivo = (
            data_repository.queryEstablecerFuncionamientoDispositivoLegacyDispositivo(
                db, dispositivo_id
            )
        )
        if dispositivo is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Dispositivo no encontrado",
            )
        activo = not dispositivo.funcionamiento_activo

    return actualizar_funcionamiento_usuario(
        dispositivo_id=dispositivo_id,
        activo=activo,
        db=db,
        current_user=current_user,
    )


def listar_dispositivos_legacyServ(
    id_usuario: int | None = None, db: Session = None, current_user=None
):
    return listar_dispositivosServ(
        id_usuario=id_usuario, db=db, current_user=current_user
    )


def listar_dispositivos_de_usuarioServ(
    id_user: int, db: Session = None, current_user=None
):
    """
    Lista todos los dispositivos asociados a un usuario específico (id_user),
    incluyendo la información de los sensores de cada dispositivo.
    Solo accesible por administradores (id_rol = 1).
    """
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador para realizar esta acción.",
        )

    # Verificar que el usuario objetivo exista
    usuario_obj = data_repository.queryListarDispositivosDeUsuarioUsuarioObj(
        db, id_user
    )
    if usuario_obj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado"
        )

    devs = data_repository.queryListarDispositivosDeUsuarioDevs(db, id_user)

    result = []
    for d in devs:
        # Consultar componentes de este dispositivo asignados
        asigs = data_repository.queryListarDispositivosDeUsuarioAsigs(db, d)

        from sqlalchemy import inspect

        d_dict = {
            attr.key: getattr(d, attr.key) for attr in inspect(d).mapper.column_attrs
        }
        d_dict["sensores"] = [
            {
                "id_sensor": asig.id_componente,
                "id_dispositivo": asig.id_dispositivo,
                "nombre": asig.componente.modelo.nombre_modelo
                if asig.componente
                else "Desconocido",
                "id_tipo_metrica": asig.componente.modelo.id_tipo_metrica
                if asig.componente
                else None,
                "pin_gpio": asig.pin_gpio,
                "estado": asig.componente.estado if asig.componente else "inactivo",
                "fecha_registro": asig.fecha_registro,
            }
            for asig in asigs
        ]
        result.append(d_dict)

    return result


def obtener_config_dispositivos_usuarioServ(
    id_user: int, db: Session = None, current_user=None
):
    """
    Retorna datos esenciales para la configuración de los archivos .ino de cada dispositivo de un usuario.
    Solo accesible por administradores (id_rol = 1).
    """
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador para realizar esta acción.",
        )

    # Verificar que el usuario objetivo exista
    usuario_obj = data_repository.queryObtenerConfigDispositivosUsuarioUsuarioObj(
        db, id_user
    )
    if usuario_obj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado"
        )

    devs = data_repository.queryObtenerConfigDispositivosUsuarioDevs(db, id_user)

    result = []
    for d in devs:
        # Consultar componentes de este dispositivo asignados
        asigs = data_repository.queryObtenerConfigDispositivosUsuarioAsigs(db, d)

        from sqlalchemy import inspect

        d_dict = {
            attr.key: getattr(d, attr.key) for attr in inspect(d).mapper.column_attrs
        }
        d_dict["sensores"] = [
            {
                "id_sensor": asig.id_componente,
                "nombre": asig.componente.modelo.nombre_modelo
                if asig.componente
                else "Desconocido",
            }
            for asig in asigs
        ]
        result.append(d_dict)

    return result


def procesar_activacion_dispositivo(
    dispositivo_id: int, active: bool, db: Session, current_user
):
    dispositivo = data_repository.queryProcesarActivacionDispositivoDispositivo(
        db, dispositivo_id
    )
    if dispositivo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Dispositivo no encontrado"
        )

    # 2. Validar propiedad / asignación del usuario actual (si no es admin)
    asig_query = data_repository.queryProcesarActivacionDispositivoAsigQuery(
        db, dispositivo_id
    )
    if current_user.id_rol != 1:
        asig_query = data_repository.queryProcesarActivacionDispositivoAsigQuery2(
            asig_query, current_user
        )

    asigs = data_repository.queryProcesarActivacionDispositivoAsigs(asig_query)
    if not asigs and current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para interactuar con este dispositivo o no está asignado a tu usuario.",
        )

    # 3. Activar todas las filas de asignaciones_iot asociadas a este dispositivo y usuario en comun
    for asig in asigs:
        asig.activo = active
        session_repository.add(db, asig)

    # 5. Publicar el estado vía MQTT al broker para sincronización física
    topic = f"yaku/dispositivo/{dispositivo.client_id_mqtt}/config"
    payload = json.dumps({"funcionamiento_activo": active})
    try:
        publish_mqtt_message(topic, payload, qos=1, retain=True)
    except Exception as mq_err:
        logger.info(
            f"[MQTT WARNING] No se pudo notificar al dispositivo {dispositivo.client_id_mqtt} via MQTT: {mq_err}"
        )

    session_repository.commit(db)

    estado_str = "activado" if active else "desactivado"
    return {
        "status": "ok",
        "message": f"Dispositivo {dispositivo.nombre} y sus asignaciones correspondientes han sido {estado_str}.",
        "dispositivo_id": dispositivo_id,
        "active": active,
    }


def listar_stock_disponiblesServ(db: Session = None, current_user=None):
    """
    Lista todos los dispositivos que están disponibles en el almacén (estado = 'disponible').
    Solo accesible por administradores (id_rol = 1).
    """
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador para realizar esta acción.",
        )
    return data_repository.queryListarStockDisponiblesResultado(db)


def asignar_dispositivo_a_cultivoServ(
    dispositivo_id: int,
    id_usuario: int,
    id_cultivo: int,
    db: Session = None,
    current_user=None,
):
    """
    Asigna un dispositivo disponible en stock a un agricultor y cultivo específico.
    El dispositivo cambia su estado a 'asignado' y se crean las asignaciones inactivas por defecto.
    Solo accesible por administradores (id_rol = 1).
    """
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador para realizar esta acción.",
        )

    # 1. Buscar dispositivo
    dev = data_repository.queryAsignarDispositivoACultivoDev(db, dispositivo_id)
    if not dev:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Dispositivo no encontrado"
        )

    if dev.estado != "disponible":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"El dispositivo no se puede asignar porque está en estado: '{dev.estado}' (debe estar 'disponible').",
        )

    # 2. Verificar que el usuario y cultivo existan
    # (Para simplificar, asumimos la existencia o validamos con consultas rápidas)
    cult = data_repository.queryAsignarDispositivoACultivoCult(
        db, id_cultivo, id_usuario
    )
    if not cult:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El cultivo especificado no existe o no pertenece a ese agricultor.",
        )

    metodo = dev.metodo_medicion
    if metodo in ("proximidad", "flujometro"):
        fuente = cult.fuente_agua
        esperada = "tanque" if metodo == "proximidad" else "conexion_directa"
        if fuente is None or normalize_source_type(fuente.tipo) != esperada:
            raise HTTPException(status_code=400, detail=f"El actuador con {metodo} requiere una fuente de agua de tipo {esperada}.")

    # 3. Cambiar estado físico del dispositivo
    dev.estado = "asignado"
    dev.en_almacen = False
    session_repository.add(db, dev)

    # 4. Crear asignación base lúdica en asignaciones_iot (activo = False por defecto)
    nueva_asig = asignaciones_iot(
        id_usuario=id_usuario,
        id_dispositivo=dispositivo_id,
        id_cultivo=id_cultivo,
        activo=False,  # Por defecto inactivo
    )
    session_repository.add(db, nueva_asig)
    session_repository.commit(db)

    # 5. Publicar mensaje MQTT INACTIVE para asegurar que inicia apagado lógicamente
    topic = f"yaku/dispositivo/{dev.client_id_mqtt}/config"
    try:
        publish_mqtt_message(topic, "INACTIVE", qos=1, retain=True)
    except Exception as mq_err:
        logger.info(f"⚠️ Error MQTT al silenciar dispositivo asignado: {mq_err}")

    return {
        "status": "ok",
        "message": f"Dispositivo {dev.nombre} asignado con éxito en stock al cultivo {cult.nombre_planta}.",
        "dispositivo_id": dispositivo_id,
        "id_usuario": id_usuario,
        "id_cultivo": id_cultivo,
    }


def liberar_dispositivo_a_stockServ(
    dispositivo_id: int, db: Session = None, current_user=None
):
    """
    Desvincula un dispositivo del agricultor/cultivo y lo regresa al stock disponible.
    Desactiva (o elimina) todas sus asignaciones activas e inhabilita su telemetría.
    Solo accesible por administradores (id_rol = 1).
    """
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador para realizar esta acción.",
        )

    # 1. Buscar dispositivo
    dev = data_repository.queryLiberarDispositivoAStockDev(db, dispositivo_id)
    if not dev:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Dispositivo no encontrado"
        )

    # 2. Cambiar estado físico del dispositivo a disponible en stock
    primer_almacen = data_repository.queryLiberarDispositivoAStockPrimerAlmacen(db)
    dev.estado = "disponible"
    dev.en_almacen = True
    dev.id_almacen = primer_almacen.id if primer_almacen else None
    session_repository.add(db, dev)

    # 3. Desactivar y eliminar/desasociar todas sus asignaciones lógicas y retornar componentes a almacén
    asigs = data_repository.queryLiberarDispositivoAStockAsigs(db, dispositivo_id)
    for asig in asigs:
        # Poner como inactivo y desvincular el componente para que no quede
        # una fila histórica compitiendo con la nueva asignación al reasignar
        # (evita el choque con el índice único de asignación activa).
        asig.activo = False
        if asig.id_componente:
            comp = data_repository.queryLiberarDispositivoAStockComp(db, asig)
            if comp:
                comp.estado = "disponible"
                comp.en_almacen = True
                comp.id_almacen = dev.id_almacen
                session_repository.add(db, comp)
        asig.id_componente = None
        asig.pin_gpio = None
        asig.id_tipo_metrica = None
        asig.id_fuente_agua = None
        session_repository.add(db, asig)

    session_repository.commit(db)

    # 4. Publicar mensaje MQTT INACTIVE para apagar telemetría
    topic = f"yaku/dispositivo/{dev.client_id_mqtt}/config"
    try:
        publish_mqtt_message(topic, "INACTIVE", qos=1, retain=True)
    except Exception as mq_err:
        logger.info(f"⚠️ Error MQTT al liberar dispositivo: {mq_err}")

    return {
        "status": "ok",
        "message": f"Dispositivo {dev.nombre} liberado y retornado al stock disponible.",
        "dispositivo_id": dispositivo_id,
    }


OFFSET_CALIBRACION_MIN = -50.0
OFFSET_CALIBRACION_MAX = 50.0


def calibrar_sensor_remotoServ(
    dispositivo_id: int,
    pin_gpio: int,
    offset: float,
    db: Session = None,
    current_user=None,
):
    """
    Calibra un sensor compensando sus lecturas con un offset. El offset se
    persiste en la asignación del sensor (dispositivo + pin) y se aplica a
    partir de ese momento a toda lectura de telemetría que ingrese para esa
    asignación (ver telemetriaRep.crear_datos_riego). También se publica por
    MQTT como instrucción informativa, aunque el efecto real ocurre en backend.
    """
    if not (OFFSET_CALIBRACION_MIN <= offset <= OFFSET_CALIBRACION_MAX):
        raise HTTPException(
            status_code=400,
            detail=(
                f"El offset debe estar entre {OFFSET_CALIBRACION_MIN} y "
                f"{OFFSET_CALIBRACION_MAX}."
            ),
        )

    dispositivo = data_repository.queryCalibrarSensorRemotoDispositivo(
        db, dispositivo_id
    )
    if dispositivo is None:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")

    # Validación de Seguridad
    if current_user.id_rol != 1:
        asig = data_repository.queryCalibrarSensorRemotoAsig(
            db, dispositivo_id, current_user
        )
        if not asig:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permiso para calibrar dispositivos en este cultivo.",
            )

    asig_pin = data_repository.queryCalibrarSensorRemotoAsigPorPin(
        db, dispositivo_id, pin_gpio
    )
    if asig_pin is None:
        raise HTTPException(
            status_code=404,
            detail="No se encontró un sensor asignado a ese pin para este dispositivo.",
        )

    topic = f"yaku/dispositivo/{dispositivo.client_id_mqtt}/config"
    payload = f"CALIBRAR:{pin_gpio}:{offset}"

    try:
        asig_pin.offset_calibracion = offset
        session_repository.add(db, asig_pin)

        try:
            publish_mqtt_message(topic, payload, qos=1, retain=True)
        except Exception as mq_err:
            logger.info(f"⚠️ No se pudo notificar la calibración por MQTT: {mq_err}")

        from src.main.model.models import logs_sistema

        nuevo_log = logs_sistema(
            id_usuario=current_user.id_usuario,
            accion="calibrar_sensor",
            modulo="hardware",
            descripcion=f"Offset de calibración de {dispositivo.nombre} (pin {pin_gpio}) actualizado a {offset}.",
        )
        session_repository.add(db, nuevo_log)
        session_repository.commit(db)

        return {
            "status": "ok",
            "message": f"Calibración aplicada: las próximas lecturas de {dispositivo.nombre} (pin {pin_gpio}) sumarán {offset}.",
            "offsetCalibracion": float(offset),
        }
    except HTTPException:
        raise
    except Exception as exc:
        session_repository.rollback(db)
        raise HTTPException(
            status_code=500, detail="Error interno del servidor"
        ) from exc


def registrar_dispositivoServ(
    payload: DispositivoCreate, db: Session = None, current_user=None
):
    """Registra un nuevo dispositivo en el inventario. Solo administradores."""
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador para realizar esta acción.",
        )

    tipo = data_repository.queryDeviceType(db, payload.id_tipo)
    if tipo is None:
        raise HTTPException(status_code=400, detail="Tipo de dispositivo no encontrado.")

    # Verificar si ya existe mac o client_id
    if payload.mac_address:
        existente_mac = data_repository.queryRegistrarDispositivoExistenteMac(
            db, payload
        )
        if existente_mac:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ya existe un dispositivo registrado con esa dirección MAC.",
            )

    if payload.client_id_mqtt:
        existente_mqtt = data_repository.queryRegistrarDispositivoExistenteMqtt(
            db, payload
        )
        if existente_mqtt:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ya existe un dispositivo registrado con ese Client ID MQTT.",
            )

    nuevo = dispositivos(
        id_tipo=payload.id_tipo,
        nombre=payload.nombre,
        mac_address=payload.mac_address,
        client_id_mqtt=payload.client_id_mqtt,
        topic_pub=payload.topic_pub,
        topic_sub=payload.topic_sub,
        id_almacen=payload.id_almacen,
        en_almacen=True,
        estado=payload.estado or "disponible",
        firmware_version=payload.firmware_version,
    )
    session_repository.add(db, nuevo)
    session_repository.commit(db)
    session_repository.refresh(db, nuevo)
    return nuevo


def registrar_componenteServ(
    payload: ComponenteCreate, db: Session = None, current_user=None
):
    """Registra un nuevo componente físico en stock. Solo administradores."""
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador para realizar esta acción.",
        )

    # Verificar si existe duplicado por número de serie
    if payload.numero_serie:
        existente = data_repository.queryRegistrarComponenteExistente(db, payload)
        if existente:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ya existe un componente registrado con este número de serie.",
            )

    nuevo = componentes(
        id_tipo_componente=payload.id_tipo_componente,
        numero_serie=payload.numero_serie,
        id_almacen=payload.id_almacen,
        en_almacen=True,
        estado=payload.estado or "disponible",
    )
    session_repository.add(db, nuevo)
    session_repository.commit(db)
    session_repository.refresh(db, nuevo)
    return nuevo


def cambiar_estado_dispositivo_stockServ(
    dispositivo_id: int, nuevo_estado: str, db: Session = None, current_user=None
):
    """
    Cambia el estado de un dispositivo en stock (Retirado, reparacion, disponible).
    """
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador para realizar esta acción.",
        )

    dev = data_repository.queryCambiarEstadoDispositivoStockDev(db, dispositivo_id)
    if not dev:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Dispositivo no encontrado"
        )

    if nuevo_estado == "Retirado":
        dev.estado = "Retirado"
        dev.en_almacen = False
        dev.id_almacen = None
    elif nuevo_estado == "reparacion":
        dev.estado = "reparacion"
        dev.en_almacen = True
    elif nuevo_estado == "disponible":
        dev.estado = "disponible"
        dev.en_almacen = True
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Estado no válido"
        )

    session_repository.add(db, dev)
    session_repository.commit(db)
    return {
        "status": "ok",
        "message": f"Estado del dispositivo actualizado a {nuevo_estado}",
    }


def cambiar_estado_componente_stockServ(
    componente_id: int, nuevo_estado: str, db: Session = None, current_user=None
):
    """
    Cambia el estado de un componente en stock (Retirado, reparacion, disponible).
    """
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador para realizar esta acción.",
        )

    comp = data_repository.queryCambiarEstadoComponenteStockComp(db, componente_id)
    if not comp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Componente no encontrado"
        )

    if nuevo_estado == "Retirado":
        comp.estado = "Retirado"
        comp.en_almacen = False
        comp.id_almacen = None
    elif nuevo_estado == "reparacion":
        comp.estado = "reparacion"
        comp.en_almacen = True
    elif nuevo_estado == "disponible":
        comp.estado = "disponible"
        comp.en_almacen = True
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Estado no válido"
        )

    session_repository.add(db, comp)
    session_repository.commit(db)
    return {
        "status": "ok",
        "message": f"Estado del componente actualizado a {nuevo_estado}",
    }


def asignar_componente_dispositivoServ(
    payload: AsignarComponentePayload, db: Session = None, current_user=None
):
    """
    Vincula un componente en stock a un dispositivo asignado en campo.
    El componente sale del almacén (id_almacen = None) y se crea un registro en asignaciones_iot.
    Si el componente es de categoría 'actuador', se registra una configuracion_tanque vacía.
    Solo accesible por administradores (id_rol = 1).
    """
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador para realizar esta acción.",
        )

    # 1. Buscar componente
    comp = data_repository.queryAsignarComponenteDispositivoComp(db, payload)
    if not comp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Componente no encontrado."
        )

    # Check if component is in stock OR already assigned to the same device
    is_in_stock = comp.en_almacen and comp.estado == "disponible"
    is_on_same_device = False

    if not is_in_stock:
        # Check if it is already assigned to the same device
        existing_asig = data_repository.queryAsignarComponenteDispositivoExistingAsig(
            db, comp, payload
        )
        if existing_asig:
            is_on_same_device = True
            if existing_asig.pin_gpio != payload.pin_gpio:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"El componente ya está conectado al pin GPIO {existing_asig.pin_gpio} en este dispositivo.",
                )

    if not (is_in_stock or is_on_same_device):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El componente seleccionado ya está asignado a otro dispositivo o no se encuentra en stock.",
        )

    es_actuador = bool(comp.modelo and comp.modelo.categoria == "actuador")
    es_sin_metrica = bool(comp.modelo and comp.modelo.categoria in ("actuador", "pantalla"))
    if not es_sin_metrica and payload.id_tipo_metrica is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Los componentes sensores requieren un parámetro de captura.",
        )

    # 2. Buscar dispositivo
    dev = data_repository.queryAsignarComponenteDispositivoDev(db, payload)
    if not dev:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Dispositivo no encontrado."
        )

    if dev.estado != "asignado":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El dispositivo debe estar asignado a un cultivo antes de vincular componentes.",
        )

    # 3. Buscar asignación base del dispositivo para obtener id_usuario e id_cultivo
    base_asig = data_repository.queryAsignarComponenteDispositivoBaseAsig(db, payload)

    if not base_asig:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El dispositivo no tiene una asignación base (usuario/cultivo) en el sistema.",
        )

    if is_on_same_device and es_sin_metrica:
        existing_asig.id_fuente_agua = payload.id_fuente_agua
        session_repository.add(db, existing_asig)
        config = data_repository.queryAsignarComponenteDispositivoConfig(
            db, existing_asig
        )
        if es_actuador and config is None:
            session_repository.add(
                db,
                configuracion_tanque(
                    id_asignacion=existing_asig.id,
                    valvula_abierta=False,
                    bomba_encendida=False,
                ),
            )
        session_repository.commit(db)
        return {
            "status": "ok",
            "message": f"Componente asignado con éxito al dispositivo {dev.nombre}.",
            "id_asignacion": existing_asig.id,
        }

    # 4. Crear registro en asignaciones_iot
    nueva_asig = asignaciones_iot(
        id_usuario=base_asig.id_usuario,
        id_dispositivo=payload.id_dispositivo,
        id_cultivo=base_asig.id_cultivo,
        id_componente=payload.id_componente,
        pin_gpio=payload.pin_gpio,
        id_tipo_metrica=None if es_sin_metrica else payload.id_tipo_metrica,
        id_fuente_agua=payload.id_fuente_agua,
        activo=False,
    )
    session_repository.add(db, nueva_asig)

    # 5. Marcar el componente como asignado y fuera del almacén
    comp.en_almacen = False
    comp.estado = "asignado"
    session_repository.add(db, comp)

    # Flush para obtener el ID de la nueva asignación
    session_repository.flush(db)

    # 6. Si es actuador, crear configuracion_tanque
    if es_actuador:
        nueva_conf = configuracion_tanque(
            id_asignacion=nueva_asig.id, valvula_abierta=False, bomba_encendida=False
        )
        session_repository.add(db, nueva_conf)

    session_repository.commit(db)

    return {
        "status": "ok",
        "message": f"Componente asignado con éxito al dispositivo {dev.nombre}.",
        "id_asignacion": nueva_asig.id,
    }


def liberar_componente_dispositivoServ(
    componente_id: int, db: Session = None, current_user=None
):
    """
    Desvincula un componente de su dispositivo y lo regresa al stock disponible.
    Desactiva las asignaciones activas asociadas a este componente.
    Solo accesible por administradores (id_rol = 1).
    """
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador para realizar esta acción.",
        )

    comp = data_repository.queryLiberarComponenteDispositivoComp(db, componente_id)
    if not comp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Componente no encontrado"
        )

    asigs = data_repository.queryLiberarComponenteDispositivoAsigs(db, componente_id)

    if not asigs:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El componente no tiene asignaciones en ningún dispositivo.",
        )

    # Obtener el almacén del dispositivo para regresar el componente al mismo almacén
    dest_almacen_id = None
    first_device = data_repository.queryLiberarComponenteDispositivoFirstDevice(
        db, asigs
    )
    if first_device:
        dest_almacen_id = first_device.id_almacen

    if dest_almacen_id is None:
        primer_almacen = data_repository.queryLiberarComponenteDispositivoPrimerAlmacen(
            db
        )
        dest_almacen_id = primer_almacen.id if primer_almacen else None

    # Desactivar las asignaciones y desvincular
    for asig in asigs:
        asig.activo = False
        asig.id_componente = None
        session_repository.add(db, asig)

    # Devolver componente al stock
    comp.estado = "disponible"
    comp.en_almacen = True
    comp.id_almacen = dest_almacen_id
    session_repository.add(db, comp)

    session_repository.commit(db)

    return {
        "status": "ok",
        "message": f"Componente desvinculado con éxito y retornado a stock.",
    }


def actualizar_asignacion_componenteServ(
    asignacion_id: int,
    payload: ActualizarAsignacionComponentePayload,
    db: Session = None,
    current_user=None,
):
    """
    Actualiza el pin GPIO, el parámetro de captura y/o la fuente de agua de una
    asignación de componente ya existente, sin crear ni eliminar filas.
    Solo accesible por administradores (id_rol = 1).
    """
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador para realizar esta acción.",
        )

    asig = data_repository.queryActualizarAsignacionComponenteAsig(db, asignacion_id)
    if not asig:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Asignación no encontrada."
        )

    comp = data_repository.queryLiberarComponenteDispositivoComp(db, asig.id_componente)
    es_sin_metrica = bool(
        comp and comp.modelo and comp.modelo.categoria in ("actuador", "pantalla")
    )
    if not es_sin_metrica and payload.id_tipo_metrica is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Los componentes sensores requieren un parámetro de captura.",
        )

    asig.pin_gpio = payload.pin_gpio
    asig.id_tipo_metrica = None if es_sin_metrica else payload.id_tipo_metrica
    asig.id_fuente_agua = payload.id_fuente_agua
    session_repository.add(db, asig)
    session_repository.commit(db)

    return {
        "status": "ok",
        "message": "Asignación actualizada con éxito.",
    }


def obtener_detalle_dispositivoServ(
    dispositivo_id: int, db: Session = None, current_user=None
):
    """
    Obtiene los detalles de un dispositivo por su ID.
    """
    dispositivo = data_repository.queryObtenerDetalleDispositivoDispositivo(
        db, dispositivo_id
    )
    if dispositivo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Dispositivo no encontrado"
        )

    # Validar propiedad para no-administradores
    if current_user.id_rol != 1 and dispositivo.id_usuario != current_user.id_usuario:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para ver los detalles de este dispositivo",
        )

    return dispositivo


def activar_desactivar_dispositivo_pluralServ(
    dispositivo_id: int, active: bool, db: Session = None, current_user=None
):
    return procesar_activacion_dispositivo(dispositivo_id, active, db, current_user)


def activar_desactivar_dispositivo_singularServ(
    dispositivo_id: int, active: bool, db: Session = None, current_user=None
):
    return procesar_activacion_dispositivo(dispositivo_id, active, db, current_user)
