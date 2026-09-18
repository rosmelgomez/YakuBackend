"""Diagnóstico físico de sensores (HU-11).

No existe en el firmware ESP32 actual ningún circuito de medición de voltaje/batería,
por lo que el diagnóstico se calcula por software a partir de: conectividad del
dispositivo (último ping), y la proporción de lecturas inválidas en la ventana más
reciente de la métrica asignada.
"""

from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.main.dtos.dispositivoDto import DiagnosticoSensorResponse
from src.main.model.models import (
    asignaciones_iot,
    humedad_ambiente,
    humedad_suelo,
    temperatura_ambiente,
    temperatura_suelo,
)
from src.main.service.deviceHealthServ import (
    DEVICE_OFFLINE_TIMEOUT_SECONDS,
    utc_now_naive,
)

VENTANA_LECTURAS = 20

METRICA_TABLA = {
    "HUM_SUELO": humedad_suelo,
    "TEMP_SUELO": temperatura_suelo,
    "TEMP_AMB": temperatura_ambiente,
    "HUM_AMB": humedad_ambiente,
}


def diagnosticar_sensorServ(
    id_asignacion: int, db: Session = None, current_user=None
) -> DiagnosticoSensorResponse:
    asig = (
        db.query(asignaciones_iot)
        .filter(asignaciones_iot.id == id_asignacion)
        .first()
    )
    if asig is None:
        raise HTTPException(status_code=404, detail="Asignación de sensor no encontrada")

    if current_user.id_rol != 1 and asig.id_usuario != current_user.id_usuario:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para diagnosticar este sensor.",
        )

    codigo_metrica = asig.tipo_metrica.codigo if asig.tipo_metrica else None
    tabla = METRICA_TABLA.get(codigo_metrica)

    dispositivo = asig.dispositivo
    now = utc_now_naive()

    if not asig.activo:
        return DiagnosticoSensorResponse(
            id_asignacion=id_asignacion,
            estado="Falla",
            motivo="La asignación está inactiva (el dispositivo fue desactivado por falta de respuesta o manualmente).",
            ultima_lectura_fecha=None,
            porcentaje_lecturas_invalidas=None,
        )

    if dispositivo is None or dispositivo.ultimo_ping is None:
        return DiagnosticoSensorResponse(
            id_asignacion=id_asignacion,
            estado="Falla",
            motivo="El dispositivo nunca ha enviado datos (sin ping registrado).",
        )

    segundos_sin_ping = (now - dispositivo.ultimo_ping).total_seconds()
    if segundos_sin_ping > DEVICE_OFFLINE_TIMEOUT_SECONDS:
        return DiagnosticoSensorResponse(
            id_asignacion=id_asignacion,
            estado="Falla",
            motivo=f"El dispositivo no responde desde hace {int(segundos_sin_ping)}s (umbral: {DEVICE_OFFLINE_TIMEOUT_SECONDS}s).",
            ultima_lectura_fecha=dispositivo.ultimo_ping,
        )

    if tabla is None:
        return DiagnosticoSensorResponse(
            id_asignacion=id_asignacion,
            estado="Ok",
            motivo="Dispositivo conectado. No se pudo evaluar validez de lecturas (métrica no reconocida).",
            ultima_lectura_fecha=dispositivo.ultimo_ping,
        )

    lecturas = (
        db.query(tabla)
        .filter(tabla.id_asignacion == id_asignacion)
        .order_by(tabla.fecha.desc())
        .limit(VENTANA_LECTURAS)
        .all()
    )

    if not lecturas:
        return DiagnosticoSensorResponse(
            id_asignacion=id_asignacion,
            estado="Falla",
            motivo="El dispositivo está conectado pero no existen lecturas registradas para este sensor.",
            ultima_lectura_fecha=dispositivo.ultimo_ping,
        )

    invalidas = sum(1 for lectura in lecturas if lectura.valido is False)
    porcentaje_invalidas = round((invalidas / len(lecturas)) * 100, 1)
    ultima_lectura_fecha = lecturas[0].fecha

    if porcentaje_invalidas >= 50:
        return DiagnosticoSensorResponse(
            id_asignacion=id_asignacion,
            estado="Falla",
            motivo=f"{porcentaje_invalidas}% de las últimas {len(lecturas)} lecturas fueron marcadas como inválidas.",
            ultima_lectura_fecha=ultima_lectura_fecha,
            porcentaje_lecturas_invalidas=porcentaje_invalidas,
        )

    if now - ultima_lectura_fecha > timedelta(seconds=DEVICE_OFFLINE_TIMEOUT_SECONDS * 3):
        return DiagnosticoSensorResponse(
            id_asignacion=id_asignacion,
            estado="Falla",
            motivo="El dispositivo está conectado pero este sensor dejó de enviar lecturas recientemente.",
            ultima_lectura_fecha=ultima_lectura_fecha,
            porcentaje_lecturas_invalidas=porcentaje_invalidas,
        )

    return DiagnosticoSensorResponse(
        id_asignacion=id_asignacion,
        estado="Ok",
        motivo=f"Dispositivo conectado y {100 - porcentaje_invalidas}% de las últimas {len(lecturas)} lecturas son válidas.",
        ultima_lectura_fecha=ultima_lectura_fecha,
        porcentaje_lecturas_invalidas=porcentaje_invalidas,
    )
