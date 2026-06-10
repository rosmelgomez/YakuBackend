from typing import Generator, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..tasks.mqtt_subscriber import publish_mqtt_message
from ..models.database import SessionLocal
from ..models.models import dispositivos, usuarios, asignaciones_iot
from ..schemas.schemas import DispositivoResponseModel, DispositivoConSensoresResponseModel, DispositivoConfigResponseModel
from .auth import get_db
from ..core.bff_auth import get_current_user_or_bff

router = APIRouter(prefix="/dispositivos", tags=["Dispositivos"])
legacy_router = APIRouter(prefix="/bomba", tags=["Legacy Bomba"])
singular_router = APIRouter(prefix="/dispositivo", tags=["Dispositivo Singular"])


@router.get("", response_model=List[DispositivoResponseModel])
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
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


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
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


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
        print(f"[MQTT WARNING] No se pudo notificar al dispositivo {dispositivo.client_id_mqtt} via MQTT: {mq_err}")

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
        print(f"[MQTT WARNING] No se pudo notificar al dispositivo {dispositivo.client_id_mqtt} via MQTT: {mq_err}")

    db.commit()

    estado_str = "activado" if active else "desactivado"
    return {
        "status": "ok",
        "message": f"Dispositivo {dispositivo.nombre} y sus asignaciones correspondientes han sido {estado_str}.",
        "dispositivo_id": dispositivo_id,
        "active": active
    }


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
    from ..models.models import cultivos
    cult = db.query(cultivos).filter(cultivos.id_cultivo == id_cultivo, cultivos.id_usuario == id_usuario).first()
    if not cult:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El cultivo especificado no existe o no pertenece a ese agricultor."
        )

    # 3. Cambiar estado físico del dispositivo
    dev.estado = "asignado"
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
        print(f"⚠️ Error MQTT al silenciar dispositivo asignado: {mq_err}")
        
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
    dev.estado = "disponible"
    dev.ubicacion = "Almacén Principal"  # Por defecto regresa al almacén
    db.add(dev)
    
    # 3. Desactivar y eliminar/desasociar todas sus asignaciones lógicas
    asigs = db.query(asignaciones_iot).filter(asignaciones_iot.id_dispositivo == dispositivo_id).all()
    for asig in asigs:
        # Poner como inactivo
        asig.activo = False
        db.add(asig)
        # Opcional: eliminar físicamente si se prefiere una limpieza total:
        # db.delete(asig)
        
    db.commit()
    
    # 4. Publicar mensaje MQTT INACTIVE para apagar telemetría
    topic = f"yaku/dispositivo/{dev.client_id_mqtt}/config"
    try:
        publish_mqtt_message(topic, "INACTIVE", qos=1, retain=True)
    except Exception as mq_err:
        print(f"⚠️ Error MQTT al liberar dispositivo: {mq_err}")
        
    return {
        "status": "ok",
        "message": f"Dispositivo {dev.nombre} liberado y retornado al stock disponible.",
        "dispositivo_id": dispositivo_id
    }

