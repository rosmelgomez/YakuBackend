"""Credenciales MQTT por dispositivo ESP32.

Cada equipo se conecta al broker con su propio usuario: si uno se pierde o se
da de baja, se revoca solo esa credencial en el broker. El registro aqui debe
coincidir con la credencial creada en el broker; el panel de firmware la envia
al ESP32 al provisionarlo, sin que el administrador la escriba a mano.
"""

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.main.core.secretCipher import SecretoNoDisponible, cifrar, descifrar
from src.main.dtos.mqttDto import CredencialDispositivoGuardar
from src.main.model.models import credenciales_mqtt_dispositivo
from src.main.repositories import mqttCredencialRep as data_repository
from src.main.repositories import sessionRep as session_repository


def _require_admin(current_user) -> None:
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Las credenciales MQTT solo puede gestionarlas un administrador.",
        )


def _ahora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _respuesta(device, credencial) -> dict:
    return {
        "id_dispositivo": device.id_dispositivo,
        "nombre": device.nombre,
        "client_id_mqtt": device.client_id_mqtt,
        "tipo": device.tipo.nombre if device.tipo else None,
        "estado": device.estado,
        "username": credencial.username if credencial else None,
        "tiene_credencial": credencial is not None,
        "fecha_actualizacion": credencial.fecha_actualizacion if credencial else None,
    }


def _cifrar_o_error(password: str) -> str:
    try:
        return cifrar(password)
    except SecretoNoDisponible as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def listar_credencialesServ(db: Session = None, current_user=None) -> list[dict]:
    _require_admin(current_user)
    return [
        _respuesta(device, credencial)
        for device, credencial in data_repository.queryListarDispositivosConCredencial(db)
    ]


def guardar_credencialServ(
    id_dispositivo: int,
    payload: CredencialDispositivoGuardar,
    db: Session = None,
    current_user=None,
) -> dict:
    """Registra la credencial del dispositivo o la modifica si ya existe."""
    _require_admin(current_user)
    device = data_repository.queryDispositivo(db, id_dispositivo)
    if device is None:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")

    username = payload.username.strip()
    otra = data_repository.queryCredencialPorUsername(db, username)
    if otra is not None and otra.id_dispositivo != id_dispositivo:
        raise HTTPException(
            status_code=409,
            detail=f"El usuario MQTT '{username}' ya está asignado a otro dispositivo.",
        )

    credencial = data_repository.queryCredencialPorDispositivo(db, id_dispositivo)
    if credencial is None:
        if not payload.password:
            raise HTTPException(
                status_code=422,
                detail="La contraseña es obligatoria al registrar la credencial.",
            )
        credencial = credenciales_mqtt_dispositivo(id_dispositivo=id_dispositivo)

    credencial.username = username
    if payload.password:
        credencial.password_cifrada = _cifrar_o_error(payload.password)
    credencial.actualizado_por = current_user.id_usuario
    credencial.fecha_actualizacion = _ahora()
    session_repository.add(db, credencial)
    session_repository.commit(db)
    session_repository.refresh(db, credencial)
    return _respuesta(device, credencial)


def eliminar_credencialServ(id_dispositivo: int, db: Session = None, current_user=None) -> None:
    _require_admin(current_user)
    credencial = data_repository.queryCredencialPorDispositivo(db, id_dispositivo)
    if credencial is None:
        raise HTTPException(
            status_code=404, detail="El dispositivo no tiene credencial MQTT registrada."
        )
    session_repository.delete(db, credencial)
    session_repository.commit(db)


def credencial_para_provisionamiento(db: Session, id_dispositivo: int) -> dict:
    """Usuario y clave en claro para enviarlos al ESP32. Solo lo usa el
    provisionamiento de firmware (endpoint exclusivo de administradores)."""
    credencial = data_repository.queryCredencialPorDispositivo(db, id_dispositivo)
    if credencial is None:
        raise HTTPException(
            status_code=409,
            detail="El dispositivo no tiene credencial MQTT registrada. Regístrela en "
            "Configuración MQTT > Credenciales de dispositivos antes de aprovisionarlo.",
        )
    try:
        password = descifrar(credencial.password_cifrada)
    except SecretoNoDisponible as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"username": credencial.username, "password": password}
