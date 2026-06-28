from typing import List
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ...tasks.mqtt_subscriber import publish_mqtt_message
from ...db.models import dispositivos, usuarios, asignaciones_iot, tipos_dispositivo, tipos_componente, componentes, configuracion_tanque
from ...schemas.dispositivo import (
    DispositivoResponseModel, DispositivoConSensoresResponseModel, DispositivoConfigResponseModel,
    DispositivoCreate, ComponenteResponseModel, ComponenteCreate, TipoComponenteResponseModel, TipoDispositivoResponseModel,
    DispositivoAdminResponse, AsignarComponentePayload, TipoMetricaResponseModel
)
from ..dependencies import get_db

logger = logging.getLogger(__name__)
from ...core.bff_auth import get_current_user_or_bff

router = APIRouter(prefix="/dispositivos", tags=["Dispositivos"])
legacy_router = APIRouter(prefix="/bomba", tags=["Legacy Bomba"])
singular_router = APIRouter(prefix="/dispositivo", tags=["Dispositivo Singular"])


@router.get("", response_model=List[DispositivoAdminResponse])
def listar_dispositivos(
    id_usuario: int | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """
    Lista los dispositivos del sistema.
    """
    if current_user.id_rol != 1:
        id_usuario = current_user.id_usuario

    if id_usuario is not None:
        return db.query(dispositivos).join(asignaciones_iot).filter(
            asignaciones_iot.id_usuario == id_usuario
        ).distinct().all()

    return db.query(dispositivos).all()


@router.get("/me", response_model=List[DispositivoResponseModel])
def listar_mis_dispositivos(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """
    Retorna la lista de dispositivos asignados únicamente al usuario autenticado actual.
    """
    return db.query(dispositivos).join(asignaciones_iot).filter(
        asignaciones_iot.id_usuario == current_user.id_usuario
    ).distinct().all()


@router.get("/tipos", response_model=List[TipoDispositivoResponseModel])
def listar_tipos_dispositivo(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff)
):
    """Lista todos los tipos de dispositivos disponibles."""
    return db.query(tipos_dispositivo).all()


@router.get("/metricas", response_model=List[TipoMetricaResponseModel])
def listar_tipos_metrica(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff)
):
    """Lista todos los tipos de métricas disponibles."""
    from ...db.models import tipos_metrica
    return db.query(tipos_metrica).order_by(tipos_metrica.id.asc()).all()


@router.get("/componentes/tipos", response_model=List[TipoComponenteResponseModel])
def listar_tipos_componente(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff)
):
    """Lista todos los tipos de componentes disponibles en el catálogo."""
    return db.query(tipos_componente).all()


@router.get("/componentes", response_model=List[ComponenteResponseModel])
def listar_componentes(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff)
):
    """Lista todos los componentes físicos registrados en el inventario."""
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador para realizar esta acción."
        )
    return db.query(componentes).order_by(componentes.id.asc()).all()


@router.get("/siguiente-client-id")
def obtener_siguiente_client_id(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff)
):
    """
    Calcula el siguiente Client ID MQTT consultando en la base de datos.
    Solo administradores.
    """
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador para realizar esta acción."
        )

    # Obtener todos los client_id_mqtt que siguen el patron ESP32_Yaku_
    items = db.query(dispositivos.client_id_mqtt).filter(
        dispositivos.client_id_mqtt.like("ESP32_Yaku_%")
    ).all()

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



@router.post("/activar/{dispositivo_id}")
def activar_dispositivo(
    dispositivo_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    dispositivo = db.query(dispositivos).filter(dispositivos.id_dispositivo == dispositivo_id).first()
    if dispositivo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dispositivo no encontrado")

    # Validación de Seguridad
    if current_user.id_rol != 1 and dispositivo.id_usuario != current_user.id_usuario:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para controlar este dispositivo",
        )

    topic = dispositivo.topic_sub or "yaku/valvula/comando"

    try:
        publish_mqtt_message(topic, "ON", qos=1, retain=True)
        return {"status": "ok", "accion": "activar", "topic": topic, "dispositivo_id": dispositivo_id}
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno del servidor") from exc


