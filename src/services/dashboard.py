from datetime import datetime, timedelta
from typing import List
import pytz
from sqlalchemy.orm import Session

from ..db.models import (
    cultivos,
    plantas,
    umbrales_planta,
    fuentes_agua,
    configuracion_control,
    umbrales_config,
    asignaciones_iot,
    dispositivos,
    tipos_dispositivo,
    componentes,
    tipos_componente,
    tipos_metrica,
    humedad_suelo,
    humedad_ambiente,
    temperatura_suelo,
    temperatura_ambiente,
    configuracion_tanque,
    telemetria_tanque,
    riego,
    alertas,
    tipos_alerta,
    modelos_ml,
    cultivo_modelo,
    predicciones_ml
)


DEFAULT_UMBRALES_METRICA = {
    "HUM_SUELO": {"min": 35.0, "max": 75.0},
    "HUM_AMB": {"min": 40.0, "max": 80.0},
    "TEMP_AMB": {"min": 18.0, "max": 30.0},
    "TEMP_SUELO": {"min": 18.0, "max": 26.0},
}


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


def mapear_sensor_ultimo(asignacion, lecturas, tipo_comp, tipo_metrica, umbrales_planta_lista, umbrales_config_lista):
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
        "fecha": lectura.fecha.isoformat() if lectura.fecha else None,
        "umbral": umbral
    }


def mapear_historial(asignacion, lecturas):
    if not asignacion or not lecturas:
        return []
    return [
        {
            "fecha": l.fecha.isoformat() if l.fecha else None,
            "valor": float(l.valor) if l.valor is not None else 0.0
        }
        for l in reversed(lecturas)
    ]


