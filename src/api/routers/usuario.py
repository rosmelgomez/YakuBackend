from typing import List
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ...db.models import usuarios, dispositivos
from ...schemas.usuario import AdminUserCreateInput, UsuarioAdminResponse, DispositivoResponseModel, AdminDashboardSummaryResponse
from ..dependencies import get_db
from ...core.bff_auth import get_current_user_or_bff
from ...core.security import hash_password

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Administración"])


def _require_admin(current_user) -> None:
    if current_user.id_rol != 1:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permisos de administrador requeridos")


def _is_last_active_admin(db: Session, user: usuarios) -> bool:
    if user.id_rol != 1 or not user.estado:
        return False
    return db.query(usuarios).filter(usuarios.id_rol == 1, usuarios.estado.is_(True)).count() <= 1


@router.post("/usuarios", status_code=status.HTTP_201_CREATED)
def crear_usuario_administrativo(
    data: AdminUserCreateInput,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    _require_admin(current_user)
    normalized_email = str(data.correo).lower()
    if db.query(usuarios).filter(usuarios.correo == normalized_email).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El correo ya esta registrado")
    user = usuarios(
        nombre=data.nombre.strip(),
        apellido=data.apellido.strip() if data.apellido else None,
        correo=normalized_email,
        contrasena=hash_password(data.contrasena),
        telefono=data.telefono,
        id_rol=data.id_rol,
        verificado=True,
        estado=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"success": True, "message": "Usuario creado", "userId": user.id_usuario}


@router.get("/usuarios", response_model=List[UsuarioAdminResponse])
def listar_usuarios_sistema(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """
    Lista todos los usuarios registrados en el sistema.
    Solo accesible por administradores (id_rol = 1).
    """
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador para realizar esta acción."
        )
    return db.query(usuarios).order_by(usuarios.id_usuario).all()


@router.post("/usuarios/{id_usuario}/estado/{estado}")
def cambiar_estado_usuario(
    id_usuario: int,
    estado: bool,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador."
        )
    user = db.query(usuarios).filter(usuarios.id_usuario == id_usuario).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if not estado and _is_last_active_admin(db, user):
        raise HTTPException(status_code=409, detail="No se puede desactivar al ultimo administrador activo")
    
    # Si pasa a desactivado (baja lógica) y estaba activo, liberamos recursos
    if not estado and user.estado:
        from ...db.models import (
            almacenes, asignaciones_iot, cultivos, fuentes_agua,
            programacion_riego, cultivo_modelo, componentes
        )
        from ...tasks.mqtt_subscriber import publish_mqtt_message

        # 1. Buscar primer almacén para retornar stock
        primer_almacen = db.query(almacenes).order_by(almacenes.id.asc()).first()
        almacen_id = primer_almacen.id if primer_almacen else None

        # 2. Obtener y procesar asignaciones activas de IoT
        asigs = db.query(asignaciones_iot).filter(
            asignaciones_iot.id_usuario == id_usuario,
            asignaciones_iot.activo == True
        ).all()
        
        for asig in asigs:
            asig.activo = False
            db.add(asig)
            
            # Liberar dispositivo
            if asig.id_dispositivo:
                dev = db.query(dispositivos).filter(dispositivos.id_dispositivo == asig.id_dispositivo).first()
                if dev:
                    dev.estado = "disponible"
                    dev.en_almacen = True
                    dev.id_almacen = almacen_id
                    db.add(dev)
                    
                    # Notificar apagado/desactivación por MQTT
                    topic = f"yaku/dispositivo/{dev.client_id_mqtt}/config"
                    try:
                        publish_mqtt_message(topic, "INACTIVE", qos=1, retain=True)
                    except Exception as mq_err:
                        logger.info(f"[MQTT Error] Error al liberar dispositivo {dev.id_dispositivo} durante baja de usuario: {mq_err}")
            
            # Liberar componente
            if asig.id_componente:
                comp = db.query(componentes).filter(componentes.id == asig.id_componente).first()
                if comp:
                    comp.estado = "disponible"
                    comp.en_almacen = True
                    comp.id_almacen = almacen_id
                    db.add(comp)

        # 3. Desactivar cultivos activos
        db.query(cultivos).filter(
            cultivos.id_usuario == id_usuario,
            cultivos.estado == 'activo'
        ).update({cultivos.estado: 'inactivo'}, synchronize_session=False)

        # 4. Desactivar fuentes de agua activas
        db.query(fuentes_agua).filter(
            fuentes_agua.id_usuario == id_usuario,
            fuentes_agua.activo == True
        ).update({fuentes_agua.activo: False}, synchronize_session=False)

        # 5. Desactivar horarios de riego programados activos
        db.query(programacion_riego).filter(
            programacion_riego.id_usuario == id_usuario,
            programacion_riego.activo == True
        ).update({programacion_riego.activo: False}, synchronize_session=False)

        # 6. Desactivar asignación de modelos de Machine Learning activos
        db.query(cultivo_modelo).filter(
            cultivo_modelo.id_usuario == id_usuario,
            cultivo_modelo.activo == True
        ).update({cultivo_modelo.activo: False}, synchronize_session=False)

    user.estado = estado
    db.commit()
    return {"status": "ok", "id_usuario": id_usuario, "estado": estado}


@router.post("/usuarios/{id_usuario}/rol/{id_rol}")
def cambiar_rol_usuario(
    id_usuario: int,
    id_rol: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador."
        )
    user = db.query(usuarios).filter(usuarios.id_usuario == id_usuario).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if id_rol not in {1, 2}:
        raise HTTPException(status_code=422, detail="Rol no permitido")
    if id_rol != 1 and _is_last_active_admin(db, user):
        raise HTTPException(status_code=409, detail="No se puede degradar al ultimo administrador activo")
    user.id_rol = id_rol
    db.commit()
    return {"status": "ok", "id_usuario": id_usuario, "id_rol": id_rol}


@router.get("/resumen", response_model=AdminDashboardSummaryResponse)
def admin_resumen_dashboard(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """
    Consolida métricas, logs, predicciones de ML y consumos globales para el administrador.
    Solo accesible por administradores (id_rol = 1).
    """
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador para realizar esta acción."
        )
    from ...services.dashboard import obtener_datos_dashboard_admin
    try:
        return obtener_datos_dashboard_admin(db)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error interno del servidor")