@router.post("/desactivar/{dispositivo_id}")
def desactivar_dispositivo(
    dispositivo_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    dispositivo = db.query(dispositivos).filter(dispositivos.id_dispositivo == dispositivo_id).first()
    if dispositivo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dispositivo no encontrado")

    # Validación de Seguridad
    if current_user.id_rol != 1 and dispositivo.id_usuario != current_user.id_usuario:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para controlar este dispositivo",
        )

    topic = dispositivo.topic_sub or "yaku/valvula/comando"

    try:
        publish_mqtt_message(topic, "OFF", qos=1, retain=True)
        return {"status": "ok", "accion": "desactivar", "topic": topic, "dispositivo_id": dispositivo_id}
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno del servidor") from exc


def actualizar_funcionamiento_usuario(
    dispositivo_id: int,
    activo: bool,
    db: Session,
    current_user,
):
    dispositivo = db.query(dispositivos).filter(dispositivos.id_dispositivo == dispositivo_id).first()
    if dispositivo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dispositivo no encontrado")

    # 1. Obtener todas las asignaciones para este dispositivo y el usuario
    asig_query = db.query(asignaciones_iot).filter(asignaciones_iot.id_dispositivo == dispositivo_id)
    if current_user.id_rol != 1:
        asig_query = asig_query.filter(asignaciones_iot.id_usuario == current_user.id_usuario)
    asigs = asig_query.all()

    if not asigs and current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para modificar este dispositivo o no está asignado a tu usuario.",
        )

    # 1.1 Si se intenta activar un actuador (tipo 2), validar que el sensor (tipo 1) del cultivo esté activo
    if activo and dispositivo.id_tipo == 2:
        cultivos_ids = [a.id_cultivo for a in asigs if a.id_cultivo is not None]
        if cultivos_ids:
            sensor_activo = db.query(asignaciones_iot).join(dispositivos).filter(
                asignaciones_iot.id_cultivo.in_(cultivos_ids),
                dispositivos.id_tipo == 1,
                asignaciones_iot.activo == True
            ).first()
            if not sensor_activo:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No se puede activar el dispositivo actuador: Primero debe activar el dispositivo de sensores."
                )

    # 2. Actualizar el estado de estas asignaciones
    for asig in asigs:
        asig.activo = activo
        db.add(asig)

    # 3. Publicar el nuevo estado vía MQTT al dispositivo para sincronización dinámica
    topic = f"yaku/dispositivo/{dispositivo.client_id_mqtt}/config"
    payload = "ACTIVE" if activo else "INACTIVE"
    try:
        publish_mqtt_message(topic, payload, qos=1, retain=True)
    except Exception as mq_err:
        logger.info(f"[MQTT WARNING] No se pudo notificar al dispositivo {dispositivo.client_id_mqtt} via MQTT: {mq_err}")

    db.commit()

    estado_str = "activado" if activo else "desactivado"
    return {
        "status": "ok",
        "message": f"Captura de datos y control automático {estado_str} para el dispositivo y sus vinculados",
        "dispositivo_id": dispositivo_id,
        "funcionamiento_activo": activo
    }


@router.post("/funcionamiento/{dispositivo_id}/{estado}")
def establecer_funcionamiento_dispositivo(
    dispositivo_id: int,
    estado: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    estado_lower = estado.lower()
    if estado_lower in ["activo", "active", "true", "1", "on"]:
        activo = True
    elif estado_lower in ["desactivo", "desactivado", "inactive", "false", "0", "off"]:
        activo = False
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Estado inválido. Use 'activo' o 'desactivado'."
        )

    return actualizar_funcionamiento_usuario(
        dispositivo_id=dispositivo_id,
        activo=activo,
        db=db,
        current_user=current_user,
    )


# --- LEGACY BOMBA ROUTER FOR BACKWARD COMPATIBILITY ---

