from typing import Generator, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..MQTT.mqtt_subscriber import publish_mqtt_message
from ..Model.conexion import SessionLocal
from ..Model.model import dispositivos, usuarios, sensores
from ..Model.schemas import DispositivoResponseModel, DispositivoConSensoresResponseModel, DispositivoConfigResponseModel
from .auth_router import get_current_user, get_db

router = APIRouter(prefix="/dispositivos", tags=["Dispositivos"])
legacy_router = APIRouter(prefix="/bomba", tags=["Legacy Bomba"])


@router.get("", response_model=List[DispositivoResponseModel])
def listar_dispositivos(
    id_usuario: int | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Lista los dispositivos del sistema.
    - Si el usuario es un agricultor (no administrador), solo se le permiten ver sus propios dispositivos.
    - Si es administrador, puede ver todos los dispositivos o filtrar por un id_usuario específico.
    """
    # Si el usuario no es admin (asumiendo id_rol != 1 es no administrador)
    if current_user.id_rol != 1:
        id_usuario = current_user.id_usuario

    query = db.query(dispositivos)
    if id_usuario is not None:
        query = query.filter(dispositivos.id_usuario == id_usuario)

    return query.all()


@router.get("/me", response_model=List[DispositivoResponseModel])
def listar_mis_dispositivos(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Retorna la lista de dispositivos asignados únicamente al usuario autenticado actual.
    """
    return db.query(dispositivos).filter(dispositivos.id_usuario == current_user.id_usuario).all()


@router.get("/{dispositivo_id}", response_model=DispositivoResponseModel)
def obtener_detalle_dispositivo(
    dispositivo_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Obtiene los detalles de un dispositivo por su ID.
    - Los agricultores solo pueden ver el detalle si el dispositivo les pertenece.
    - Los administradores pueden ver cualquier dispositivo.
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
    current_user=Depends(get_current_user),
):
    dispositivo = db.query(dispositivos).filter(dispositivos.id_dispositivo == dispositivo_id).first()
    if dispositivo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dispositivo no encontrado")

    # Validación de Seguridad: El agricultor sólo puede controlar sus propios dispositivos
    if current_user.id_rol != 1:
        if dispositivo.id_usuario != current_user.id_usuario:
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
    current_user=Depends(get_current_user),
):
    dispositivo = db.query(dispositivos).filter(dispositivos.id_dispositivo == dispositivo_id).first()
    if dispositivo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dispositivo no encontrado")

    # Validación de Seguridad: El agricultor sólo puede controlar sus propios dispositivos
    if current_user.id_rol != 1:
        if dispositivo.id_usuario != current_user.id_usuario:
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

    # Validación de Seguridad: El agricultor sólo puede controlar sus propios dispositivos
    if current_user.id_rol != 1:
        if dispositivo.id_usuario != current_user.id_usuario:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permiso para modificar este dispositivo",
            )

    # Encontrar todos los dispositivos asignados al propietario de este dispositivo
    owner_id = dispositivo.id_usuario
    user_devices = db.query(dispositivos).filter(dispositivos.id_usuario == owner_id).all()

    # Actualizar todos sus dispositivos asignados
    for dev in user_devices:
        dev.funcionamiento_activo = activo
        db.add(dev)
        
        # Publicar el nuevo estado vía MQTT al dispositivo para sincronización dinámica
        topic = f"yaku/dispositivo/{dev.client_id_mqtt}/config"
        payload = "ACTIVE" if activo else "INACTIVE"
        try:
            publish_mqtt_message(topic, payload, qos=1, retain=True)
        except Exception as mq_err:
            print(f"⚠️ No se pudo notificar al dispositivo {dev.client_id_mqtt} vía MQTT: {mq_err}")

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
    current_user=Depends(get_current_user),
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
    current_user=Depends(get_current_user),
):
    return activar_dispositivo(dispositivo_id=dispositivo_id, db=db, current_user=current_user)


@legacy_router.post("/desactivar/{dispositivo_id}")
def desactivar_bomba_legacy(
    dispositivo_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return desactivar_dispositivo(dispositivo_id=dispositivo_id, db=db, current_user=current_user)


@legacy_router.post("/funcionamiento/{dispositivo_id}")
def establecer_funcionamiento_dispositivo_legacy(
    dispositivo_id: int,
    activo: bool | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
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
    current_user=Depends(get_current_user),
):
    return listar_dispositivos(id_usuario=id_usuario, db=db, current_user=current_user)


@router.get("/usuario/{id_user}", response_model=List[DispositivoConSensoresResponseModel])
def listar_dispositivos_de_usuario(
    id_user: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
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
    
    devs = db.query(dispositivos).filter(dispositivos.id_usuario == id_user).order_by(dispositivos.id_dispositivo).all()
    
    result = []
    for d in devs:
        # Consultar sensores de este dispositivo
        sens = db.query(sensores).filter(sensores.id_dispositivo == d.id_dispositivo).order_by(sensores.id_sensor).all()
        
        from sqlalchemy import inspect
        d_dict = {attr.key: getattr(d, attr.key) for attr in inspect(d).mapper.column_attrs}
        d_dict["sensores"] = [
            {
                "id_sensor": s.id_sensor,
                "id_dispositivo": s.id_dispositivo,
                "nombre": s.nombre,
                "id_tipo_metrica": s.id_tipo_metrica,
                "pin_gpio": s.pin_gpio,
                "estado": s.estado,
                "fecha_registro": s.fecha_registro
            }
            for s in sens
        ]
        result.append(d_dict)
        
    return result


@router.get("/usuario/config/{id_user}", response_model=List[DispositivoConfigResponseModel])
def obtener_config_dispositivos_usuario(
    id_user: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Retorna datos esenciales para la configuración de los archivos .ino de cada dispositivo de un usuario,
    como client_id_mqtt, topic_pub, topic_sub, id_dispositivo y la lista de sensores con sus IDs y nombres.
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

    devs = db.query(dispositivos).filter(dispositivos.id_usuario == id_user).order_by(dispositivos.id_dispositivo).all()

    result = []
    for d in devs:
        # Consultar sensores de este dispositivo
        sens = db.query(sensores).filter(sensores.id_dispositivo == d.id_dispositivo).order_by(sensores.id_sensor).all()

        from sqlalchemy import inspect
        d_dict = {attr.key: getattr(d, attr.key) for attr in inspect(d).mapper.column_attrs}
        d_dict["sensores"] = [
            {
                "id_sensor": s.id_sensor,
                "nombre": s.nombre
            }
            for s in sens
        ]
        result.append(d_dict)

    return result