def obtener_datos_dashboard(db: Session, userId: int) -> List[dict]:
    lima_tz = pytz.timezone("America/Lima")
    fechaActual = datetime.now(lima_tz).replace(tzinfo=None)
    
    fechaLimite7d = fechaActual - timedelta(days=7)
    fechaLimiteConsumo = (fechaActual - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
    
    # 1. Obtener cultivos activos del usuario
    db_cultivos = db.query(cultivos).filter(
        cultivos.id_usuario == userId,
        cultivos.estado == "activo"
    ).all()
    metricas_por_codigo = {
        m.codigo: m
        for m in db.query(tipos_metrica).filter(
            tipos_metrica.codigo.in_(("HUM_SUELO", "HUM_AMB", "TEMP_AMB", "TEMP_SUELO"))
        ).all()
    }
    
    result = []
    for cult in db_cultivos:
        # Relaciones del cultivo
        planta = db.query(plantas).filter(plantas.id_planta == cult.id_planta).first()
        umbrales = db.query(umbrales_planta).filter(umbrales_planta.id_planta == cult.id_planta).all() if planta else []
        fuente = db.query(fuentes_agua).filter(fuentes_agua.id == cult.id_fuente_agua).first()
        config_ctrl = db.query(configuracion_control).filter(
            configuracion_control.id_usuario == userId,
            configuracion_control.id_cultivo == cult.id_cultivo
        ).all()
        umbrales_c = db.query(umbrales_config).filter(
            umbrales_config.id_usuario == userId,
            umbrales_config.id_cultivo == cult.id_cultivo
        ).all()
        
        # Asignaciones de este cultivo (independientemente de si están activas o no)
        asigs = db.query(asignaciones_iot).filter(
            asignaciones_iot.id_usuario == userId,
            asignaciones_iot.id_cultivo == cult.id_cultivo
        ).all()
        
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
            dev = db.query(dispositivos).filter(dispositivos.id_dispositivo == asig.id_dispositivo).first()
            if dev:
                tipo_dev = db.query(tipos_dispositivo).filter(tipos_dispositivo.id == dev.id_tipo).first()
                dispositivosMap[dev.id_dispositivo] = {
                    "id": dev.id_dispositivo,
                    "nombre": dev.nombre,
                    "estado": dev.estado if dev.estado else "offline",
                    "funcionamientoActivo": any(a.activo for a in asigs if a.id_dispositivo == dev.id_dispositivo)
                }
                
            # Componente
            comp = db.query(componentes).filter(componentes.id == asig.id_componente).first() if asig.id_componente else None
            tipo_comp = db.query(tipos_componente).filter(tipos_componente.id == comp.id_tipo_componente).first() if comp else None
            tipo_metric = db.query(tipos_metrica).filter(tipos_metrica.id == tipo_comp.id_tipo_metrica).first() if (tipo_comp and tipo_comp.id_tipo_metrica) else None
            
            # Consultar lecturas de telemetría de 7 días
            hs_list = db.query(humedad_suelo).filter(humedad_suelo.id_asignacion == asig.id, humedad_suelo.valido == True, humedad_suelo.fecha >= fechaLimite7d).order_by(humedad_suelo.fecha.desc()).all()
            if hs_list:
                asigHS, lecturasHS, compHS, metricHS = asig, hs_list, tipo_comp, tipo_metric
                
            ha_list = db.query(humedad_ambiente).filter(humedad_ambiente.id_asignacion == asig.id, humedad_ambiente.valido == True, humedad_ambiente.fecha >= fechaLimite7d).order_by(humedad_ambiente.fecha.desc()).all()
            if ha_list:
                asigHA, lecturasHA, compHA, metricHA = asig, ha_list, tipo_comp, tipo_metric
                
            ts_list = db.query(temperatura_suelo).filter(temperatura_suelo.id_asignacion == asig.id, temperatura_suelo.valido == True, temperatura_suelo.fecha >= fechaLimite7d).order_by(temperatura_suelo.fecha.desc()).all()
            if ts_list:
                asigTS, lecturasTS, compTS, metricTS = asig, ts_list, tipo_comp, tipo_metric
                
            ta_list = db.query(temperatura_ambiente).filter(temperatura_ambiente.id_asignacion == asig.id, temperatura_ambiente.valido == True, temperatura_ambiente.fecha >= fechaLimite7d).order_by(temperatura_ambiente.fecha.desc()).all()
            if ta_list:
                asigTA, lecturasTA, compTA, metricTA = asig, ta_list, tipo_comp, tipo_metric
                
            # Telemetría Tanque
            tt_latest = db.query(telemetria_tanque).filter(telemetria_tanque.id_asignacion == asig.id).order_by(telemetria_tanque.fecha.desc()).first()
            if tt_latest:
                asigTanque, ultimaTelemetriaTanque, compTanque = asig, tt_latest, tipo_comp
                
            # Consultar consumos de riego
            riego_list = db.query(riego).filter(riego.id_asignacion == asig.id, riego.fecha >= fechaLimiteConsumo, riego.estado == True).all()
            for r in riego_list:
                fecha_r_lima = r.fecha.replace(tzinfo=pytz.utc).astimezone(lima_tz).replace(tzinfo=None) if r.fecha else None
                if fecha_r_lima:
                    date_key = fecha_r_lima.strftime("%Y-%m-%d")
                    if date_key in consumoSemanalMap and r.cantidad_agua_litros is not None:
                        consumoSemanalMap[date_key]["valor"] += float(r.cantidad_agua_litros)
                        
                    if ultimoRiegoFecha is None or fecha_r_lima > ultimoRiegoFecha:
                        ultimoRiegoFecha = fecha_r_lima
                        
                    if fecha_r_lima >= inicioDeHoy:
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
        for u in umbrales_c:
            tipo_m = db.query(tipos_metrica).filter(tipos_metrica.id == u.id_tipo_metrica).first()
            if tipo_m and tipo_m.codigo == 'NIVEL_AGUA':
                umbralAgua = u
                break
        limiteConsumo = float(umbralAgua.valor_maximo) if (umbralAgua and umbralAgua.valor_maximo is not None) else None
        
        sensoresData = {
            "humedadSuelo": mapear_sensor_ultimo(asigHS, lecturasHS, compHS, metricas_por_codigo.get("HUM_SUELO") or metricHS, umbrales, umbrales_c),
            "humedadAmbiente": mapear_sensor_ultimo(asigHA, lecturasHA, compHA, metricas_por_codigo.get("HUM_AMB") or metricHA, umbrales, umbrales_c),
            "temperaturaSuelo": mapear_sensor_ultimo(asigTS, lecturasTS, compTS, metricas_por_codigo.get("TEMP_SUELO") or metricTS, umbrales, umbrales_c),
            "temperaturaAmbiente": mapear_sensor_ultimo(asigTA, lecturasTA, compTA, metricas_por_codigo.get("TEMP_AMB") or metricTA, umbrales, umbrales_c),
        }
        
        historialData = {
            "humedadSuelo": mapear_historial(asigHS, lecturasHS),
            "humedadAmbiente": mapear_historial(asigHA, lecturasHA),
            "temperaturaSuelo": mapear_historial(asigTS, lecturasTS),
            "temperaturaAmbiente": mapear_historial(asigTA, lecturasTA),
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
            "ultimoRiego": ultimoRiegoFecha.isoformat() if ultimoRiegoFecha else None,
            "humedadSueloProm": humedadSueloProm,
            "humedadAmbiental": humedadAmbiental
        }
        
        result.append({
            "idCultivo": cult.id_cultivo,
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
    # 1. Umbrales
    umbrales_raw = db.query(umbrales_config).filter(
        umbrales_config.id_usuario == userId,
        umbrales_config.id_cultivo == idCultivo
    ).order_by(umbrales_config.id.asc()).all()
    
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
            
            db_u = umbrales_config(
                id_usuario=userId,
                id_cultivo=idCultivo,
                id_tipo_metrica=t.id,
                valor_minimo=min_val,
                valor_maximo=max_val
            )
            db.add(db_u)
        db.commit()
        
        # Query again
        umbrales_raw = db.query(umbrales_config).filter(
            umbrales_config.id_usuario == userId,
            umbrales_config.id_cultivo == idCultivo
        ).order_by(umbrales_config.id.asc()).all()
    
    umbrales = []
    for u in umbrales_raw:
        tipo_m = db.query(tipos_metrica).filter(tipos_metrica.id == u.id_tipo_metrica).first()
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
    
    alertas_activas = []
    for a in alertas_activas_raw:
        tipo_a = db.query(tipos_alerta).filter(tipos_alerta.id == a.id_tipo_alerta).first()
        tipo_m = db.query(tipos_metrica).filter(tipos_metrica.id == a.id_tipo_metrica).first()
        
        sensor_nombre = "Sistema"
        asig = db.query(asignaciones_iot).filter(asignaciones_iot.id == a.id_asignacion).first()
        if asig and asig.id_componente:
            comp = db.query(componentes).filter(componentes.id == asig.id_componente).first()
            if comp:
                tipo_c = db.query(tipos_componente).filter(tipos_componente.id == comp.id_tipo_componente).first()
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
    
    historial = []
    for h in historial_raw:
        tipo_a = db.query(tipos_alerta).filter(tipos_alerta.id == h.id_tipo_alerta).first()
        tipo_m = db.query(tipos_metrica).filter(tipos_metrica.id == h.id_tipo_metrica).first()
        
        fecha_str = h.fecha.strftime("%d/%m") if h.fecha else ""
        
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
    lima_tz = pytz.timezone("America/Lima")
    fechaActual = datetime.now(lima_tz).replace(tzinfo=None)
    
    fechaLimite = (fechaActual - timedelta(days=dias)).replace(hour=0, minute=0, second=0, microsecond=0)
    
    asigs = db.query(asignaciones_iot).filter(
        asignaciones_iot.id_usuario == userId,
        asignaciones_iot.id_cultivo == idCultivo
    ).all()
    
    if not asigs:
        return { "chartData": [], "stats": None, "riegoLog": [] }
        
    asignaciones_ids = [a.id for a in asigs]
    
    data_por_dia = {}
    for i in range(dias + 1):
        d = fechaLimite + timedelta(days=i)
        date_key = d.strftime("%Y-%m-%d")
        meses_es = ["ene.", "feb.", "mar.", "abr.", "may.", "jun.", "jul.", "ago.", "sep.", "oct.", "nov.", "dic."]
        label = f"{meses_es[d.month - 1]} {d.day}"
        data_por_dia[date_key] = { "label": label, "hs": [], "ha": [], "ts": [], "ta": [], "riegos": 0 }
        
    stats_raw = {
        "hs": { "min": float('inf'), "max": float('-inf'), "sum": 0.0, "count": 0, "model": 'No asignado' },
        "ha": { "min": float('inf'), "max": float('-inf'), "sum": 0.0, "count": 0, "model": 'No asignado' },
        "ts": { "min": float('inf'), "max": float('-inf'), "sum": 0.0, "count": 0, "model": 'No asignado' },
        "ta": { "min": float('inf'), "max": float('-inf'), "sum": 0.0, "count": 0, "model": 'No asignado' }
    }
    
    def get_lima_date_key(dt_utc):
        dt_lima = dt_utc.replace(tzinfo=pytz.utc).astimezone(lima_tz).replace(tzinfo=None)
        return dt_lima.strftime("%Y-%m-%d")
        
    for asig in asigs:
        comp = db.query(componentes).filter(componentes.id == asig.id_componente).first() if asig.id_componente else None
        tipo_c = db.query(tipos_componente).filter(tipos_componente.id == comp.id_tipo_componente).first() if comp else None
        
        raw_model = tipo_c.nombre_modelo if tipo_c else "Desconocido"
        clean_model = raw_model.replace('Higrómetro ', '').replace('Termómetro ', '').replace(' Capacitivo', '')
        
        hs_list = db.query(humedad_suelo).filter(humedad_suelo.id_asignacion == asig.id, humedad_suelo.valido == True, humedad_suelo.fecha >= fechaLimite).all()
        if hs_list:
            stats_raw["hs"]["model"] = clean_model
            for l in hs_list:
                val = float(l.ema if l.ema is not None else l.valor)
                key = get_lima_date_key(l.fecha)
                if key in data_por_dia:
                    data_por_dia[key]["hs"].append(val)
                if val < stats_raw["hs"]["min"]: stats_raw["hs"]["min"] = val
                if val > stats_raw["hs"]["max"]: stats_raw["hs"]["max"] = val
                stats_raw["hs"]["sum"] += val
                stats_raw["hs"]["count"] += 1
                
        ha_list = db.query(humedad_ambiente).filter(humedad_ambiente.id_asignacion == asig.id, humedad_ambiente.valido == True, humedad_ambiente.fecha >= fechaLimite).all()
        if ha_list:
            stats_raw["ha"]["model"] = clean_model.replace(' (Humedad)', '')
            for l in ha_list:
                val = float(l.ema if l.ema is not None else l.valor)
                key = get_lima_date_key(l.fecha)
                if key in data_por_dia:
                    data_por_dia[key]["ha"].append(val)
                if val < stats_raw["ha"]["min"]: stats_raw["ha"]["min"] = val
                if val > stats_raw["ha"]["max"]: stats_raw["ha"]["max"] = val
                stats_raw["ha"]["sum"] += val
                stats_raw["ha"]["count"] += 1
                
        ts_list = db.query(temperatura_suelo).filter(temperatura_suelo.id_asignacion == asig.id, temperatura_suelo.valido == True, temperatura_suelo.fecha >= fechaLimite).all()
        if ts_list:
            stats_raw["ts"]["model"] = clean_model.replace(' Suelo', '')
            for l in ts_list:
                val = float(l.ema if l.ema is not None else (l.temperatura if getattr(l, 'temperatura', None) is not None else l.valor))
                key = get_lima_date_key(l.fecha)
                if key in data_por_dia:
                    data_por_dia[key]["ts"].append(val)
                if val < stats_raw["ts"]["min"]: stats_raw["ts"]["min"] = val
                if val > stats_raw["ts"]["max"]: stats_raw["ts"]["max"] = val
                stats_raw["ts"]["sum"] += val
                stats_raw["ts"]["count"] += 1
                
        ta_list = db.query(temperatura_ambiente).filter(temperatura_ambiente.id_asignacion == asig.id, temperatura_ambiente.valido == True, temperatura_ambiente.fecha >= fechaLimite).all()
        if ta_list:
            stats_raw["ta"]["model"] = clean_model.replace(' (Temperatura)', '')
            for l in ta_list:
                val = float(l.ema if l.ema is not None else (l.temperatura if getattr(l, 'temperatura', None) is not None else l.valor))
                key = get_lima_date_key(l.fecha)
                if key in data_por_dia:
                    data_por_dia[key]["ta"].append(val)
                if val < stats_raw["ta"]["min"]: stats_raw["ta"]["min"] = val
                if val > stats_raw["ta"]["max"]: stats_raw["ta"]["max"] = val
                stats_raw["ta"]["sum"] += val
                stats_raw["ta"]["count"] += 1
                
    riegos_recientes = db.query(riego).filter(
        riego.estado == True,
        riego.fecha >= fechaLimite,
        riego.id_asignacion.in_(asignaciones_ids)
    ).order_by(riego.fecha.desc()).all()
    
    riego_log = []
    for r in riegos_recientes:
        key = get_lima_date_key(r.fecha)
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
            
        r_lima = r.fecha.replace(tzinfo=pytz.utc).astimezone(lima_tz)
        fecha_str = r_lima.strftime("%d/%m %H:%M")
        
        riego_log.append({
            "id": str(r.id),
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
    
    datos_historicos = []
    lima_tz = pytz.timezone("America/Lima")
    
    for idx, hs in enumerate(reversed(hum_suelo)):
        ha = hum_amb[len(hum_amb) - 1 - idx] if idx < len(hum_amb) else None
        ts = temp_suelo[len(temp_suelo) - 1 - idx] if idx < len(temp_suelo) else None
        ta = temp_amb[len(temp_amb) - 1 - idx] if idx < len(temp_amb) else None
        
        hs_lima = hs.fecha.replace(tzinfo=pytz.utc).astimezone(lima_tz) if hs.fecha else datetime.now()
        hora_str = hs_lima.strftime("%H:%M")
        
        datos_historicos.append({
            "hora": hora_str,
            "humSuelo": float(hs.porcentaje if hs.porcentaje is not None else hs.valor) if hs else 0.0,
            "humAmb": float(ha.porcentaje if (ha and ha.porcentaje is not None) else (ha.valor if ha else 0.0)),
            "tempSuelo": float(ts.temperatura if (ts and getattr(ts, 'temperatura', None) is not None) else (ts.valor if ts else 0.0)),
            "tempAmb": float(ta.temperatura if (ta and getattr(ta, 'temperatura', None) is not None) else (ta.valor if ta else 0.0))
        })
        
    umbrales = db.query(umbrales_config).filter(
        umbrales_config.id_usuario == userId,
        umbrales_config.id_cultivo == idCultivo
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
            
        p_lima = p.fecha.replace(tzinfo=pytz.utc).astimezone(lima_tz) if p.fecha else datetime.now()
        fecha_str = p_lima.strftime("%d/%m")
        hora_str = p_lima.strftime("%H:%M")
        
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
        "predicciones": lista_predicciones
    }


def obtener_datos_dashboard_admin(db: Session) -> dict:
    from ..db.models import usuarios, logs_sistema, cultivos, dispositivos, alertas, riego, predicciones_ml, modelos_ml
    import pytz
    from datetime import datetime, timedelta

    lima_tz = pytz.timezone("America/Lima")
    fecha_actual = datetime.now(lima_tz).replace(tzinfo=None)
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
            "fecha": l.fecha
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
            "fecha": p.fecha
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

    inicio_de_limite = fecha_limite_7d.replace(hour=0, minute=0, second=0, microsecond=0)
    riegos_globales = db.query(riego).filter(riego.fecha >= inicio_de_limite, riego.estado == True).all()
    for r in riegos_globales:
        r_lima = r.fecha.replace(tzinfo=pytz.utc).astimezone(lima_tz).replace(tzinfo=None) if r.fecha else None
        if r_lima:
            date_key = r_lima.strftime("%Y-%m-%d")
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
        "cultivos_filtro": crops_filter
    }