@legacy_router.post("/activar/{dispositivo_id}")
def activar_bomba_legacy(
    dispositivo_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    return activar_dispositivo(dispositivo_id=dispositivo_id, db=db, current_user=current_user)


@legacy_router.post("/desactivar/{dispositivo_id}")
def desactivar_bomba_legacy(
    dispositivo_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    return desactivar_dispositivo(dispositivo_id=dispositivo_id, db=db, current_user=current_user)


@legacy_router.post("/funcionamiento/{dispositivo_id}")
def establecer_funcionamiento_dispositivo_legacy(
    dispositivo_id: int,
    activo: bool | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    if activo is None:
        dispositivo = db.query(dispositivos).filter(dispositivos.id_dispositivo == dispositivo_id).first()
        if dispositivo is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dispositivo no encontrado")
        activo = not dispositivo.funcionamiento_activo

    return actualizar_funcionamiento_usuario(
        dispositivo_id=dispositivo_id,
        activo=activo,
        db=db,
        current_user=current_user,
    )


@legacy_router.get("/dispositivos", response_model=List[DispositivoResponseModel])
def listar_dispositivos_legacy(
    id_usuario: int | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    return listar_dispositivos(id_usuario=id_usuario, db=db, current_user=current_user)


@router.get("/usuario/{id_user}", response_model=List[DispositivoConSensoresResponseModel])
def listar_dispositivos_de_usuario(
    id_user: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """
    Lista todos los dispositivos asociados a un usuario específico (id_user),
    incluyendo la información de los sensores de cada dispositivo.
    Solo accesible por administradores (id_rol = 1).
    """
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador para realizar esta acción."
        )
    
    # Verificar que el usuario objetivo exista
    usuario_obj = db.query(usuarios).filter(usuarios.id_usuario == id_user).first()
    if usuario_obj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )
    
    devs = db.query(dispositivos).join(asignaciones_iot).filter(
        asignaciones_iot.id_usuario == id_user
    ).distinct().order_by(dispositivos.id_dispositivo).all()
    
    result = []
    for d in devs:
        # Consultar componentes de este dispositivo asignados
        asigs = db.query(asignaciones_iot).filter(
            asignaciones_iot.id_dispositivo == d.id_dispositivo,
            asignaciones_iot.id_componente != None
        ).order_by(asignaciones_iot.id).all()
        
        from sqlalchemy import inspect
        d_dict = {attr.key: getattr(d, attr.key) for attr in inspect(d).mapper.column_attrs}
        d_dict["sensores"] = [
            {
                "id_sensor": asig.id_componente,
                "id_dispositivo": asig.id_dispositivo,
                "nombre": asig.componente.modelo.nombre_modelo if asig.componente else "Desconocido",
                "id_tipo_metrica": asig.componente.modelo.id_tipo_metrica if asig.componente else None,
                "pin_gpio": asig.pin_gpio,
                "estado": asig.componente.estado if asig.componente else "inactivo",
                "fecha_registro": asig.fecha_registro
            }
            for asig in asigs
        ]
        result.append(d_dict)
        
    return result


@router.get("/usuario/config/{id_user}", response_model=List[DispositivoConfigResponseModel])
def obtener_config_dispositivos_usuario(
    id_user: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """
    Retorna datos esenciales para la configuración de los archivos .ino de cada dispositivo de un usuario.
    Solo accesible por administradores (id_rol = 1).
    """
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador para realizar esta acción."
        )

    # Verificar que el usuario objetivo exista
    usuario_obj = db.query(usuarios).filter(usuarios.id_usuario == id_user).first()
    if usuario_obj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )

    devs = db.query(dispositivos).join(asignaciones_iot).filter(
        asignaciones_iot.id_usuario == id_user
    ).distinct().order_by(dispositivos.id_dispositivo).all()

    result = []
    for d in devs:
        # Consultar componentes de este dispositivo asignados
        asigs = db.query(asignaciones_iot).filter(
            asignaciones_iot.id_dispositivo == d.id_dispositivo,
            asignaciones_iot.id_componente != None
        ).order_by(asignaciones_iot.id).all()

        from sqlalchemy import inspect
        d_dict = {attr.key: getattr(d, attr.key) for attr in inspect(d).mapper.column_attrs}
        d_dict["sensores"] = [
            {
                "id_sensor": asig.id_componente,
                "nombre": asig.componente.modelo.nombre_modelo if asig.componente else "Desconocido"
            }
            for asig in asigs
        ]
        result.append(d_dict)

    return result


def procesar_activacion_dispositivo(
    dispositivo_id: int,
    active: bool,
    db: Session,
    current_user,
):
    # 1. Buscar el dispositivo
    dispositivo = db.query(dispositivos).filter(dispositivos.id_dispositivo == dispositivo_id).first()
    if dispositivo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dispositivo no encontrado")

    # 2. Validar propiedad / asignación del usuario actual (si no es admin)
    asig_query = db.query(asignaciones_iot).filter(
        asignaciones_iot.id_dispositivo == dispositivo_id
    )
    if current_user.id_rol != 1:
        asig_query = asig_query.filter(asignaciones_iot.id_usuario == current_user.id_usuario)

    asigs = asig_query.all()
    if not asigs and current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para interactuar con este dispositivo o no está asignado a tu usuario."
        )

    # 3. Activar todas las filas de asignaciones_iot asociadas a este dispositivo y usuario en comun
    for asig in asigs:
        asig.activo = active
        db.add(asig)

    # 5. Publicar el estado vía MQTT al broker para sincronización física
    topic = f"yaku/dispositivo/{dispositivo.client_id_mqtt}/config"
    payload = "ACTIVE" if active else "INACTIVE"
    try:
        publish_mqtt_message(topic, payload, qos=1, retain=True)
    except Exception as mq_err:
        logger.info(f"[MQTT WARNING] No se pudo notificar al dispositivo {dispositivo.client_id_mqtt} via MQTT: {mq_err}")

    db.commit()

    estado_str = "activado" if active else "desactivado"
    return {
        "status": "ok",
        "message": f"Dispositivo {dispositivo.nombre} y sus asignaciones correspondientes han sido {estado_str}.",
        "dispositivo_id": dispositivo_id,
        "active": active
    }



# --- ADMISTRATIVE STOCK / WAREHOUSE ENDPOINTS ---

@router.get("/admin/stock", response_model=List[DispositivoResponseModel])
def listar_stock_disponibles(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """
    Lista todos los dispositivos que están disponibles en el almacén (estado = 'disponible').
    Solo accesible por administradores (id_rol = 1).
    """
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador para realizar esta acción."
        )
    return db.query(dispositivos).filter(dispositivos.estado == "disponible").all()


@router.post("/admin/asignar/{dispositivo_id}/{id_usuario}/{id_cultivo}")
def asignar_dispositivo_a_cultivo(
    dispositivo_id: int,
    id_usuario: int,
    id_cultivo: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """
    Asigna un dispositivo disponible en stock a un agricultor y cultivo específico.
    El dispositivo cambia su estado a 'asignado' y se crean las asignaciones inactivas por defecto.
    Solo accesible por administradores (id_rol = 1).
    """
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador para realizar esta acción."
        )
    
    # 1. Buscar dispositivo
    dev = db.query(dispositivos).filter(dispositivos.id_dispositivo == dispositivo_id).first()
    if not dev:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dispositivo no encontrado")
        
    if dev.estado != "disponible":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"El dispositivo no se puede asignar porque está en estado: '{dev.estado}' (debe estar 'disponible')."
        )
        
    # 2. Verificar que el usuario y cultivo existan
    # (Para simplificar, asumimos la existencia o validamos con consultas rápidas)
    from ...db.models import cultivos
    cult = db.query(cultivos).filter(cultivos.id_cultivo == id_cultivo, cultivos.id_usuario == id_usuario).first()
    if not cult:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El cultivo especificado no existe o no pertenece a ese agricultor."
        )

    # 3. Cambiar estado físico del dispositivo
    dev.estado = "asignado"
    dev.en_almacen = False
    db.add(dev)
    
    # 4. Crear asignación base lúdica en asignaciones_iot (activo = False por defecto)
    nueva_asig = asignaciones_iot(
        id_usuario=id_usuario,
        id_dispositivo=dispositivo_id,
        id_cultivo=id_cultivo,
        activo=False  # Por defecto inactivo
    )
    db.add(nueva_asig)
    db.commit()
    
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
        "id_cultivo": id_cultivo
    }


