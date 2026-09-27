"""Configuracion MQTT que se envia a cada ESP32 (topic yaku/dispositivo/<id>/config).

El ESP32 guarda en NVS los ids de asignacion con los que publica telemetria y
solo los pide (config/req) al conectarse al broker. Por eso, cada vez que
cambia el titular o el estado de un dispositivo, el backend publica aqui la
configuracion COMPLETA (retenida): si solo se enviara funcionamiento_activo,
un equipo reasignado seguiria publicando con los ids del agricultor anterior.
"""

import json
import logging

from sqlalchemy.orm import Session

from src.main.core.waterSource import source_firmware_config
from src.main.model.models import dispositivos, fuentes_agua
from src.main.repositories import dispositivoRep

logger = logging.getLogger(__name__)

# Claves de asignacion que leen los firmwares. Las que no tengan asignacion
# vigente se envian en 0: el firmware del colector conserva el id anterior si
# la clave falta (asig["X"] | anterior), y con 0 el backend descarta la lectura.
CODIGOS_FIRMWARE = ("HUM_SUELO", "HUM_AMB", "TEMP_AMB", "TEMP_SUELO", "NIVEL_AGUA", "CAUDAL")

# Estados de stock (dispositivoServ): el equipo no tiene titular.
ESTADOS_SIN_TITULAR = ("disponible", "Retirado", "reparacion")


def asignacion_principal(vigentes: list):
    """Asignacion que representa al dispositivo: la activa mas reciente, o la ultima."""
    activas = [a for a in vigentes if a.activo]
    if activas:
        return activas[-1]
    return vigentes[-1] if vigentes else None


def _fuente_de(db: Session, asig, vigentes: list):
    if asig.id_fuente_agua is not None:
        fuente = db.query(fuentes_agua).filter(fuentes_agua.id == asig.id_fuente_agua).first()
        if fuente is not None:
            return fuente
    # Otra asignacion del mismo titular con fuente (activas primero)
    for otra in sorted(vigentes, key=lambda a: not a.activo):
        if otra.id_fuente_agua is not None:
            fuente = db.query(fuentes_agua).filter(fuentes_agua.id == otra.id_fuente_agua).first()
            if fuente is not None:
                return fuente
    return asig.cultivo.fuente_agua if asig.cultivo is not None else None


def _mapa_asignaciones(device: dispositivos, vigentes: list) -> dict:
    # Activas y mas recientes al final: ante dos filas con la misma metrica, gana esa.
    ordenadas = sorted(vigentes, key=lambda a: (bool(a.activo), a.id))
    mapa = {
        item.tipo_metrica.codigo: item.id
        for item in ordenadas
        if item.tipo_metrica is not None
    }
    # Solo el actuador de tanque (proximidad) necesita NIVEL_AGUA; antes se le
    # agregaba tambien al colector de sensores (metodo NULL), que no la usa.
    if device.metodo_medicion == "proximidad" and "NIVEL_AGUA" not in mapa and ordenadas:
        actuador = next(
            (
                item
                for item in reversed(ordenadas)
                if item.componente
                and item.componente.modelo
                and item.componente.modelo.categoria == "actuador"
            ),
            None,
        )
        mapa["NIVEL_AGUA"] = (actuador or ordenadas[-1]).id
    for codigo in CODIGOS_FIRMWARE:
        mapa.setdefault(codigo, 0)
    return mapa


def construir_config_dispositivo(db: Session, device: dispositivos) -> dict:
    """Configuracion completa para el titular actual del dispositivo."""
    if device.estado in ESTADOS_SIN_TITULAR:
        # En stock: apagado y sin ids (las filas viejas son solo historial).
        vigentes = []
    else:
        vigentes = dispositivoRep.queryAsignacionesVigentesDispositivo(db, device.id_dispositivo)
    asig = asignacion_principal(vigentes)

    fuente = _fuente_de(db, asig, vigentes) if asig is not None else None
    litros_acumulados = 0.0
    if asig is not None:
        from src.main.service.irrigationServ import obtener_litros_acumulados_asignacion

        litros_acumulados = obtener_litros_acumulados_asignacion(db, asig.id)

    mapa = _mapa_asignaciones(device, vigentes)
    payload = {
        "metodo_medicion": device.metodo_medicion,
        **source_firmware_config(fuente),
        "funcionamiento_activo": bool(asig.activo) if asig is not None else False,
        "modo": "predictivo",  # ML predictivo como unico modo
        "litros_acumulados": round(float(litros_acumulados), 2),
        "topic_pub": device.topic_pub,
        "topic_sub": device.topic_sub or "yaku/riego/comando",
        "asignaciones": mapa,
    }
    if device.metodo_medicion == "flujometro":
        # El firmware de flujo solo toma un id del mapa si aun no tiene uno;
        # id_asignacion en la raiz lo reemplaza siempre.
        payload["id_asignacion"] = mapa["CAUDAL"] or mapa["NIVEL_AGUA"]
    return payload


def publicar_config_dispositivo(db: Session, device: dispositivos) -> None:
    """Publica (retenida) la configuracion completa. Nunca interrumpe la operacion."""
    if device is None or not device.client_id_mqtt:
        return
    try:
        payload = construir_config_dispositivo(db, device)
        from src.main.tasks.mqttSubscriberTask import publish_mqtt_message

        publish_mqtt_message(
            f"yaku/dispositivo/{device.client_id_mqtt}/config",
            json.dumps(payload),
            qos=1,
            retain=True,
        )
    except Exception as exc:
        logger.warning(
            "[MQTT] No se pudo publicar la configuracion de %s: %s",
            device.client_id_mqtt,
            exc,
        )
