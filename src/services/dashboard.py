from datetime import datetime, timedelta
from collections import defaultdict
from typing import List
import pytz
from sqlalchemy.orm import Session

from ..db.models import (
    cultivos,
    plantas,
    umbrales_planta,
    fuentes_agua,
    configuracion_control,
    configuracion_umbrales,
    asignaciones_iot,
    dispositivos,
    tipos_dispositivo,
    componentes,
    tipos_componente,
    tipos_metrica,
    usuarios,
    humedad_suelo,
    humedad_ambiente,
    temperatura_suelo,
    temperatura_ambiente,
    telemetria_tanque,
    riego,
    alertas,
    tipos_alerta,
    cultivo_modelo,
    predicciones_ml
)


DEFAULT_UMBRALES_METRICA = {
    "HUM_SUELO": {"min": 35.0, "max": 75.0},
    "HUM_AMB": {"min": 40.0, "max": 80.0},
    "TEMP_AMB": {"min": 18.0, "max": 30.0},
    "TEMP_SUELO": {"min": 18.0, "max": 26.0},
}


DEFAULT_TIMEZONE = "America/Lima"


def _get_timezone(zona_horaria: str | None):
    try:
        return pytz.timezone(zona_horaria or DEFAULT_TIMEZONE)
    except pytz.UnknownTimeZoneError:
        return pytz.timezone(DEFAULT_TIMEZONE)


def _to_timezone(dt: datetime | None, tz) -> datetime | None:
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = pytz.utc.localize(dt)
    else:
        dt = dt.astimezone(pytz.utc)
    return dt.astimezone(tz)


def _to_timezone_iso(dt: datetime | None, tz) -> str | None:
    local_dt = _to_timezone(dt, tz)
    return local_dt.isoformat() if local_dt else None


def _local_naive_to_utc_naive(dt: datetime, tz) -> datetime:
    return tz.localize(dt).astimezone(pytz.utc).replace(tzinfo=None)


def _local_naive_to_timezone_iso(dt: datetime | None, tz) -> str | None:
    return tz.localize(dt).isoformat() if dt else None


def _resolver_umbral(tipo_metrica, umbrales_planta_lista, umbrales_config_lista):
    if not tipo_metrica:
        return None

    fallback = DEFAULT_UMBRALES_METRICA.get(tipo_metrica.codigo)
    umbral_planta = None
    for u in umbrales_planta_lista:
        if u.id_tipo_metrica == tipo_metrica.id:
            umbral_planta = {
                "min": float(u.valor_minimo) if u.valor_minimo is not None else None,
                "max": float(u.valor_maximo) if u.valor_maximo is not None else None
            }
            break

    for u in umbrales_config_lista:
        if u.id_tipo_metrica == tipo_metrica.id:
            min_val = float(u.valor_minimo) if u.valor_minimo is not None else None
            max_val = float(u.valor_maximo) if u.valor_maximo is not None else None
            if fallback and min_val == 10.0 and max_val == 90.0:
                return umbral_planta or fallback
            return {
                "min": min_val,
                "max": max_val
            }

    if umbral_planta:
        return umbral_planta

    return fallback


def _valor_lectura(lectura, tipo_metrica):
    codigo = tipo_metrica.codigo if tipo_metrica else ""
    if codigo in {"HUM_SUELO", "HUM_AMB"} and getattr(lectura, "porcentaje", None) is not None:
        return float(lectura.porcentaje)
    if codigo in {"TEMP_SUELO", "TEMP_AMB"} and getattr(lectura, "temperatura", None) is not None:
        return float(lectura.temperatura)
    return float(lectura.valor) if lectura.valor is not None else 0.0


def mapear_sensor_ultimo(asignacion, lecturas, tipo_comp, tipo_metrica, umbrales_planta_lista, umbrales_config_lista, tz):
    if not asignacion or not lecturas:
        return None
    lectura = lecturas[0]

    umbral = _resolver_umbral(tipo_metrica, umbrales_planta_lista, umbrales_config_lista)
                
    porcentaje = float(lectura.porcentaje) if getattr(lectura, 'porcentaje', None) is not None else None
    ema = float(lectura.ema) if getattr(lectura, 'ema', None) is not None else None
    
    return {
        "modelo": tipo_comp.nombre_modelo if tipo_comp else "Desconocido",
        "metrica": tipo_metrica.nombre if tipo_metrica else "Sensor",
        "unidad": tipo_metrica.unidad if tipo_metrica else "",
        "valor": _valor_lectura(lectura, tipo_metrica),
        "porcentaje": porcentaje,
        "ema": ema,
        "fecha": _to_timezone_iso(lectura.fecha, tz),
        "umbral": umbral
    }


def mapear_historial(asignacion, lecturas, tz):
    if not asignacion or not lecturas:
        return []
    return [
        {
            "fecha": _to_timezone_iso(l.fecha, tz),
            "valor": float(l.valor) if l.valor is not None else 0.0
        }
        for l in reversed(lecturas)
    ]


def _group_by_assignment(rows):
    grouped = defaultdict(list)
    for row in rows:
        grouped[row.id_asignacion].append(row)
    return grouped


def _latest_per_assignment(rows):
    latest = {}
    for row in rows:
        current = latest.get(row.id_asignacion)
        if current is None or (row.fecha and current.fecha and row.fecha > current.fecha):
            latest[row.id_asignacion] = row
    return latest


def _component_context_maps(db: Session, asigs: list):
    component_ids = {a.id_componente for a in asigs if a.id_componente}
    comps = {
        c.id: c
        for c in db.query(componentes).filter(componentes.id.in_(component_ids)).all()
    } if component_ids else {}

    tipo_component_ids = {c.id_tipo_componente for c in comps.values() if c.id_tipo_componente}
    tipo_comps = {
        t.id: t
        for t in db.query(tipos_componente).filter(tipos_componente.id.in_(tipo_component_ids)).all()
    } if tipo_component_ids else {}

    tipo_metrica_ids = {t.id_tipo_metrica for t in tipo_comps.values() if t.id_tipo_metrica}
    tipo_metricas = {
        m.id: m
        for m in db.query(tipos_metrica).filter(tipos_metrica.id.in_(tipo_metrica_ids)).all()
    } if tipo_metrica_ids else {}

    return comps, tipo_comps, tipo_metricas