@router.post("/admin/liberar/{dispositivo_id}")
def liberar_dispositivo_a_stock(
    dispositivo_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """
    Desvincula un dispositivo del agricultor/cultivo y lo regresa al stock disponible.
    Desactiva (o elimina) todas sus asignaciones activas e inhabilita su telemetría.
    Solo accesible por administradores (id_rol = 1).
    """
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador para realizar esta acción."
        )
        
    # 1. Buscar dispositivo
    dev = db.query(dispositivos).filter(dispositivos.id_dispositivo == dispositivo_id).first()
    if not dev:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dispositivo no encontrado")
        
    # 2. Cambiar estado físico del dispositivo a disponible en stock
    from ...db.models import almacenes
    primer_almacen = db.query(almacenes).order_by(almacenes.id.asc()).first()
    dev.estado = "disponible"
    dev.en_almacen = True
    dev.id_almacen = primer_almacen.id if primer_almacen else None
    db.add(dev)
    
    # 3. Desactivar y eliminar/desasociar todas sus asignaciones lógicas y retornar componentes a almacén
    asigs = db.query(asignaciones_iot).filter(asignaciones_iot.id_dispositivo == dispositivo_id).all()
    for asig in asigs:
        # Poner como inactivo
        asig.activo = False
        db.add(asig)
        if asig.id_componente:
            comp = db.query(componentes).filter(componentes.id == asig.id_componente).first()
            if comp:
                comp.estado = "disponible"
                comp.en_almacen = True
                comp.id_almacen = dev.id_almacen
                db.add(comp)
        # Opcional: eliminar físicamente si se prefiere una limpieza total:
        # db.delete(asig)
        
    db.commit()
    
    # 4. Publicar mensaje MQTT INACTIVE para apagar telemetría
    topic = f"yaku/dispositivo/{dev.client_id_mqtt}/config"
    try:
        publish_mqtt_message(topic, "INACTIVE", qos=1, retain=True)
    except Exception as mq_err:
        logger.info(f"⚠️ Error MQTT al liberar dispositivo: {mq_err}")
        
    return {
        "status": "ok",
        "message": f"Dispositivo {dev.nombre} liberado y retornado al stock disponible.",
        "dispositivo_id": dispositivo_id
    }


