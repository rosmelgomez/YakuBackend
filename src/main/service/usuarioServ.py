import logging

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.main.core.security import hash_password
from src.main.dtos.usuarioDto import AdminUserCreateInput
from src.main.model.models import usuarios
from src.main.repositories import sessionRep as session_repository
from src.main.repositories import usuarioRep as data_repository

logger = logging.getLogger(__name__)


def _require_admin(current_user) -> None:
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permisos de administrador requeridos",
        )


def _is_last_active_admin(db: Session, user: usuarios) -> bool:
    if user.id_rol != 1 or not user.estado:
        return False
    return data_repository.queryIsLastActiveAdminUsuarios(db) <= 1


def crear_usuario_administrativoServ(
    data: AdminUserCreateInput, db: Session = None, current_user=None
):
    _require_admin(current_user)
    normalized_email = str(data.correo).strip().lower()
    if data_repository.queryCrearUsuarioAdministrativoUsuarios(db, normalized_email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="El correo ya esta registrado"
        )
    user = usuarios(
        nombre=data.nombre.strip(),
        apellido=data.apellido.strip() if data.apellido else None,
        correo=normalized_email,
        contrasena=hash_password(data.contrasena),
        telefono=data.telefono.strip() if data.telefono else None,
        id_rol=data.id_rol,
        verificado=True,
        estado=True,
    )
    session_repository.add(db, user)
    session_repository.commit(db)
    session_repository.refresh(db, user)
    return {"success": True, "message": "Usuario creado", "userId": user.id_usuario}


def listar_usuarios_sistemaServ(db: Session = None, current_user=None):
    """
    Lista todos los usuarios registrados en el sistema.
    Solo accesible por administradores (id_rol = 1).
    """
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador para realizar esta acción.",
        )
    return data_repository.queryListarUsuariosSistemaResultado(db)


def cambiar_estado_usuarioServ(
    id_usuario: int, estado: bool, db: Session = None, current_user=None
):
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador.",
        )
    user = data_repository.queryCambiarEstadoUsuarioUser(db, id_usuario)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if not estado and _is_last_active_admin(db, user):
        raise HTTPException(
            status_code=409,
            detail="No se puede desactivar al ultimo administrador activo",
        )

    # Si pasa a desactivado (baja lógica) y estaba activo, liberamos recursos
    if not estado and user.estado:
        from src.main.tasks.mqttSubscriberTask import publish_mqtt_message

        # 1. Buscar primer almacén para retornar stock
        primer_almacen = data_repository.queryCambiarEstadoUsuarioPrimerAlmacen(db)
        almacen_id = primer_almacen.id if primer_almacen else None

        # 2. Obtener y procesar asignaciones activas de IoT
        asigs = data_repository.queryCambiarEstadoUsuarioAsigs(db, id_usuario)

        for asig in asigs:
            asig.activo = False
            session_repository.add(db, asig)

            # Liberar dispositivo
            if asig.id_dispositivo:
                dev = data_repository.queryCambiarEstadoUsuarioDev(db, asig)
                if dev:
                    dev.estado = "disponible"
                    dev.en_almacen = True
                    dev.id_almacen = almacen_id
                    session_repository.add(db, dev)

                    # Notificar apagado/desactivación por MQTT
                    topic = f"yaku/dispositivo/{dev.client_id_mqtt}/config"
                    try:
                        publish_mqtt_message(topic, "INACTIVE", qos=1, retain=True)
                    except Exception as mq_err:
                        logger.info(
                            f"[MQTT Error] Error al liberar dispositivo {dev.id_dispositivo} durante baja de usuario: {mq_err}"
                        )

            # Liberar componente
            if asig.id_componente:
                comp = data_repository.queryCambiarEstadoUsuarioComp(db, asig)
                if comp:
                    comp.estado = "disponible"
                    comp.en_almacen = True
                    comp.id_almacen = almacen_id
                    session_repository.add(db, comp)

        # 3. Desactivar cultivos activos
        data_repository.queryCambiarEstadoUsuarioCultivos(db, id_usuario)

        # 4. Desactivar fuentes de agua activas
        data_repository.queryCambiarEstadoUsuarioFuentesAgua(db, id_usuario)

        # 5. Desactivar horarios de riego programados activos
        data_repository.queryCambiarEstadoUsuarioProgramacionRiego(db, id_usuario)

        # 6. Desactivar asignación de modelos de Machine Learning activos
        data_repository.queryCambiarEstadoUsuarioCultivoModelo(db, id_usuario)

    user.estado = estado
    session_repository.commit(db)
    return {"status": "ok", "id_usuario": id_usuario, "estado": estado}


def cambiar_rol_usuarioServ(
    id_usuario: int, id_rol: int, db: Session = None, current_user=None
):
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador.",
        )
    user = data_repository.queryCambiarRolUsuarioUser(db, id_usuario)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if id_rol not in {1, 2}:
        raise HTTPException(status_code=422, detail="Rol no permitido")
    if id_rol != 1 and _is_last_active_admin(db, user):
        raise HTTPException(
            status_code=409,
            detail="No se puede degradar al ultimo administrador activo",
        )
    user.id_rol = id_rol
    session_repository.commit(db)
    return {"status": "ok", "id_usuario": id_usuario, "id_rol": id_rol}


def admin_resumen_dashboardServ(db: Session = None, current_user=None):
    """
    Consolida métricas, logs, predicciones de ML y consumos globales para el administrador.
    Solo accesible por administradores (id_rol = 1).
    """
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador para realizar esta acción.",
        )
    from src.main.service.dashboardServ import obtener_datos_dashboard_admin

    try:
        return obtener_datos_dashboard_admin(db, current_user.id_usuario)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error interno del servidor")