def obtener_datos_dashboard(db: Session, userId: int) -> List[dict]:
    usuario = db.query(usuarios).filter(usuarios.id_usuario == userId).first()
    dashboard_tz = _get_timezone(usuario.zona_horaria if usuario else None)
    fechaActual = datetime.now(dashboard_tz).replace(tzinfo=None)
    
    fechaLimite7d = _local_naive_to_utc_naive(fechaActual - timedelta(days=7), dashboard_tz)
    fechaLimiteConsumo = (fechaActual - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
    fechaLimiteConsumoUtc = _local_naive_to_utc_naive(fechaLimiteConsumo, dashboard_tz)
    
    # 1. Obtener cultivos activos del usuario
    db_cultivos = db.query(cultivos).filter(
        cultivos.id_usuario == userId,
        cultivos.estado == "activo"
    ).all()
    if not db_cultivos:
        return []

    cultivo_ids = [cult.id_cultivo for cult in db_cultivos]
    planta_ids = {cult.id_planta for cult in db_cultivos if cult.id_planta}
    fuente_ids = {cult.id_fuente_agua for cult in db_cultivos if cult.id_fuente_agua}

    plantas_map = {
        p.id_planta: p
        for p in db.query(plantas).filter(plantas.id_planta.in_(planta_ids)).all()
    } if planta_ids else {}
    fuentes_map = {
        f.id: f
        for f in db.query(fuentes_agua).filter(fuentes_agua.id.in_(fuente_ids)).all()
    } if fuente_ids else {}
    umbrales_planta_map = defaultdict(list)
    if planta_ids:
        for u in db.query(umbrales_planta).filter(umbrales_planta.id_planta.in_(planta_ids)).all():
            umbrales_planta_map[u.id_planta].append(u)
    config_control_map = defaultdict(list)
    for c in db.query(configuracion_control).filter(
        configuracion_control.id_usuario == userId,
        configuracion_control.id_cultivo.in_(cultivo_ids),
    ).all():
        config_control_map[c.id_cultivo].append(c)
    umbrales_config_map = defaultdict(list)
    for u in db.query(configuracion_umbrales).filter(
        configuracion_umbrales.id_usuario == userId,
        configuracion_umbrales.id_cultivo.in_(cultivo_ids),
    ).all():
        umbrales_config_map[u.id_cultivo].append(u)

    asigs_all = db.query(asignaciones_iot).filter(
        asignaciones_iot.id_usuario == userId,
        asignaciones_iot.id_cultivo.in_(cultivo_ids),
    ).all()
    asigs_by_cultivo = defaultdict(list)
    for asig in asigs_all:
        asigs_by_cultivo[asig.id_cultivo].append(asig)

    asig_ids = [a.id for a in asigs_all]
    device_ids = {a.id_dispositivo for a in asigs_all if a.id_dispositivo}
    devices_map = {
        d.id_dispositivo: d
        for d in db.query(dispositivos).filter(dispositivos.id_dispositivo.in_(device_ids)).all()
    } if device_ids else {}
    comps_map, tipo_comps_map, tipo_metricas_map = _component_context_maps(db, asigs_all)

    hs_by_asig = ha_by_asig = ts_by_asig = ta_by_asig = defaultdict(list)
    tanque_latest_by_asig = {}
    riegos_by_asig = defaultdict(list)
    if asig_ids:
        hs_by_asig = _group_by_assignment(db.query(humedad_suelo).filter(
            humedad_suelo.id_asignacion.in_(asig_ids),
            humedad_suelo.valido == True,
            humedad_suelo.fecha >= fechaLimite7d,
        ).order_by(humedad_suelo.fecha.desc()).all())
        ha_by_asig = _group_by_assignment(db.query(humedad_ambiente).filter(
            humedad_ambiente.id_asignacion.in_(asig_ids),
            humedad_ambiente.valido == True,
            humedad_ambiente.fecha >= fechaLimite7d,
        ).order_by(humedad_ambiente.fecha.desc()).all())
        ts_by_asig = _group_by_assignment(db.query(temperatura_suelo).filter(
            temperatura_suelo.id_asignacion.in_(asig_ids),
            temperatura_suelo.valido == True,
            temperatura_suelo.fecha >= fechaLimite7d,
        ).order_by(temperatura_suelo.fecha.desc()).all())
        ta_by_asig = _group_by_assignment(db.query(temperatura_ambiente).filter(
            temperatura_ambiente.id_asignacion.in_(asig_ids),
            temperatura_ambiente.valido == True,
            temperatura_ambiente.fecha >= fechaLimite7d,
        ).order_by(temperatura_ambiente.fecha.desc()).all())
        tanque_latest_by_asig = _latest_per_assignment(db.query(telemetria_tanque).filter(
            telemetria_tanque.id_asignacion.in_(asig_ids),
        ).order_by(telemetria_tanque.fecha.desc()).all())
        riegos_by_asig = _group_by_assignment(db.query(riego).filter(
            riego.id_asignacion.in_(asig_ids),
            riego.fecha >= fechaLimiteConsumoUtc,
            riego.estado == True,
        ).all())

    metricas_por_codigo = {
        m.codigo: m
        for m in db.query(tipos_metrica).filter(
            tipos_metrica.codigo.in_(("HUM_SUELO", "HUM_AMB", "TEMP_AMB", "TEMP_SUELO"))
        ).all()
    }
    
    result = []
    for cult in db_cultivos:
        # Relaciones del cultivo
        planta = plantas_map.get(cult.id_planta)
        umbrales = umbrales_planta_map.get(cult.id_planta, []) if planta else []
        fuente = fuentes_map.get(cult.id_fuente_agua)
        config_ctrl = config_control_map.get(cult.id_cultivo, [])
        umbrales_c = umbrales_config_map.get(cult.id_cultivo, [])
        asigs = asigs_by_cultivo.get(cult.id_cultivo, [])
        
        # Mapear consumo semanal de 7 dias
        diasSemana = ['Dom', 'Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb']
        consumoSemanalMap = {}
        for i in range(6, -1, -1):
            d = fechaActual - timedelta(days=i)
            dateKey = d.strftime("%Y-%m-%d")
            label = "Hoy" if i == 0 else diasSemana[(d.weekday() + 1) % 7] # Ajustar a Domingo=0 para paridad
            consumoSemanalMap[dateKey] = { "label": label, "valor": 0.0 }
            
        riegosHoy = 0
        litrosHoy = 0.0
        ultimoRiegoFecha = None
        inicioDeHoy = fechaActual.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Telemetría
        asigHS = None
        asigHA = None
        asigTS = None
        asigTA = None
        asigTanque = None
        
        lecturasHS = []
        lecturasHA = []
        lecturasTS = []
        lecturasTA = []
        ultimaTelemetriaTanque = None
        
        compHS = None
        compHA = None
        compTS = None
        compTA = None
        compTanque = None
        
        metricHS = None
        metricHA = None
        metricTS = None
        metricTA = None
        
        dispositivosMap = {}
        
        for asig in asigs:
            # Dispositivo
            dev = devices_map.get(asig.id_dispositivo)
            if dev:
                dispositivosMap[dev.id_dispositivo] = {
                    "id": dev.id_dispositivo,
                    "nombre": dev.nombre,
                    "estado": dev.estado if dev.estado else "offline",
                    "funcionamientoActivo": any(a.activo for a in asigs if a.id_dispositivo == dev.id_dispositivo)
                }
                
            # Componente
            comp = comps_map.get(asig.id_componente) if asig.id_componente else None
            tipo_comp = tipo_comps_map.get(comp.id_tipo_componente) if comp else None
            tipo_metric = tipo_metricas_map.get(tipo_comp.id_tipo_metrica) if (tipo_comp and tipo_comp.id_tipo_metrica) else None
            
            # Consultar lecturas de telemetría de 7 días
            hs_list = hs_by_asig.get(asig.id, [])
            if hs_list:
                if not lecturasHS or hs_list[0].fecha > lecturasHS[0].fecha:
                    asigHS, lecturasHS, compHS, metricHS = asig, hs_list, tipo_comp, tipo_metric
                
            ha_list = ha_by_asig.get(asig.id, [])
            if ha_list:
                if not lecturasHA or ha_list[0].fecha > lecturasHA[0].fecha:
                    asigHA, lecturasHA, compHA, metricHA = asig, ha_list, tipo_comp, tipo_metric
                
            ts_list = ts_by_asig.get(asig.id, [])
            if ts_list:
                if not lecturasTS or ts_list[0].fecha > lecturasTS[0].fecha:
                    asigTS, lecturasTS, compTS, metricTS = asig, ts_list, tipo_comp, tipo_metric
                
            ta_list = ta_by_asig.get(asig.id, [])
            if ta_list:
                if not lecturasTA or ta_list[0].fecha > lecturasTA[0].fecha:
                    asigTA, lecturasTA, compTA, metricTA = asig, ta_list, tipo_comp, tipo_metric
                
            # Telemetría Tanque
            tt_latest = tanque_latest_by_asig.get(asig.id)
            if tt_latest:
                if not ultimaTelemetriaTanque or tt_latest.fecha > ultimaTelemetriaTanque.fecha:
                    asigTanque, ultimaTelemetriaTanque, compTanque = asig, tt_latest, tipo_comp
                
            # Consultar consumos de riego
            riego_list = riegos_by_asig.get(asig.id, [])
            for r in riego_list:
                fecha_r_local = _to_timezone(r.fecha, dashboard_tz).replace(tzinfo=None) if r.fecha else None
                if fecha_r_local:
                    date_key = fecha_r_local.strftime("%Y-%m-%d")
                    if date_key in consumoSemanalMap and r.cantidad_agua_litros is not None:
                        consumoSemanalMap[date_key]["valor"] += float(r.cantidad_agua_litros)
                        
                    if ultimoRiegoFecha is None or fecha_r_local > ultimoRiegoFecha:
                        ultimoRiegoFecha = fecha_r_local
                        
                    if fecha_r_local >= inicioDeHoy:
                        riegosHoy += 1
                        if r.cantidad_agua_litros is not None:
                            litrosHoy += float(r.cantidad_agua_litros)
                            
        # Finalizar mapeado semanal
        consumoSemanal = [
            { "label": d["label"], "valor": round(d["valor"], 1) }
            for d in consumoSemanalMap.values()
        ]
        
        # Mapear tanque
        tanqueData = None
        if asigTanque or fuente:
            capacidad_maxima = float(fuente.capacidad_litros) if (fuente and fuente.capacidad_litros is not None) else 0.0
            porcentaje_nivel = float(ultimaTelemetriaTanque.porcentaje_nivel) if (ultimaTelemetriaTanque and ultimaTelemetriaTanque.porcentaje_nivel is not None) else 0.0
            litros_actuales = (porcentaje_nivel / 100.0) * capacidad_maxima
            timeout_min = (config_ctrl[0].duracion_riego_max_seg // 60) if (config_ctrl and config_ctrl[0].duracion_riego_max_seg is not None) else 10
            
            # DETERMINAR SI EL DISPOSITIVO DEL TANQUE ESTÁ ACTIVO
            disp_tanque_act = False
            if asigTanque:
                disp_tanque_act = any(a.activo for a in asigs if a.id_dispositivo == asigTanque.id_dispositivo)
            elif fuente:
                disp_tanque_act = any(a.activo for a in asigs if a.id_fuente_agua == fuente.id)

            tanqueData = {
                "idTelemetria": str(ultimaTelemetriaTanque.id) if (ultimaTelemetriaTanque and ultimaTelemetriaTanque.id) else None,
                "nombre": fuente.nombre if fuente else "Depósito de agua",
                "litrosActuales": round(litros_actuales, 1),
                "litrosTotales": capacidad_maxima,
                "porcentaje": porcentaje_nivel,
                "sensorModelo": compTanque.nombre_modelo if compTanque else "Desconocido",
                "estadoNivel": ultimaTelemetriaTanque.estado_nivel if ultimaTelemetriaTanque else "Desconocido",
                "bombaEncendida": ultimaTelemetriaTanque.bomba_encendida if ultimaTelemetriaTanque else False,
                "timeoutMinutos": timeout_min,
                "dispositivoActivo": disp_tanque_act
            }
            
        umbralAgua = None
        metricas_config_ids = {u.id_tipo_metrica for u in umbrales_c}
        metricas_config_map = {
            m.id: m
            for m in db.query(tipos_metrica).filter(tipos_metrica.id.in_(metricas_config_ids)).all()
        } if metricas_config_ids else {}
        for u in umbrales_c:
            tipo_m = metricas_config_map.get(u.id_tipo_metrica)
            if tipo_m and tipo_m.codigo == 'NIVEL_AGUA':
                umbralAgua = u
                break
        limiteConsumo = float(umbralAgua.valor_maximo) if (umbralAgua and umbralAgua.valor_maximo is not None) else None
        
        sensoresData = {
            "humedadSuelo": mapear_sensor_ultimo(asigHS, lecturasHS, compHS, metricas_por_codigo.get("HUM_SUELO") or metricHS, umbrales, umbrales_c, dashboard_tz),
            "humedadAmbiente": mapear_sensor_ultimo(asigHA, lecturasHA, compHA, metricas_por_codigo.get("HUM_AMB") or metricHA, umbrales, umbrales_c, dashboard_tz),
            "temperaturaSuelo": mapear_sensor_ultimo(asigTS, lecturasTS, compTS, metricas_por_codigo.get("TEMP_SUELO") or metricTS, umbrales, umbrales_c, dashboard_tz),
            "temperaturaAmbiente": mapear_sensor_ultimo(asigTA, lecturasTA, compTA, metricas_por_codigo.get("TEMP_AMB") or metricTA, umbrales, umbrales_c, dashboard_tz),
        }
        
        historialData = {
            "humedadSuelo": mapear_historial(asigHS, lecturasHS, dashboard_tz),
            "humedadAmbiente": mapear_historial(asigHA, lecturasHA, dashboard_tz),
            "temperaturaSuelo": mapear_historial(asigTS, lecturasTS, dashboard_tz),
            "temperaturaAmbiente": mapear_historial(asigTA, lecturasTA, dashboard_tz),
        }
        
        humedadSueloProm = None
        if sensoresData["humedadSuelo"]:
            humedadSueloProm = sensoresData["humedadSuelo"]["ema"] if sensoresData["humedadSuelo"]["ema"] is not None else sensoresData["humedadSuelo"]["porcentaje"]
            
        humedadAmbiental = None
        if sensoresData["humedadAmbiente"]:
            humedadAmbiental = sensoresData["humedadAmbiente"]["ema"] if sensoresData["humedadAmbiente"]["ema"] is not None else sensoresData["humedadAmbiente"]["porcentaje"]
            
        resumenDia = {
            "riegosHoy": riegosHoy,
            "litrosHoy": round(litrosHoy, 1),
            "ultimoRiego": _local_naive_to_timezone_iso(ultimoRiegoFecha, dashboard_tz),
            "humedadSueloProm": humedadSueloProm,
            "humedadAmbiental": humedadAmbiental
        }
        
        result.append({
            "idCultivo": cult.id_cultivo,
            "zonaHoraria": dashboard_tz.zone,
            "tanque": tanqueData,
            "nombreCultivo": cult.nombre_planta,
            "conceptoPlanta": planta.nombre if planta else "Desconocido",
            "etapaCrecimiento": cult.etapa_crecimiento,
            "consumoSemanal": consumoSemanal,
            "limiteConsumo": limiteConsumo,
            "sensores": sensoresData,
            "historialSensores": historialData,
            "dispositivos": list(dispositivosMap.values()),
            "resumenDia": resumenDia
        })
        
    return result


def obtener_datos_alertas(db: Session, userId: int, idCultivo: int) -> dict:
    usuario = db.query(usuarios).filter(usuarios.id_usuario == userId).first()
    user_tz = _get_timezone(usuario.zona_horaria if usuario else None)
    
    # 1. Umbrales
    umbrales_raw = db.query(configuracion_umbrales).filter(
        configuracion_umbrales.id_usuario == userId,
        configuracion_umbrales.id_cultivo == idCultivo
    ).order_by(configuracion_umbrales.id.asc()).all()
    
    if not umbrales_raw:
        # Seed default thresholds based on scientific plant recommendations (umbrales_planta)
        cultivo_db = db.query(cultivos).filter(cultivos.id_cultivo == idCultivo).first()
        id_planta = cultivo_db.id_planta if cultivo_db else None
        
        umbrales_recomendados = []
        if id_planta:
            umbrales_recomendados = db.query(umbrales_planta).filter(umbrales_planta.id_planta == id_planta).all()
            
        tipos = db.query(tipos_metrica).order_by(tipos_metrica.id.asc()).all()
        for t in tipos:
            rec = next((r for r in umbrales_recomendados if r.id_tipo_metrica == t.id), None)
            min_val = float(rec.valor_minimo) if (rec and rec.valor_minimo is not None) else 10.0
            max_val = float(rec.valor_maximo) if (rec and rec.valor_maximo is not None) else 90.0
            
            db_u = configuracion_umbrales(
                id_usuario=userId,
                id_cultivo=idCultivo,
                id_tipo_metrica=t.id,
                valor_minimo=min_val,
                valor_maximo=max_val
            )
            db.add(db_u)
        db.commit()
        
        # Query again
        umbrales_raw = db.query(configuracion_umbrales).filter(
            configuracion_umbrales.id_usuario == userId,
            configuracion_umbrales.id_cultivo == idCultivo
        ).order_by(configuracion_umbrales.id.asc()).all()
    
    umbrales = []
    tipo_metrica_ids = {u.id_tipo_metrica for u in umbrales_raw if u.id_tipo_metrica}
    tipo_metricas_alertas_map = {
        m.id: m
        for m in db.query(tipos_metrica).filter(tipos_metrica.id.in_(tipo_metrica_ids)).all()
    } if tipo_metrica_ids else {}
    for u in umbrales_raw:
        tipo_m = tipo_metricas_alertas_map.get(u.id_tipo_metrica)
        umbrales.append({
            "id": u.id,
            "nombre": tipo_m.nombre if tipo_m else 'Métrica',
            "unidad": tipo_m.unidad if tipo_m else '',
            "min": float(u.valor_minimo) if u.valor_minimo is not None else 0.0,
            "max": float(u.valor_maximo) if u.valor_maximo is not None else 0.0
        })
        
    # 2. Alertas Activas (estado != 'resuelta')
    alertas_activas_raw = db.query(alertas).join(asignaciones_iot, alertas.id_asignacion == asignaciones_iot.id).filter(
        alertas.estado.in_(("pendiente", "activa")),
        asignaciones_iot.id_cultivo == idCultivo,
        asignaciones_iot.id_usuario == userId
    ).order_by(alertas.fecha.desc()).all()

    alertas_activas_tipo_ids = {a.id_tipo_alerta for a in alertas_activas_raw if a.id_tipo_alerta}
    alertas_activas_metrica_ids = {a.id_tipo_metrica for a in alertas_activas_raw if a.id_tipo_metrica}
    alertas_activas_asig_ids = {a.id_asignacion for a in alertas_activas_raw if a.id_asignacion}

    tipos_alerta_activas_map = {
        t.id: t
        for t in db.query(tipos_alerta).filter(tipos_alerta.id.in_(alertas_activas_tipo_ids)).all()
    } if alertas_activas_tipo_ids else {}
    metricas_activas_map = {
        m.id: m
        for m in db.query(tipos_metrica).filter(tipos_metrica.id.in_(alertas_activas_metrica_ids)).all()
    } if alertas_activas_metrica_ids else {}
    asigs_activas_map = {
        a.id: a
        for a in db.query(asignaciones_iot).filter(asignaciones_iot.id.in_(alertas_activas_asig_ids)).all()
    } if alertas_activas_asig_ids else {}
    comps_alertas_map, tipo_comps_alertas_map, _ = _component_context_maps(
        db,
        list(asigs_activas_map.values()),
    )
    
    alertas_activas = []
    for a in alertas_activas_raw:
        tipo_a = tipos_alerta_activas_map.get(a.id_tipo_alerta)
        tipo_m = metricas_activas_map.get(a.id_tipo_metrica)
        
        sensor_nombre = "Sistema"
        asig = asigs_activas_map.get(a.id_asignacion)
        if asig and asig.id_componente:
            comp = comps_alertas_map.get(asig.id_componente)
            tipo_c = tipo_comps_alertas_map.get(comp.id_tipo_componente) if comp else None
            if tipo_c:
                sensor_nombre = tipo_c.nombre_modelo
                    
        alertas_activas.append({
            "id": str(a.id),
            "titulo": tipo_a.nombre if tipo_a else 'Alerta',
            "mensaje": a.mensaje,
            "valor": float(a.valor_detectado) if a.valor_detectado is not None else None,
            "unidad": tipo_m.unidad if tipo_m else '',
            "severidad": tipo_a.severidad if tipo_a else 'info',
            "sensor": sensor_nombre
        })
        
    # 3. Historial (Resueltas)
    historial_raw = db.query(alertas).join(asignaciones_iot, alertas.id_asignacion == asignaciones_iot.id).filter(
        alertas.estado == 'resuelta',
        asignaciones_iot.id_cultivo == idCultivo,
        asignaciones_iot.id_usuario == userId
    ).order_by(alertas.fecha.desc()).limit(10).all()

    historial_tipo_ids = {h.id_tipo_alerta for h in historial_raw if h.id_tipo_alerta}
    historial_metrica_ids = {h.id_tipo_metrica for h in historial_raw if h.id_tipo_metrica}
    tipos_alerta_historial_map = {
        t.id: t
        for t in db.query(tipos_alerta).filter(tipos_alerta.id.in_(historial_tipo_ids)).all()
    } if historial_tipo_ids else {}
    metricas_historial_map = {
        m.id: m
        for m in db.query(tipos_metrica).filter(tipos_metrica.id.in_(historial_metrica_ids)).all()
    } if historial_metrica_ids else {}
    
    historial = []
    for h in historial_raw:
        tipo_a = tipos_alerta_historial_map.get(h.id_tipo_alerta)
        tipo_m = metricas_historial_map.get(h.id_tipo_metrica)
        
        h_local = _to_timezone(h.fecha, user_tz) if h.fecha else None
        fecha_str = h_local.strftime("%d/%m") if h_local else ""
        
        historial.append({
            "id": str(h.id),
            "tipo": tipo_a.nombre if tipo_a else 'Alerta',
            "valor": float(h.valor_detectado) if h.valor_detectado is not None else None,
            "unidad": tipo_m.unidad if tipo_m else '',
            "estado": 'Resuelta',
            "fecha": fecha_str
        })
        
    return { "umbrales": umbrales, "alertasActivas": alertas_activas, "historial": historial }


def obtener_datos_historico(db: Session, userId: int, idCultivo: int, dias: int = 30) -> dict:
    usuario = db.query(usuarios).filter(usuarios.id_usuario == userId).first()
    user_tz = _get_timezone(usuario.zona_horaria if usuario else None)
    fechaActual = datetime.now(user_tz).replace(tzinfo=None)
    
    is_hourly = (dias <= 1)
    
    if is_hourly:
        # dias == 0 -> 6 hours, dias == 1 -> 24 hours
        hours_count = 24 if dias == 1 else 6
        fechaLimite = (fechaActual - timedelta(hours=hours_count)).replace(minute=0, second=0, microsecond=0)
        fechaLimiteUtc = _local_naive_to_utc_naive(fechaLimite, user_tz)
    else:
        fechaLimite = (fechaActual - timedelta(days=dias)).replace(hour=0, minute=0, second=0, microsecond=0)
        fechaLimiteUtc = _local_naive_to_utc_naive(fechaLimite, user_tz)
        
    asigs = db.query(asignaciones_iot).filter(
        asignaciones_iot.id_usuario == userId,
        asignaciones_iot.id_cultivo == idCultivo
    ).all()
    
    if not asigs:
        return { "chartData": [], "stats": None, "riegoLog": [] }
        
    asignaciones_ids = [a.id for a in asigs]
    comps_map, tipo_comps_map, _ = _component_context_maps(db, asigs)

    hs_by_asig = _group_by_assignment(db.query(humedad_suelo).filter(
        humedad_suelo.id_asignacion.in_(asignaciones_ids),
        humedad_suelo.valido == True,
        humedad_suelo.fecha >= fechaLimiteUtc,
    ).all())
    ha_by_asig = _group_by_assignment(db.query(humedad_ambiente).filter(
        humedad_ambiente.id_asignacion.in_(asignaciones_ids),
        humedad_ambiente.valido == True,
        humedad_ambiente.fecha >= fechaLimiteUtc,
    ).all())
    ts_by_asig = _group_by_assignment(db.query(temperatura_suelo).filter(
        temperatura_suelo.id_asignacion.in_(asignaciones_ids),
        temperatura_suelo.valido == True,
        temperatura_suelo.fecha >= fechaLimiteUtc,
    ).all())
    ta_by_asig = _group_by_assignment(db.query(temperatura_ambiente).filter(
        temperatura_ambiente.id_asignacion.in_(asignaciones_ids),
        temperatura_ambiente.valido == True,
        temperatura_ambiente.fecha >= fechaLimiteUtc,
    ).all())
    
    data_por_dia = {}
    if is_hourly:
        for i in range(hours_count + 1):
            h = fechaLimite + timedelta(hours=i)
            key = h.strftime("%Y-%m-%d %H:00")
            label = h.strftime("%H:%M")
            data_por_dia[key] = { "label": label, "hs": [], "ha": [], "ts": [], "ta": [], "riegos": 0 }
    else:
        for i in range(dias + 1):
            d = fechaLimite + timedelta(days=i)
            key = d.strftime("%Y-%m-%d")
            meses_es = ["ene.", "feb.", "mar.", "abr.", "may.", "jun.", "jul.", "ago.", "sep.", "oct.", "nov.", "dic."]
            label = f"{meses_es[d.month - 1]} {d.day}"
            data_por_dia[key] = { "label": label, "hs": [], "ha": [], "ts": [], "ta": [], "riegos": 0 }
        
    stats_raw = {
        "hs": { "min": float('inf'), "max": float('-inf'), "sum": 0.0, "count": 0, "model": 'No asignado' },
        "ha": { "min": float('inf'), "max": float('-inf'), "sum": 0.0, "count": 0, "model": 'No asignado' },
        "ts": { "min": float('inf'), "max": float('-inf'), "sum": 0.0, "count": 0, "model": 'No asignado' },
        "ta": { "min": float('inf'), "max": float('-inf'), "sum": 0.0, "count": 0, "model": 'No asignado' }
    }
    
    def get_local_date_key(dt_utc):
        dt_local = dt_utc.replace(tzinfo=pytz.utc).astimezone(user_tz).replace(tzinfo=None)
        if is_hourly:
            return dt_local.strftime("%Y-%m-%d %H:00")
        else:
            return dt_local.strftime("%Y-%m-%d")
        
    for asig in asigs:
        comp = comps_map.get(asig.id_componente) if asig.id_componente else None
        tipo_c = tipo_comps_map.get(comp.id_tipo_componente) if comp else None
        
        raw_model = tipo_c.nombre_modelo if tipo_c else "Desconocido"
        clean_model = raw_model.replace('Higrómetro ', '').replace('Termómetro ', '').replace(' Capacitivo', '')
        
        hs_list = hs_by_asig.get(asig.id, [])
        if hs_list:
            stats_raw["hs"]["model"] = clean_model
            for l in hs_list:
                val = float(l.ema if l.ema is not None else l.valor)
                key = get_local_date_key(l.fecha)
                if key in data_por_dia:
                    data_por_dia[key]["hs"].append(val)
                if val < stats_raw["hs"]["min"]: stats_raw["hs"]["min"] = val
                if val > stats_raw["hs"]["max"]: stats_raw["hs"]["max"] = val
                stats_raw["hs"]["sum"] += val
                stats_raw["hs"]["count"] += 1
                
        ha_list = ha_by_asig.get(asig.id, [])
        if ha_list:
            stats_raw["ha"]["model"] = clean_model.replace(' (Humedad)', '')
            for l in ha_list:
                val = float(l.ema if l.ema is not None else l.valor)
                key = get_local_date_key(l.fecha)
                if key in data_por_dia:
                    data_por_dia[key]["ha"].append(val)
                if val < stats_raw["ha"]["min"]: stats_raw["ha"]["min"] = val
                if val > stats_raw["ha"]["max"]: stats_raw["ha"]["max"] = val
                stats_raw["ha"]["sum"] += val
                stats_raw["ha"]["count"] += 1
                
        ts_list = ts_by_asig.get(asig.id, [])
        if ts_list:
            stats_raw["ts"]["model"] = clean_model.replace(' Suelo', '')
            for l in ts_list:
                val = float(l.ema if l.ema is not None else (l.temperatura if getattr(l, 'temperatura', None) is not None else l.valor))
                key = get_local_date_key(l.fecha)
                if key in data_por_dia:
                    data_por_dia[key]["ts"].append(val)
                if val < stats_raw["ts"]["min"]: stats_raw["ts"]["min"] = val
                if val > stats_raw["ts"]["max"]: stats_raw["ts"]["max"] = val
                stats_raw["ts"]["sum"] += val
                stats_raw["ts"]["count"] += 1
                
        ta_list = ta_by_asig.get(asig.id, [])
        if ta_list:
            stats_raw["ta"]["model"] = clean_model.replace(' (Temperatura)', '')
            for l in ta_list:
                val = float(l.ema if l.ema is not None else (l.temperatura if getattr(l, 'temperatura', None) is not None else l.valor))
                key = get_local_date_key(l.fecha)
                if key in data_por_dia:
                    data_por_dia[key]["ta"].append(val)
                if val < stats_raw["ta"]["min"]: stats_raw["ta"]["min"] = val
                if val > stats_raw["ta"]["max"]: stats_raw["ta"]["max"] = val
                stats_raw["ta"]["sum"] += val
                stats_raw["ta"]["count"] += 1
                
    riegos_recientes = db.query(riego).filter(
        riego.estado == True,
        riego.fecha >= fechaLimiteUtc,
        riego.id_asignacion.in_(asignaciones_ids)
    ).order_by(riego.fecha.desc()).all()
    
    riego_log = []
    for r in riegos_recientes:
        key = get_local_date_key(r.fecha)
        if key in data_por_dia:
            data_por_dia[key]["riegos"] += 1
            
        origen_str = 'Auto'
        color_str = '#22c55e'
        tipo = (r.tipo_riego or '').lower()
        if 'manual' in tipo:
            origen_str = 'Manual'
            color_str = '#f59e0b'
        elif 'ml' in tipo:
            origen_str = 'ML'
            color_str = '#a855f7'
            
        r_local = r.fecha.replace(tzinfo=pytz.utc).astimezone(user_tz) if r.fecha else datetime.now(user_tz)
        fecha_str = r_local.strftime("%d/%m %H:%M")
        
        riego_log.append({
            "id": str(r.id),
            "fecha": r_local.isoformat(),
            "fechaStr": fecha_str,
            "origen": origen_str,
            "colorOrigen": color_str,
            "litros": f"{float(r.cantidad_agua_litros):.1f}" if r.cantidad_agua_litros is not None else '--'
        })
        
    chart_data = []
    for key, d in data_por_dia.items():
        hs_avg = round(sum(d["hs"]) / len(d["hs"]), 1) if d["hs"] else None
        ha_avg = round(sum(d["ha"]) / len(d["ha"]), 1) if d["ha"] else None
        ts_avg = round(sum(d["ts"]) / len(d["ts"]), 1) if d["ts"] else None
        ta_avg = round(sum(d["ta"]) / len(d["ta"]), 1) if d["ta"] else None
        
        chart_data.append({
            "fecha": key,
            "label": d["label"],
            "humedadSuelo": hs_avg,
            "humedadAmbiente": ha_avg,
            "temperaturaSuelo": ts_avg,
            "temperaturaAmbiente": ta_avg,
            "riegos": d["riegos"] if d["riegos"] > 0 else None
        })
        
    def format_stat(stat, key):
        count = stat["count"]
        return {
            "sensor": stat["model"],
            "min": round(stat["min"], 1) if count > 0 and stat["min"] != float('inf') else None,
            "prom": round(stat["sum"] / count, 1) if count > 0 else None,
            "max": round(stat["max"], 1) if count > 0 and stat["max"] != float('-inf') else None
        }
        
    stats = {
        "humedadSuelo": format_stat(stats_raw["hs"], "hs"),
        "humedadAmbiente": format_stat(stats_raw["ha"], "ha"),
        "temperaturaAmbiente": format_stat(stats_raw["ta"], "ta"),
        "temperaturaSuelo": format_stat(stats_raw["ts"], "ts")
    }
    
    return { "chartData": chart_data, "stats": stats, "riegoLog": riego_log[:20] }


def obtener_datos_ml(db: Session, userId: int, idCultivo: int) -> dict:
    from ..db.models import cultivos, modelos_ml
    usr_mod = db.query(cultivo_modelo).filter(
        cultivo_modelo.id_usuario == userId,
        cultivo_modelo.id_cultivo == idCultivo
    ).order_by(cultivo_modelo.fecha_asignacion.desc()).first()
    
    if not usr_mod:
        default_model = db.query(modelos_ml).filter(modelos_ml.es_default == True).first()
        if not default_model:
            default_model = db.query(modelos_ml).order_by(modelos_ml.id_modelo.asc()).first()
        id_mod = default_model.id_modelo if default_model else 1
        usr_mod = cultivo_modelo(
            id_usuario=userId,
            id_cultivo=idCultivo,
            id_modelo=id_mod,
            activo=False
        )
        db.add(usr_mod)
        db.commit()
        db.refresh(usr_mod)
        
    modelo_activo = None
    if usr_mod:
        modelo_activo = db.query(modelos_ml).filter(modelos_ml.id_modelo == usr_mod.id_modelo).first()
        
    asigs = db.query(asignaciones_iot).filter(
        asignaciones_iot.id_usuario == userId,
        asignaciones_iot.id_cultivo == idCultivo
    ).all()
    
    ids_asig = [a.id for a in asigs]
    
    hum_suelo = db.query(humedad_suelo).filter(humedad_suelo.id_asignacion.in_(ids_asig), humedad_suelo.valido == True).order_by(humedad_suelo.fecha.desc()).limit(15).all()
    hum_amb = db.query(humedad_ambiente).filter(humedad_ambiente.id_asignacion.in_(ids_asig), humedad_ambiente.valido == True).order_by(humedad_ambiente.fecha.desc()).limit(15).all()
    temp_suelo = db.query(temperatura_suelo).filter(temperatura_suelo.id_asignacion.in_(ids_asig), temperatura_suelo.valido == True).order_by(temperatura_suelo.fecha.desc()).limit(15).all()
    temp_amb = db.query(temperatura_ambiente).filter(temperatura_ambiente.id_asignacion.in_(ids_asig), temperatura_ambiente.valido == True).order_by(temperatura_ambiente.fecha.desc()).limit(15).all()
    usuario = db.query(usuarios).filter(usuarios.id_usuario == userId).first()
    user_tz = _get_timezone(usuario.zona_horaria if usuario else None)
    
    datos_historicos = []
    
    for idx, hs in enumerate(reversed(hum_suelo)):
        ha = hum_amb[len(hum_amb) - 1 - idx] if idx < len(hum_amb) else None
        ts = temp_suelo[len(temp_suelo) - 1 - idx] if idx < len(temp_suelo) else None
        ta = temp_amb[len(temp_amb) - 1 - idx] if idx < len(temp_amb) else None
        
        hs_local = hs.fecha.replace(tzinfo=pytz.utc).astimezone(user_tz) if hs.fecha else datetime.now(user_tz)
        hora_str = hs_local.strftime("%H:%M")
        
        datos_historicos.append({
            "hora": hora_str,
            "humSuelo": float(hs.porcentaje if hs.porcentaje is not None else hs.valor) if hs else 0.0,
            "humAmb": float(ha.porcentaje if (ha and ha.porcentaje is not None) else (ha.valor if ha else 0.0)),
            "tempSuelo": float(ts.temperatura if (ts and getattr(ts, 'temperatura', None) is not None) else (ts.valor if ts else 0.0)),
            "tempAmb": float(ta.temperatura if (ta and getattr(ta, 'temperatura', None) is not None) else (ta.valor if ta else 0.0))
        })
        
    umbrales = db.query(configuracion_umbrales).filter(
        configuracion_umbrales.id_usuario == userId,
        configuracion_umbrales.id_cultivo == idCultivo
    ).all()
    
    umbral_minimo = 40.0
    for u in umbrales:
        tipo_m = db.query(tipos_metrica).filter(tipos_metrica.id == u.id_tipo_metrica).first()
        if tipo_m and 'suelo' in tipo_m.nombre.lower():
            umbral_minimo = float(u.valor_minimo) if u.valor_minimo is not None else 40.0
            break

    # Consultar las últimas 15 predicciones de ML para este cultivo
    preds = db.query(predicciones_ml).filter(
        predicciones_ml.id_usuario == userId,
        predicciones_ml.id_cultivo == idCultivo
    ).order_by(predicciones_ml.fecha.desc()).limit(15).all()

    lista_predicciones = []
    for p in preds:
        r = db.query(riego).filter(riego.id_prediccion == p.id_prediccion).first()
        
        riego_detalles = None
        if r:
            riego_detalles = {
                "duracion_segundos": r.duracion_segundos,
                "cantidad_agua_litros": float(r.cantidad_agua_litros) if r.cantidad_agua_litros is not None else None,
                "estado": r.estado,
                "motivo_cierre": r.motivo_cierre
            }
            
        p_local = p.fecha.replace(tzinfo=pytz.utc).astimezone(user_tz) if p.fecha else datetime.now(user_tz)
        fecha_str = p_local.strftime("%d/%m")
        hora_str = p_local.strftime("%H:%M")
        
        vars_in = p.variables_entrada or {}
        
        lista_predicciones.append({
            "id": p.id_prediccion,
            "fecha": fecha_str,
            "hora": hora_str,
            "variables": {
                "humedad_suelo": vars_in.get("humedad_suelo"),
                "humedad_ambiente": vars_in.get("humedad_ambiente"),
                "temperatura_ambiente": vars_in.get("temperatura_ambiente"),
                "temperatura_suelo": vars_in.get("temperatura_suelo")
            },
            "recomendacion": p.recomendacion,
            "probabilidad": float(p.probabilidad) if p.probabilidad is not None else None,
            "ejecutado": p.accion_ejecutada,
            "riego_detalles": riego_detalles
        })
            
    # Obtener modelos compatibles con la planta del cultivo
    cultivo_db = db.query(cultivos).filter(cultivos.id_cultivo == idCultivo).first()
    id_planta_filtro = cultivo_db.id_planta if cultivo_db else None

    modelos_db = db.query(modelos_ml).all()
    modelos_compatibles = []
    for m in modelos_db:
        if id_planta_filtro is not None and m.id_planta is not None and m.id_planta != id_planta_filtro:
            continue
        modelos_compatibles.append({
            "id_modelo": m.id_modelo,
            "nombre_modelo": m.nombre_modelo,
            "algoritmo": m.algoritmo,
            "descripcion": m.descripcion,
            "version": m.version,
            "precision_modelo": float(m.precision_modelo) if m.precision_modelo is not None else None,
            "activo": (modelo_activo and modelo_activo.id_modelo == m.id_modelo) if modelo_activo else False
        })

    # Calcular comparativa de fases experimental de forma dinámica
    comparativa = {
        "manual_litros": 0.0,
        "manual_estres": 0.0,
        "manual_dias": 0,
        "programado_litros": 0.0,
        "programado_estres": 0.0,
        "programado_dias": 0,
        "ml_litros": 0.0,
        "ml_estres": 0.0,
        "ml_dias": 0,
        "ahorro_agua": 0.0,
        "reduccion_estres": 0.0
    }

    # 1. Obtener todos los riegos del cultivo
    riegos_all = db.query(riego).filter(riego.id_asignacion.in_(ids_asig)).order_by(riego.fecha.asc()).all()
    
    t_manual = None
    t_programado = None
    t_ml = None
    
    for r in riegos_all:
        tipo = (r.tipo_riego or '').lower()
        if 'manual' in tipo and t_manual is None:
            t_manual = r.fecha
        elif 'programado' in tipo and t_programado is None:
            t_programado = r.fecha
        elif ('ml' in tipo or 'automatico_ml' in tipo) and t_ml is None:
            t_ml = r.fecha

    # 2. Definir rango de tiempos para cada fase y calcular consumo
    now_utc = datetime.utcnow()
    
    manual_total_litros = 0.0
    programado_total_litros = 0.0
    ml_total_litros = 0.0
    
    for r in riegos_all:
        vol = float(r.cantidad_agua_litros) if r.cantidad_agua_litros is not None else 0.0
        if t_ml and r.fecha >= t_ml:
            ml_total_litros += vol
        elif t_programado and r.fecha >= t_programado:
            programado_total_litros += vol
        elif t_manual and r.fecha >= t_manual:
            manual_total_litros += vol

    # Días transcurridos en cada fase
    def get_days(t_start, t_end):
        if not t_start:
            return 0
        diff = t_end - t_start
        return max(1, diff.days + 1)

    dias_manual = get_days(t_manual, min(filter(None, [t_programado, t_ml, now_utc])))
    dias_prog = get_days(t_programado, min(filter(None, [t_ml, now_utc])))
    dias_ml = get_days(t_ml, now_utc)

    comparativa["manual_dias"] = dias_manual
    comparativa["programado_dias"] = dias_prog
    comparativa["ml_dias"] = dias_ml

    comparativa["manual_litros"] = round(manual_total_litros / dias_manual, 1) if dias_manual > 0 else 0.0
    comparativa["programado_litros"] = round(programado_total_litros / dias_prog, 1) if dias_prog > 0 else 0.0
    comparativa["ml_litros"] = round(ml_total_litros / dias_ml, 1) if dias_ml > 0 else 0.0

    # 3. Obtener estrés hídrico de cada fase
    hum_records = db.query(humedad_suelo).filter(
        humedad_suelo.id_asignacion.in_(ids_asig),
        humedad_suelo.valido == True
    ).all()

    manual_stressed = 0
    manual_total_readings = 0
    
    prog_stressed = 0
    prog_total_readings = 0
    
    ml_stressed = 0
    ml_total_readings = 0

    for h in hum_records:
        val = float(h.porcentaje if h.porcentaje is not None else h.valor) if h else 0.0
        is_stressed = val < umbral_minimo
        
        if t_ml and h.fecha >= t_ml:
            ml_total_readings += 1
            if is_stressed:
                ml_stressed += 1
        elif t_programado and h.fecha >= t_programado:
            prog_total_readings += 1
            if is_stressed:
                prog_stressed += 1
        elif t_manual and h.fecha >= t_manual:
            manual_total_readings += 1
            if is_stressed:
                manual_stressed += 1

    comparativa["manual_estres"] = round((manual_stressed / manual_total_readings) * 100, 1) if manual_total_readings > 0 else 0.0
    comparativa["programado_estres"] = round((prog_stressed / prog_total_readings) * 100, 1) if prog_total_readings > 0 else 0.0
    comparativa["ml_estres"] = round((ml_stressed / ml_total_readings) * 100, 1) if ml_total_readings > 0 else 0.0

    # Ahorros
    if comparativa["manual_litros"] > 0:
        comparativa["ahorro_agua"] = round(((comparativa["manual_litros"] - comparativa["ml_litros"]) / comparativa["manual_litros"]) * 100, 1)
    if comparativa["manual_estres"] > 0:
        comparativa["reduccion_estres"] = round(((comparativa["manual_estres"] - comparativa["ml_estres"]) / comparativa["manual_estres"]) * 100, 1)

    return {
        "modelo": {
            "nombre": modelo_activo.nombre_modelo if modelo_activo else 'Sin modelo',
            "algoritmo": modelo_activo.algoritmo if modelo_activo else 'Algoritmo no definido',
            "version": modelo_activo.version if modelo_activo else '1.0.0',
            "mae": float(modelo_activo.precision_modelo) if (modelo_activo and modelo_activo.precision_modelo is not None) else 0.0,
            "activo": bool(usr_mod.activo) if usr_mod else False
        },
        "modelos": modelos_compatibles,
        "historial": datos_historicos,
        "umbral": umbral_minimo,
        "predicciones": lista_predicciones,
        "comparativa_fases": comparativa
    }


def obtener_datos_dashboard_admin(db: Session, userId: int | None = None) -> dict:
    from ..db.models import usuarios, logs_sistema, cultivos, dispositivos, alertas, riego, predicciones_ml, modelos_ml
    from datetime import datetime, timedelta

    usuario = db.query(usuarios).filter(usuarios.id_usuario == userId).first() if userId else None
    admin_tz = _get_timezone(usuario.zona_horaria if usuario else None)
    fecha_actual = datetime.now(admin_tz).replace(tzinfo=None)
    fecha_limite_7d = fecha_actual - timedelta(days=7)

    # 1. Contadores (Métricas)
    total_usuarios = db.query(usuarios).count()
    total_dispositivos = db.query(dispositivos).count()
    total_dispositivos_activos = db.query(dispositivos).filter(dispositivos.estado == "asignado").count()
    total_cultivos_activos = db.query(cultivos).filter(cultivos.estado == "activo").count()
    alertas_pendientes = db.query(alertas).filter(alertas.estado.in_(("pendiente", "activa"))).count()

    metricas = {
        "total_usuarios": total_usuarios,
        "total_dispositivos": total_dispositivos,
        "total_dispositivos_activos": total_dispositivos_activos,
        "total_cultivos_activos": total_cultivos_activos,
        "alertas_pendientes": alertas_pendientes
    }

    # 2. Obtener logs recientes (Últimos 50)
    db_logs = db.query(logs_sistema).order_by(logs_sistema.fecha.desc()).limit(50).all()
    logs_res = []
    for l in db_logs:
        user_name = "Sistema"
        if l.id_usuario:
            usr = db.query(usuarios).filter(usuarios.id_usuario == l.id_usuario).first()
            if usr:
                user_name = f"{usr.nombre} {usr.apellido or ''}".strip()
        
        logs_res.append({
            "id": l.id,
            "id_usuario": l.id_usuario,
            "usuario_nombre": user_name,
            "accion": l.accion,
            "modulo": l.modulo,
            "descripcion": l.descripcion,
            "ip_acceso": l.ip_acceso,
            "fecha": _to_timezone_iso(l.fecha, admin_tz)
        })

    # 3. Obtener últimas 50 predicciones de ML
    db_preds = db.query(predicciones_ml).order_by(predicciones_ml.fecha.desc()).limit(50).all()
    preds_res = []
    for p in db_preds:
        user_name = "Desconocido"
        if p.id_usuario:
            usr = db.query(usuarios).filter(usuarios.id_usuario == p.id_usuario).first()
            if usr:
                user_name = usr.nombre

        cult_name = "Desconocido"
        if p.id_cultivo:
            cult = db.query(cultivos).filter(cultivos.id_cultivo == p.id_cultivo).first()
            if cult:
                cult_name = cult.nombre_planta

        mod_name = "Modelo General"
        if p.id_modelo:
            mod = db.query(modelos_ml).filter(modelos_ml.id_modelo == p.id_modelo).first()
            if mod:
                mod_name = mod.nombre_modelo

        preds_res.append({
            "id": p.id_prediccion,
            "id_usuario": p.id_usuario,
            "id_cultivo": p.id_cultivo,
            "usuario_nombre": user_name,
            "cultivo_nombre": cult_name,
            "modelo_nombre": mod_name,
            "recomendacion": p.recomendacion,
            "probabilidad": float(p.probabilidad) if p.probabilidad is not None else 0.0,
            "accion_ejecutada": bool(p.accion_ejecutada),
            "fecha": _to_timezone_iso(p.fecha, admin_tz)
        })

    # 4. Estadísticas de modelos de ML
    db_models = db.query(modelos_ml).all()
    models_res = []
    for m in db_models:
        total_pred_model = db.query(predicciones_ml).filter(predicciones_ml.id_modelo == m.id_modelo).count()
        models_res.append({
            "id": m.id_modelo,
            "nombre_modelo": m.nombre_modelo,
            "algoritmo": m.algoritmo,
            "precision_modelo": float(m.precision_modelo) if m.precision_modelo is not None else None,
            "precision_score": float(m.precision_score) if m.precision_score is not None else None,
            "recall_score": float(m.recall_score) if m.recall_score is not None else None,
            "f1_score": float(m.f1_score) if m.f1_score is not None else None,
            "es_default": bool(m.es_default),
            "predicciones_totales": total_pred_model
        })

    # 5. Consumo semanal de agua global (últimos 7 días)
    consumo_map = {}
    for i in range(6, -1, -1):
        d = fecha_actual - timedelta(days=i)
        date_key = d.strftime("%Y-%m-%d")
        label = d.strftime("%d/%m")
        consumo_map[date_key] = { "fecha": label, "litros": 0.0, "riegos": 0 }

    inicio_de_limite = _local_naive_to_utc_naive(
        fecha_limite_7d.replace(hour=0, minute=0, second=0, microsecond=0),
        admin_tz,
    )
    riegos_globales = db.query(riego).filter(riego.fecha >= inicio_de_limite, riego.estado == True).all()
    for r in riegos_globales:
        r_local = _to_timezone(r.fecha, admin_tz).replace(tzinfo=None) if r.fecha else None
        if r_local:
            date_key = r_local.strftime("%Y-%m-%d")
            if date_key in consumo_map:
                if r.cantidad_agua_litros is not None:
                    consumo_map[date_key]["litros"] += float(r.cantidad_agua_litros)
                consumo_map[date_key]["riegos"] += 1

    chart_data = list(consumo_map.values())

    # 6. Obtener listas de usuarios y cultivos para filtros
    db_all_users = db.query(usuarios).all()
    users_filter = [
        {
            "id": u.id_usuario,
            "nombre": u.nombre,
            "apellido": u.apellido,
            "correo": u.correo
        }
        for u in db_all_users
    ]

    db_all_crops = db.query(cultivos).all()
    crops_filter = [
        {
            "id": c.id_cultivo,
            "nombre_planta": c.nombre_planta,
            "id_usuario": c.id_usuario
        }
        for c in db_all_crops
    ]

    return {
        "metricas": metricas,
        "logs": logs_res,
        "predicciones": preds_res,
        "modelos": models_res,
        "consumo_semanal": chart_data,
        "usuarios_filtro": users_filter,
        "cultivos_filtro": crops_filter,
        "zona_horaria": admin_tz.zone,
    }