@router.post("/calibrar/{dispositivo_id}/{pin_gpio}/{offset}")
def calibrar_sensor_remoto(
    dispositivo_id: int,
    pin_gpio: int,
    offset: float,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """
    Permite calibrar un sensor físicamente compensando las lecturas (offset)
    y enviando la instrucción vía MQTT al microcontrolador.
    """
    dispositivo = db.query(dispositivos).filter(dispositivos.id_dispositivo == dispositivo_id).first()
    if dispositivo is None:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")

    # Validación de Seguridad
    if current_user.id_rol != 1:
        asig = db.query(asignaciones_iot).filter(
            asignaciones_iot.id_dispositivo == dispositivo_id,
            asignaciones_iot.id_usuario == current_user.id_usuario
        ).first()
        if not asig:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permiso para calibrar dispositivos en este cultivo."
            )

    topic = f"yaku/dispositivo/{dispositivo.client_id_mqtt}/config"
    payload = f"CALIBRAR:{pin_gpio}:{offset}"
    
    try:
        publish_mqtt_message(topic, payload, qos=1, retain=True)
        
        from ...db.models import logs_sistema
        nuevo_log = logs_sistema(
            id_usuario=current_user.id_usuario,
            accion="calibrar_sensor",
            modulo="hardware",
            descripcion=f"Calibración enviada al dispositivo {dispositivo.nombre} en pin {pin_gpio} con offset {offset}."
        )
        db.add(nuevo_log)
        db.commit()
        
        return {
            "status": "ok",
            "message": f"Instrucción de calibración enviada correctamente al dispositivo {dispositivo.nombre}.",
            "topic": topic,
            "payload": payload
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Error interno del servidor") from exc


@router.post("", response_model=DispositivoResponseModel, status_code=status.HTTP_201_CREATED)
def registrar_dispositivo(
    payload: DispositivoCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff)
):
    """Registra un nuevo dispositivo en el inventario. Solo administradores."""
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador para realizar esta acción."
        )

    # Verificar si ya existe mac o client_id
    if payload.mac_address:
        existente_mac = db.query(dispositivos).filter(dispositivos.mac_address == payload.mac_address).first()
        if existente_mac:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ya existe un dispositivo registrado con esa dirección MAC."
            )
            
    if payload.client_id_mqtt:
        existente_mqtt = db.query(dispositivos).filter(dispositivos.client_id_mqtt == payload.client_id_mqtt).first()
        if existente_mqtt:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ya existe un dispositivo registrado con ese Client ID MQTT."
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
        firmware_version=payload.firmware_version
    )
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo


@router.post("/componentes", response_model=ComponenteResponseModel, status_code=status.HTTP_201_CREATED)
def registrar_componente(
    payload: ComponenteCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff)
):
    """Registra un nuevo componente físico en stock. Solo administradores."""
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador para realizar esta acción."
        )

    # Verificar si existe duplicado por número de serie
    if payload.numero_serie:
        existente = db.query(componentes).filter(componentes.numero_serie == payload.numero_serie).first()
        if existente:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ya existe un componente registrado con este número de serie."
            )

    nuevo = componentes(
        id_tipo_componente=payload.id_tipo_componente,
        numero_serie=payload.numero_serie,
        id_almacen=payload.id_almacen,
        en_almacen=True,
        estado=payload.estado or "disponible"
    )
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo


@router.post("/admin/dispositivo/{dispositivo_id}/estado/{nuevo_estado}")
def cambiar_estado_dispositivo_stock(
    dispositivo_id: int,
    nuevo_estado: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """
    Cambia el estado de un dispositivo en stock (Retirado, reparacion, disponible).
    """
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador para realizar esta acción."
        )

    dev = db.query(dispositivos).filter(dispositivos.id_dispositivo == dispositivo_id).first()
    if not dev:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dispositivo no encontrado")

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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Estado no válido")

    db.add(dev)
    db.commit()
    return {"status": "ok", "message": f"Estado del dispositivo actualizado a {nuevo_estado}"}


@router.post("/admin/componente/{componente_id}/estado/{nuevo_estado}")
def cambiar_estado_componente_stock(
    componente_id: int,
    nuevo_estado: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """
    Cambia el estado de un componente en stock (Retirado, reparacion, disponible).
    """
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador para realizar esta acción."
        )

    comp = db.query(componentes).filter(componentes.id == componente_id).first()
    if not comp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Componente no encontrado")

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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Estado no válido")

    db.add(comp)
    db.commit()
    return {"status": "ok", "message": f"Estado del componente actualizado a {nuevo_estado}"}


@router.post("/admin/asignar-componente")
def asignar_componente_dispositivo(
    payload: AsignarComponentePayload,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
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
            detail="No tienes permisos de administrador para realizar esta acción."
        )

    # 1. Buscar componente
    comp = db.query(componentes).filter(componentes.id == payload.id_componente).first()
    if not comp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Componente no encontrado."
        )

    # Check if component is in stock OR already assigned to the same device
    is_in_stock = comp.en_almacen and comp.estado == "disponible"
    is_on_same_device = False
    
    if not is_in_stock:
        # Check if it is already assigned to the same device
        existing_asig = db.query(asignaciones_iot).filter(
            asignaciones_iot.id_componente == comp.id,
            asignaciones_iot.id_dispositivo == payload.id_dispositivo
        ).first()
        if existing_asig:
            is_on_same_device = True
            if existing_asig.pin_gpio != payload.pin_gpio:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"El componente ya está conectado al pin GPIO {existing_asig.pin_gpio} en este dispositivo."
                )

    if not (is_in_stock or is_on_same_device):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El componente seleccionado ya está asignado a otro dispositivo o no se encuentra en stock."
        )

    es_actuador = bool(comp.modelo and comp.modelo.categoria == "actuador")
    if not es_actuador and payload.id_tipo_metrica is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Los componentes sensores requieren un parámetro de captura."
        )

    # 2. Buscar dispositivo
    dev = db.query(dispositivos).filter(dispositivos.id_dispositivo == payload.id_dispositivo).first()
    if not dev:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dispositivo no encontrado."
        )

    if dev.estado != "asignado":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El dispositivo debe estar asignado a un cultivo antes de vincular componentes."
        )

    # 3. Buscar asignación base del dispositivo para obtener id_usuario e id_cultivo
    base_asig = db.query(asignaciones_iot).filter(
        asignaciones_iot.id_dispositivo == payload.id_dispositivo
    ).first()

    if not base_asig:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El dispositivo no tiene una asignación base (usuario/cultivo) en el sistema."
        )

    if is_on_same_device and es_actuador:
        existing_asig.id_fuente_agua = payload.id_fuente_agua
        db.add(existing_asig)
        config = db.query(configuracion_tanque).filter(
            configuracion_tanque.id_asignacion == existing_asig.id
        ).first()
        if config is None:
            db.add(configuracion_tanque(
                id_asignacion=existing_asig.id,
                valvula_abierta=False,
                bomba_encendida=False
            ))
        db.commit()
        return {
            "status": "ok",
            "message": f"Componente asignado con éxito al dispositivo {dev.nombre}.",
            "id_asignacion": existing_asig.id
        }

    # 4. Crear registro en asignaciones_iot
    nueva_asig = asignaciones_iot(
        id_usuario=base_asig.id_usuario,
        id_dispositivo=payload.id_dispositivo,
        id_cultivo=base_asig.id_cultivo,
        id_componente=payload.id_componente,
        pin_gpio=payload.pin_gpio,
        id_tipo_metrica=None if es_actuador else payload.id_tipo_metrica,
        id_fuente_agua=payload.id_fuente_agua,
        activo=False
    )
    db.add(nueva_asig)

    # 5. Marcar el componente como asignado y fuera del almacén
    comp.en_almacen = False
    comp.estado = "asignado"
    db.add(comp)

    # Flush para obtener el ID de la nueva asignación
    db.flush()

    # 6. Si es actuador, crear configuracion_tanque
    if es_actuador:
        nueva_conf = configuracion_tanque(
            id_asignacion=nueva_asig.id,
            valvula_abierta=False,
            bomba_encendida=False
        )
        db.add(nueva_conf)

    db.commit()

    return {
        "status": "ok",
        "message": f"Componente asignado con éxito al dispositivo {dev.nombre}.",
        "id_asignacion": nueva_asig.id
    }


