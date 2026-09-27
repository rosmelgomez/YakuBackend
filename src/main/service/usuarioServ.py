import logging
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.main.core.security import hash_password
from src.main.dtos.usuarioDto import AdminUserCreateInput
from src.main.model.models import logs_sistema, usuarios
from src.main.repositories import sessionRep as session_repository
from src.main.repositories import usuarioRep as data_repository
from src.main.service.notifications.emailServ import (
    enviar_resultado_solicitud_registro,
)

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
    if data.dni and data.dni.strip():
        dni_norm = data.dni.strip()
        dni_existente = db.query(usuarios).filter(usuarios.dni == dni_norm).first()
        if dni_existente:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="El DNI ya está registrado por otro usuario",
            )

    user = usuarios(
        nombre=data.nombre.strip(),
        apellido=data.apellido.strip() if data.apellido else None,
        correo=normalized_email,
        contrasena=hash_password(data.contrasena),
        telefono=data.telefono.strip() if data.telefono else None,
        zona_horaria=data.zona_horaria.strip() if data.zona_horaria else "America/Lima",
        dni=data.dni.strip() if data.dni else None,
        fecha_nacimiento=data.fecha_nacimiento,
        direccion=data.direccion.strip() if data.direccion else None,
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


def listar_solicitudes_registroServ(db: Session = None, current_user=None):
    """Lista las solicitudes de auto-registro pendientes de revisión."""
    _require_admin(current_user)
    return data_repository.queryListarSolicitudesPendientes(db)


def _revisar_solicitud(
    id_usuario: int,
    aprobar: bool,
    motivo: str | None,
    db: Session,
    current_user,
):
    _require_admin(current_user)
    user = data_repository.queryRevisarSolicitudUser(db, id_usuario)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if user.estado_aprobacion != "pendiente":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La solicitud ya fue revisada",
        )

    motivo_limpio = motivo.strip() if motivo and motivo.strip() else None
    user.estado_aprobacion = "aprobado" if aprobar else "rechazado"
    user.motivo_rechazo = None if aprobar else motivo_limpio
    user.fecha_revision = datetime.now()
    user.revisado_por = current_user.id_usuario
    session_repository.add(
        db,
        logs_sistema(
            id_usuario=current_user.id_usuario,
            accion="aprobacion_registro" if aprobar else "rechazo_registro",
            modulo="Usuarios",
            descripcion=(
                f"La solicitud de registro de {user.correo} fue "
                f"{'aprobada' if aprobar else 'rechazada'} por {current_user.correo}."
                + (f" Motivo: {motivo_limpio}" if not aprobar and motivo_limpio else "")
            ),
        ),
    )
    session_repository.commit(db)

    try:
        enviar_resultado_solicitud_registro(
            destinatario=user.correo,
            nombre=user.nombre,
            aprobado=aprobar,
            motivo=motivo_limpio,
        )
    except Exception as e:
        logger.warning(f"Error al notificar resultado de registro: {e}")

    return {
        "status": "ok",
        "id_usuario": id_usuario,
        "estado_aprobacion": user.estado_aprobacion,
    }


def aprobar_solicitud_registroServ(
    id_usuario: int, db: Session = None, current_user=None
):
    return _revisar_solicitud(id_usuario, True, None, db, current_user)


def rechazar_solicitud_registroServ(
    id_usuario: int, motivo: str | None = None, db: Session = None, current_user=None
):
    return _revisar_solicitud(id_usuario, False, motivo, db, current_user)


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

        # 5. Desactivar asignación de modelos de Machine Learning activos
        data_repository.queryCambiarEstadoUsuarioCultivoModelo(db, id_usuario)

    user.estado = estado
    session_repository.add(
        db,
        logs_sistema(
            id_usuario=current_user.id_usuario,
            accion="cambio_estado_usuario",
            modulo="Usuarios",
            descripcion=f"El usuario {user.correo} fue {'activado' if estado else 'desactivado'} por {current_user.correo}.",
        ),
    )
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
    rol_anterior = user.id_rol
    user.id_rol = id_rol
    session_repository.add(
        db,
        logs_sistema(
            id_usuario=current_user.id_usuario,
            accion="cambio_rol_usuario",
            modulo="Permisos",
            descripcion=f"El rol de {user.correo} cambió de {rol_anterior} a {id_rol}, modificado por {current_user.correo}.",
        ),
    )
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