@router.post("/admin/liberar-componente/{componente_id}")
def liberar_componente_dispositivo(
    componente_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """
    Desvincula un componente de su dispositivo y lo regresa al stock disponible.
    Desactiva las asignaciones activas asociadas a este componente.
    Solo accesible por administradores (id_rol = 1).
    """
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador para realizar esta acción."
        )

    comp = db.query(componentes).filter(componentes.id == componente_id).first()
    if not comp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Componente no encontrado")

    asigs = db.query(asignaciones_iot).filter(
        asignaciones_iot.id_componente == componente_id
    ).all()

    if not asigs:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El componente no tiene asignaciones en ningún dispositivo."
        )

    # Obtener el almacén del dispositivo para regresar el componente al mismo almacén
    dest_almacen_id = None
    first_device = db.query(dispositivos).filter(dispositivos.id_dispositivo == asigs[0].id_dispositivo).first()
    if first_device:
        dest_almacen_id = first_device.id_almacen

    if dest_almacen_id is None:
        from ...db.models import almacenes
        primer_almacen = db.query(almacenes).order_by(almacenes.id.asc()).first()
        dest_almacen_id = primer_almacen.id if primer_almacen else None

    # Desactivar las asignaciones y desvincular
    for asig in asigs:
        asig.activo = False
        asig.id_componente = None
        db.add(asig)

    # Devolver componente al stock
    comp.estado = "disponible"
    comp.en_almacen = True
    comp.id_almacen = dest_almacen_id
    db.add(comp)

    db.commit()

    return {
        "status": "ok",
        "message": f"Componente desvinculado con éxito y retornado a stock."
    }


# --- PARAMETERIZED ROUTE RESOLUTION FALLBACKS ---

@router.get("/{dispositivo_id}", response_model=DispositivoResponseModel)
def obtener_detalle_dispositivo(
    dispositivo_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """
    Obtiene los detalles de un dispositivo por su ID.
    """
    dispositivo = db.query(dispositivos).filter(dispositivos.id_dispositivo == dispositivo_id).first()
    if dispositivo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dispositivo no encontrado"
        )

    # Validar propiedad para no-administradores
    if current_user.id_rol != 1 and dispositivo.id_usuario != current_user.id_usuario:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para ver los detalles de este dispositivo"
        )

    return dispositivo


@router.post("/{dispositivo_id}/{active}")
def activar_desactivar_dispositivo_plural(
    dispositivo_id: int,
    active: bool,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    return procesar_activacion_dispositivo(dispositivo_id, active, db, current_user)


@singular_router.post("/{dispositivo_id}/{active}")
def activar_desactivar_dispositivo_singular(
    dispositivo_id: int,
    active: bool,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    return procesar_activacion_dispositivo(dispositivo_id, active, db, current_user)



