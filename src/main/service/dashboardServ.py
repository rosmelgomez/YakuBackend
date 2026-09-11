import logging

logger = logging.getLogger(__name__)

from collections import defaultdict
from datetime import datetime, timedelta
from typing import List

import pytz
from sqlalchemy.orm import Session

from src.main.model.models import configuracion_umbrales, cultivo_modelo
from src.main.repositories import dashboardRep as data_repository
from src.main.repositories import sessionRep as session_repository

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
                "max": float(u.valor_maximo) if u.valor_maximo is not None else None,
            }
            break

    for u in umbrales_config_lista:
        if u.id_tipo_metrica == tipo_metrica.id:
            min_val = float(u.valor_minimo) if u.valor_minimo is not None else None
            max_val = float(u.valor_maximo) if u.valor_maximo is not None else None
            if fallback and min_val == 10.0 and max_val == 90.0:
                return umbral_planta or fallback
            return {"min": min_val, "max": max_val}

    if umbral_planta:
        return umbral_planta

    return fallback


def _valor_lectura(lectura, tipo_metrica):
    codigo = tipo_metrica.codigo if tipo_metrica else ""
    if (
        codigo in {"HUM_SUELO", "HUM_AMB"}
        and getattr(lectura, "porcentaje", None) is not None
    ):
        return float(lectura.porcentaje)
    if (
        codigo in {"TEMP_SUELO", "TEMP_AMB"}
        and getattr(lectura, "temperatura", None) is not None
    ):
        return float(lectura.temperatura)
    return float(lectura.valor) if lectura.valor is not None else 0.0


def mapear_sensor_ultimo(
    asignacion,
    lecturas,
    tipo_comp,
    tipo_metrica,
    umbrales_planta_lista,
    umbrales_config_lista,
    tz,
):
    if not asignacion or not lecturas:
        return None
    lectura = lecturas[0]

    umbral = _resolver_umbral(
        tipo_metrica, umbrales_planta_lista, umbrales_config_lista
    )

    porcentaje = (
        float(lectura.porcentaje)
        if getattr(lectura, "porcentaje", None) is not None
        else None
    )
    ema = float(lectura.ema) if getattr(lectura, "ema", None) is not None else None

    return {
        "modelo": tipo_comp.nombre_modelo if tipo_comp else "Desconocido",
        "metrica": tipo_metrica.nombre if tipo_metrica else "Sensor",
        "unidad": tipo_metrica.unidad if tipo_metrica else "",
        "valor": _valor_lectura(lectura, tipo_metrica),
        "porcentaje": porcentaje,
        "ema": ema,
        "fecha": _to_timezone_iso(lectura.fecha, tz),
        "umbral": umbral,
    }


def mapear_historial(asignacion, lecturas, tz):
    if not asignacion or not lecturas:
        return []
    return [
        {
            "fecha": _to_timezone_iso(l.fecha, tz),
            "valor": float(l.valor) if l.valor is not None else 0.0,
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
        if current is None or (
            row.fecha and current.fecha and row.fecha > current.fecha
        ):
            latest[row.id_asignacion] = row
    return latest


def _component_context_maps(db: Session, asigs: list):
    component_ids = {a.id_componente for a in asigs if a.id_componente}
    comps = (
        {
            c.id: c
            for c in data_repository.queryComponentContextMapsComponentes(
                db, component_ids
            )
        }
        if component_ids
        else {}
    )

    tipo_component_ids = {
        c.id_tipo_componente for c in comps.values() if c.id_tipo_componente
    }
    tipo_comps = (
        {
            t.id: t
            for t in data_repository.queryComponentContextMapsTiposComponente(
                db, tipo_component_ids
            )
        }
        if tipo_component_ids
        else {}
    )

    tipo_metrica_ids = {
        t.id_tipo_metrica for t in tipo_comps.values() if t.id_tipo_metrica
    }
    tipo_metricas = (
        {
            m.id: m
            for m in data_repository.queryComponentContextMapsTiposMetrica(
                db, tipo_metrica_ids
            )
        }
        if tipo_metrica_ids
        else {}
    )

    return comps, tipo_comps, tipo_metricas


def obtener_datos_dashboard(db: Session, userId: int) -> List[dict]:
    usuario = data_repository.queryObtenerDatosDashboardUsuario(db, userId)
    dashboard_tz = _get_timezone(usuario.zona_horaria if usuario else None)
    fechaActual = datetime.now(dashboard_tz).replace(tzinfo=None)

    fechaLimite7d = _local_naive_to_utc_naive(
        fechaActual - timedelta(days=7), dashboard_tz
    )
    fechaLimiteConsumo = (fechaActual - timedelta(days=6)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    fechaLimiteConsumoUtc = _local_naive_to_utc_naive(fechaLimiteConsumo, dashboard_tz)

    # 1. Obtener cultivos activos del usuario
    db_cultivos = data_repository.queryObtenerDatosDashboardDbCultivos(db, userId)
    if not db_cultivos:
        return []

    cultivo_ids = [cult.id_cultivo for cult in db_cultivos]
    planta_ids = {cult.id_planta for cult in db_cultivos if cult.id_planta}
    fuente_ids = {cult.id_fuente_agua for cult in db_cultivos if cult.id_fuente_agua}

    plantas_map = (
        {
            p.id_planta: p
            for p in data_repository.queryObtenerDatosDashboardPlantas(db, planta_ids)
        }
        if planta_ids
        else {}
    )
    fuentes_map = (
        {
            f.id: f
            for f in data_repository.queryObtenerDatosDashboardFuentesAgua(
                db, fuente_ids
            )
        }
        if fuente_ids
        else {}
    )
    umbrales_planta_map = defaultdict(list)
    if planta_ids:
        for u in data_repository.queryObtenerDatosDashboardUmbralesPlanta(
            db, planta_ids
        ):
            umbrales_planta_map[u.id_planta].append(u)
    config_control_map = defaultdict(list)
    for c in data_repository.queryObtenerDatosDashboardConfiguracionControl(
        db, userId, cultivo_ids
    ):
        config_control_map[c.id_cultivo].append(c)
    umbrales_config_map = defaultdict(list)
    for u in data_repository.queryObtenerDatosDashboardConfiguracionUmbrales(
        db, userId, cultivo_ids
    ):
        umbrales_config_map[u.id_cultivo].append(u)

    asigs_all = data_repository.queryObtenerDatosDashboardAsigsAll(
        db, userId, cultivo_ids
    )
    asigs_by_cultivo = defaultdict(list)
    for asig in asigs_all:
        asigs_by_cultivo[asig.id_cultivo].append(asig)

    asig_ids = [a.id for a in asigs_all]
    device_ids = {a.id_dispositivo for a in asigs_all if a.id_dispositivo}
    devices_map = (
        {
            d.id_dispositivo: d
            for d in data_repository.queryObtenerDatosDashboardDispositivos(
                db, device_ids
            )
        }
        if device_ids
        else {}
    )
    comps_map, tipo_comps_map, tipo_metricas_map = _component_context_maps(
        db, asigs_all
    )

    hs_by_asig = ha_by_asig = ts_by_asig = ta_by_asig = defaultdict(list)
    tanque_latest_by_asig = {}
    riegos_by_asig = defaultdict(list)
    if asig_ids:
        hs_by_asig = _group_by_assignment(
            data_repository.queryObtenerDatosDashboardHumedadSuelo(
                db, asig_ids, fechaLimite7d
            )
        )
        ha_by_asig = _group_by_assignment(
            data_repository.queryObtenerDatosDashboardHumedadAmbiente(
                db, asig_ids, fechaLimite7d
            )
        )
        ts_by_asig = _group_by_assignment(
            data_repository.queryObtenerDatosDashboardTemperaturaSuelo(
                db, asig_ids, fechaLimite7d
            )
        )
        ta_by_asig = _group_by_assignment(
            data_repository.queryObtenerDatosDashboardTemperaturaAmbiente(
                db, asig_ids, fechaLimite7d
            )
        )
        tanque_latest_by_asig = _latest_per_assignment(
            data_repository.queryObtenerDatosDashboardTelemetriaTanque(db, asig_ids)
        )
        riegos_by_asig = _group_by_assignment(
            data_repository.queryObtenerDatosDashboardRiego(
                db, asig_ids, fechaLimiteConsumoUtc
            )
        )

    metricas_por_codigo = {
        m.codigo: m for m in data_repository.queryObtenerDatosDashboardTiposMetrica(db)
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
        diasSemana = ["Dom", "Lun", "Mar", "Mié", "Jue", "Vie", "Sáb"]
        consumoSemanalMap = {}
        for i in range(6, -1, -1):
            d = fechaActual - timedelta(days=i)
            dateKey = d.strftime("%Y-%m-%d")
            label = (
                "Hoy" if i == 0 else diasSemana[(d.weekday() + 1) % 7]
            )  # Ajustar a Domingo=0 para paridad
            consumoSemanalMap[dateKey] = {"label": label, "valor": 0.0}

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
                    "funcionamientoActivo": any(
                        a.activo
                        for a in asigs
                        if a.id_dispositivo == dev.id_dispositivo
                    ),
                }

            # Componente
            comp = comps_map.get(asig.id_componente) if asig.id_componente else None
            tipo_comp = tipo_comps_map.get(comp.id_tipo_componente) if comp else None
            tipo_metric = (
                tipo_metricas_map.get(tipo_comp.id_tipo_metrica)
                if (tipo_comp and tipo_comp.id_tipo_metrica)
                else None
            )

            # Consultar lecturas de telemetría de 7 días
            hs_list = hs_by_asig.get(asig.id, [])
            if hs_list:
                if not lecturasHS or hs_list[0].fecha > lecturasHS[0].fecha:
                    asigHS, lecturasHS, compHS, metricHS = (
                        asig,
                        hs_list,
                        tipo_comp,
                        tipo_metric,
                    )

            ha_list = ha_by_asig.get(asig.id, [])
            if ha_list:
                if not lecturasHA or ha_list[0].fecha > lecturasHA[0].fecha:
                    asigHA, lecturasHA, compHA, metricHA = (
                        asig,
                        ha_list,
                        tipo_comp,
                        tipo_metric,
                    )

            ts_list = ts_by_asig.get(asig.id, [])
            if ts_list:
                if not lecturasTS or ts_list[0].fecha > lecturasTS[0].fecha:
                    asigTS, lecturasTS, compTS, metricTS = (
                        asig,
                        ts_list,
                        tipo_comp,
                        tipo_metric,
                    )

            ta_list = ta_by_asig.get(asig.id, [])
            if ta_list:
                if not lecturasTA or ta_list[0].fecha > lecturasTA[0].fecha:
                    asigTA, lecturasTA, compTA, metricTA = (
                        asig,
                        ta_list,
                        tipo_comp,
                        tipo_metric,
                    )

            # Telemetría Tanque
            tt_latest = tanque_latest_by_asig.get(asig.id)
            if tt_latest:
                if (
                    not ultimaTelemetriaTanque
                    or tt_latest.fecha > ultimaTelemetriaTanque.fecha
                ):
                    asigTanque, ultimaTelemetriaTanque, compTanque = (
                        asig,
                        tt_latest,
                        tipo_comp,
                    )

            # Consultar consumos de riego
            riego_list = riegos_by_asig.get(asig.id, [])
            for r in riego_list:
                fecha_r_local = (
                    _to_timezone(r.fecha, dashboard_tz).replace(tzinfo=None)
                    if r.fecha
                    else None
                )
                if fecha_r_local:
                    date_key = fecha_r_local.strftime("%Y-%m-%d")
                    if (
                        date_key in consumoSemanalMap
                        and r.cantidad_agua_litros is not None
                    ):
                        consumoSemanalMap[date_key]["valor"] += float(
                            r.cantidad_agua_litros
                        )

                    if ultimoRiegoFecha is None or fecha_r_local > ultimoRiegoFecha:
                        ultimoRiegoFecha = fecha_r_local

                    if fecha_r_local >= inicioDeHoy:
                        riegosHoy += 1
                        if r.cantidad_agua_litros is not None:
                            litrosHoy += float(r.cantidad_agua_litros)

        # Finalizar mapeado semanal
        consumoSemanal = [
            {"label": d["label"], "valor": round(d["valor"], 1)}
            for d in consumoSemanalMap.values()
        ]

        # Mapear tanque
        tanqueData = None
        if asigTanque or fuente:
            capacidad_maxima = (
                float(fuente.capacidad_litros)
                if (fuente and fuente.capacidad_litros is not None)
                else 0.0
            )
            porcentaje_nivel = (
                float(ultimaTelemetriaTanque.porcentaje_nivel)
                if (
                    ultimaTelemetriaTanque
                    and ultimaTelemetriaTanque.porcentaje_nivel is not None
                )
                else 0.0
            )
            litros_actuales = (porcentaje_nivel / 100.0) * capacidad_maxima
            timeout_min = (
                (config_ctrl[0].duracion_riego_max_seg // 60)
                if (config_ctrl and config_ctrl[0].duracion_riego_max_seg is not None)
                else 10
            )

            # DETERMINAR SI EL DISPOSITIVO DEL TANQUE ESTÁ ACTIVO
            disp_tanque_act = False
            if asigTanque:
                disp_tanque_act = any(
                    a.activo
                    for a in asigs
                    if a.id_dispositivo == asigTanque.id_dispositivo
                )
            elif fuente:
                disp_tanque_act = any(
                    a.activo for a in asigs if a.id_fuente_agua == fuente.id
                )

            tanqueData = {
                "idTelemetria": str(ultimaTelemetriaTanque.id)
                if (ultimaTelemetriaTanque and ultimaTelemetriaTanque.id)
                else None,
                "nombre": fuente.nombre if fuente else "Depósito de agua",
                "litrosActuales": round(litros_actuales, 1),
                "litrosTotales": capacidad_maxima,
                "porcentaje": porcentaje_nivel,
                "sensorModelo": compTanque.nombre_modelo
                if compTanque
                else "Desconocido",
                "estadoNivel": ultimaTelemetriaTanque.estado_nivel
                if ultimaTelemetriaTanque
                else "Desconocido",
                "bombaEncendida": ultimaTelemetriaTanque.bomba_encendida
                if ultimaTelemetriaTanque
                else False,
                "timeoutMinutos": timeout_min,
                "dispositivoActivo": disp_tanque_act,
            }

        umbralAgua = None
        metricas_config_ids = {u.id_tipo_metrica for u in umbrales_c}
        metricas_config_map = (
            {
                m.id: m
                for m in data_repository.queryObtenerDatosDashboardTiposMetrica2(
                    db, metricas_config_ids
                )
            }
            if metricas_config_ids
            else {}
        )
        for u in umbrales_c:
            tipo_m = metricas_config_map.get(u.id_tipo_metrica)
            if tipo_m and tipo_m.codigo == "NIVEL_AGUA":
                umbralAgua = u
                break
        limiteConsumo = (
            float(umbralAgua.valor_maximo)
            if (umbralAgua and umbralAgua.valor_maximo is not None)
            else None
        )

        sensoresData = {
            "humedadSuelo": mapear_sensor_ultimo(
                asigHS,
                lecturasHS,
                compHS,
                metricas_por_codigo.get("HUM_SUELO") or metricHS,
                umbrales,
                umbrales_c,
                dashboard_tz,
            ),
            "humedadAmbiente": mapear_sensor_ultimo(
                asigHA,
                lecturasHA,
                compHA,
                metricas_por_codigo.get("HUM_AMB") or metricHA,
                umbrales,
                umbrales_c,
                dashboard_tz,
            ),
            "temperaturaSuelo": mapear_sensor_ultimo(
                asigTS,
                lecturasTS,
                compTS,
                metricas_por_codigo.get("TEMP_SUELO") or metricTS,
                umbrales,
                umbrales_c,
                dashboard_tz,
            ),
            "temperaturaAmbiente": mapear_sensor_ultimo(
                asigTA,
                lecturasTA,
                compTA,
                metricas_por_codigo.get("TEMP_AMB") or metricTA,
                umbrales,
                umbrales_c,
                dashboard_tz,
            ),
        }

        historialData = {
            "humedadSuelo": mapear_historial(asigHS, lecturasHS, dashboard_tz),
            "humedadAmbiente": mapear_historial(asigHA, lecturasHA, dashboard_tz),
            "temperaturaSuelo": mapear_historial(asigTS, lecturasTS, dashboard_tz),
            "temperaturaAmbiente": mapear_historial(asigTA, lecturasTA, dashboard_tz),
        }

        humedadSueloProm = None
        if sensoresData["humedadSuelo"]:
            humedadSueloProm = (
                sensoresData["humedadSuelo"]["ema"]
                if sensoresData["humedadSuelo"]["ema"] is not None
                else sensoresData["humedadSuelo"]["porcentaje"]
            )

        humedadAmbiental = None
        if sensoresData["humedadAmbiente"]:
            humedadAmbiental = (
                sensoresData["humedadAmbiente"]["ema"]
                if sensoresData["humedadAmbiente"]["ema"] is not None
                else sensoresData["humedadAmbiente"]["porcentaje"]
            )

        resumenDia = {
            "riegosHoy": riegosHoy,
            "litrosHoy": round(litrosHoy, 1),
            "ultimoRiego": _local_naive_to_timezone_iso(ultimoRiegoFecha, dashboard_tz),
            "humedadSueloProm": humedadSueloProm,
            "humedadAmbiental": humedadAmbiental,
        }

        result.append(
            {
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
                "resumenDia": resumenDia,
            }
        )

    return result


def obtener_datos_alertas(db: Session, userId: int, idCultivo: int) -> dict:
    usuario = data_repository.queryObtenerDatosAlertasUsuario(db, userId)
    user_tz = _get_timezone(usuario.zona_horaria if usuario else None)

    # 1. Umbrales
    umbrales_raw = data_repository.queryObtenerDatosAlertasUmbralesRaw(
        db, userId, idCultivo
    )

    if not umbrales_raw:
        # Seed default thresholds based on scientific plant recommendations (umbrales_planta)
        cultivo_db = data_repository.queryObtenerDatosAlertasCultivoDb(db, idCultivo)
        id_planta = cultivo_db.id_planta if cultivo_db else None

        umbrales_recomendados = []
        if id_planta:
            umbrales_recomendados = (
                data_repository.queryObtenerDatosAlertasUmbralesRecomendados(
                    db, id_planta
                )
            )

        tipos = data_repository.queryObtenerDatosAlertasTipos(db)
        for t in tipos:
            rec = next(
                (r for r in umbrales_recomendados if r.id_tipo_metrica == t.id), None
            )
            min_val = (
                float(rec.valor_minimo)
                if (rec and rec.valor_minimo is not None)
                else 10.0
            )
            max_val = (
                float(rec.valor_maximo)
                if (rec and rec.valor_maximo is not None)
                else 90.0
            )

            db_u = configuracion_umbrales(
                id_usuario=userId,
                id_cultivo=idCultivo,
                id_tipo_metrica=t.id,
                valor_minimo=min_val,
                valor_maximo=max_val,
            )
            session_repository.add(db, db_u)
        session_repository.commit(db)

        # Query again
        umbrales_raw = data_repository.queryObtenerDatosAlertasUmbralesRaw2(
            db, userId, idCultivo
        )

    umbrales = []
    tipo_metrica_ids = {u.id_tipo_metrica for u in umbrales_raw if u.id_tipo_metrica}
    tipo_metricas_alertas_map = (
        {
            m.id: m
            for m in data_repository.queryObtenerDatosAlertasTiposMetrica(
                db, tipo_metrica_ids
            )
        }
        if tipo_metrica_ids
        else {}
    )
    for u in umbrales_raw:
        tipo_m = tipo_metricas_alertas_map.get(u.id_tipo_metrica)
        umbrales.append(
            {
                "id": u.id,
                "nombre": tipo_m.nombre if tipo_m else "Métrica",
                "unidad": tipo_m.unidad if tipo_m else "",
                "min": float(u.valor_minimo) if u.valor_minimo is not None else 0.0,
                "max": float(u.valor_maximo) if u.valor_maximo is not None else 0.0,
            }
        )

    # 2. Alertas Activas (estado != 'resuelta')
    alertas_activas_raw = data_repository.queryObtenerDatosAlertasAlertasActivasRaw(
        db, idCultivo, userId
    )

    alertas_activas_tipo_ids = {
        a.id_tipo_alerta for a in alertas_activas_raw if a.id_tipo_alerta
    }
    alertas_activas_metrica_ids = {
        a.id_tipo_metrica for a in alertas_activas_raw if a.id_tipo_metrica
    }
    alertas_activas_asig_ids = {
        a.id_asignacion for a in alertas_activas_raw if a.id_asignacion
    }

    tipos_alerta_activas_map = (
        {
            t.id: t
            for t in data_repository.queryObtenerDatosAlertasTiposAlerta(
                db, alertas_activas_tipo_ids
            )
        }
        if alertas_activas_tipo_ids
        else {}
    )
    metricas_activas_map = (
        {
            m.id: m
            for m in data_repository.queryObtenerDatosAlertasTiposMetrica2(
                db, alertas_activas_metrica_ids
            )
        }
        if alertas_activas_metrica_ids
        else {}
    )
    asigs_activas_map = (
        {
            a.id: a
            for a in data_repository.queryObtenerDatosAlertasAsignacionesIot(
                db, alertas_activas_asig_ids
            )
        }
        if alertas_activas_asig_ids
        else {}
    )
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
            tipo_c = (
                tipo_comps_alertas_map.get(comp.id_tipo_componente) if comp else None
            )
            if tipo_c:
                sensor_nombre = tipo_c.nombre_modelo

        alertas_activas.append(
            {
                "id": str(a.id),
                "titulo": tipo_a.nombre if tipo_a else "Alerta",
                "mensaje": a.mensaje,
                "valor": float(a.valor_detectado)
                if a.valor_detectado is not None
                else None,
                "unidad": tipo_m.unidad if tipo_m else "",
                "severidad": tipo_a.severidad if tipo_a else "info",
                "sensor": sensor_nombre,
            }
        )

    # 3. Historial (Resueltas)
    historial_raw = data_repository.queryObtenerDatosAlertasHistorialRaw(
        db, idCultivo, userId
    )

    historial_tipo_ids = {h.id_tipo_alerta for h in historial_raw if h.id_tipo_alerta}
    historial_metrica_ids = {
        h.id_tipo_metrica for h in historial_raw if h.id_tipo_metrica
    }
    tipos_alerta_historial_map = (
        {
            t.id: t
            for t in data_repository.queryObtenerDatosAlertasTiposAlerta2(
                db, historial_tipo_ids
            )
        }
        if historial_tipo_ids
        else {}
    )
    metricas_historial_map = (
        {
            m.id: m
            for m in data_repository.queryObtenerDatosAlertasTiposMetrica3(
                db, historial_metrica_ids
            )
        }
        if historial_metrica_ids
        else {}
    )

    historial = []
    for h in historial_raw:
        tipo_a = tipos_alerta_historial_map.get(h.id_tipo_alerta)
        tipo_m = metricas_historial_map.get(h.id_tipo_metrica)

        h_local = _to_timezone(h.fecha, user_tz) if h.fecha else None
        fecha_str = h_local.strftime("%d/%m") if h_local else ""

        historial.append(
            {
                "id": str(h.id),
                "tipo": tipo_a.nombre if tipo_a else "Alerta",
                "valor": float(h.valor_detectado)
                if h.valor_detectado is not None
                else None,
                "unidad": tipo_m.unidad if tipo_m else "",
                "estado": "Resuelta",
                "fecha": fecha_str,
            }
        )

    return {
        "umbrales": umbrales,
        "alertasActivas": alertas_activas,
        "historial": historial,
    }


def obtener_datos_historico(
    db: Session, userId: int, idCultivo: int, dias: int = 30
) -> dict:
    usuario = data_repository.queryObtenerDatosHistoricoUsuario(db, userId)
    user_tz = _get_timezone(usuario.zona_horaria if usuario else None)
    fechaActual = datetime.now(user_tz).replace(tzinfo=None)

    is_hourly = dias <= 1

    if is_hourly:
        # dias == 0 -> 6 hours, dias == 1 -> 24 hours
        hours_count = 24 if dias == 1 else 6
        fechaLimite = (fechaActual - timedelta(hours=hours_count)).replace(
            minute=0, second=0, microsecond=0
        )
        fechaLimiteUtc = _local_naive_to_utc_naive(fechaLimite, user_tz)
    else:
        fechaLimite = (fechaActual - timedelta(days=dias)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        fechaLimiteUtc = _local_naive_to_utc_naive(fechaLimite, user_tz)

    asigs = data_repository.queryObtenerDatosHistoricoAsigs(db, userId, idCultivo)

    if not asigs:
        return {"chartData": [], "stats": None, "riegoLog": []}

    asignaciones_ids = [a.id for a in asigs]
    comps_map, tipo_comps_map, _ = _component_context_maps(db, asigs)

    hs_by_asig = _group_by_assignment(
        data_repository.queryObtenerDatosHistoricoHumedadSuelo(
            db, asignaciones_ids, fechaLimiteUtc
        )
    )
    ha_by_asig = _group_by_assignment(
        data_repository.queryObtenerDatosHistoricoHumedadAmbiente(
            db, asignaciones_ids, fechaLimiteUtc
        )
    )
    ts_by_asig = _group_by_assignment(
        data_repository.queryObtenerDatosHistoricoTemperaturaSuelo(
            db, asignaciones_ids, fechaLimiteUtc
        )
    )
    ta_by_asig = _group_by_assignment(
        data_repository.queryObtenerDatosHistoricoTemperaturaAmbiente(
            db, asignaciones_ids, fechaLimiteUtc
        )
    )

    data_por_dia = {}
    if is_hourly:
        for i in range(hours_count + 1):
            h = fechaLimite + timedelta(hours=i)
            key = h.strftime("%Y-%m-%d %H:00")
            label = h.strftime("%H:%M")
            data_por_dia[key] = {
                "label": label,
                "hs": [],
                "ha": [],
                "ts": [],
                "ta": [],
                "riegos": 0,
            }
    else:
        for i in range(dias + 1):
            d = fechaLimite + timedelta(days=i)
            key = d.strftime("%Y-%m-%d")
            meses_es = [
                "ene.",
                "feb.",
                "mar.",
                "abr.",
                "may.",
                "jun.",
                "jul.",
                "ago.",
                "sep.",
                "oct.",
                "nov.",
                "dic.",
            ]
            label = f"{meses_es[d.month - 1]} {d.day}"
            data_por_dia[key] = {
                "label": label,
                "hs": [],
                "ha": [],
                "ts": [],
                "ta": [],
                "riegos": 0,
            }

    stats_raw = {
        "hs": {
            "min": float("inf"),
            "max": float("-inf"),
            "sum": 0.0,
            "count": 0,
            "model": "No asignado",
        },
        "ha": {
            "min": float("inf"),
            "max": float("-inf"),
            "sum": 0.0,
            "count": 0,
            "model": "No asignado",
        },
        "ts": {
            "min": float("inf"),
            "max": float("-inf"),
            "sum": 0.0,
            "count": 0,
            "model": "No asignado",
        },
        "ta": {
            "min": float("inf"),
            "max": float("-inf"),
            "sum": 0.0,
            "count": 0,
            "model": "No asignado",
        },
    }

    def get_local_date_key(dt_utc):
        dt_local = (
            dt_utc.replace(tzinfo=pytz.utc).astimezone(user_tz).replace(tzinfo=None)
        )
        if is_hourly:
            return dt_local.strftime("%Y-%m-%d %H:00")
        else:
            return dt_local.strftime("%Y-%m-%d")

    for asig in asigs:
        comp = comps_map.get(asig.id_componente) if asig.id_componente else None
        tipo_c = tipo_comps_map.get(comp.id_tipo_componente) if comp else None

        raw_model = tipo_c.nombre_modelo if tipo_c else "Desconocido"
        clean_model = (
            raw_model.replace("Higrómetro ", "")
            .replace("Termómetro ", "")
            .replace(" Capacitivo", "")
        )

        hs_list = hs_by_asig.get(asig.id, [])
        if hs_list:
            stats_raw["hs"]["model"] = clean_model
            for l in hs_list:
                val = float(l.ema if l.ema is not None else l.valor)
                key = get_local_date_key(l.fecha)
                if key in data_por_dia:
                    data_por_dia[key]["hs"].append(val)
                if val < stats_raw["hs"]["min"]:
                    stats_raw["hs"]["min"] = val
                if val > stats_raw["hs"]["max"]:
                    stats_raw["hs"]["max"] = val
                stats_raw["hs"]["sum"] += val
                stats_raw["hs"]["count"] += 1

        ha_list = ha_by_asig.get(asig.id, [])
        if ha_list:
            stats_raw["ha"]["model"] = clean_model.replace(" (Humedad)", "")
            for l in ha_list:
                val = float(l.ema if l.ema is not None else l.valor)
                key = get_local_date_key(l.fecha)
                if key in data_por_dia:
                    data_por_dia[key]["ha"].append(val)
                if val < stats_raw["ha"]["min"]:
                    stats_raw["ha"]["min"] = val
                if val > stats_raw["ha"]["max"]:
                    stats_raw["ha"]["max"] = val
                stats_raw["ha"]["sum"] += val
                stats_raw["ha"]["count"] += 1

        ts_list = ts_by_asig.get(asig.id, [])
        if ts_list:
            stats_raw["ts"]["model"] = clean_model.replace(" Suelo", "")
            for l in ts_list:
                val = float(
                    l.ema
                    if l.ema is not None
                    else (
                        l.temperatura
                        if getattr(l, "temperatura", None) is not None
                        else l.valor
                    )
                )
                key = get_local_date_key(l.fecha)
                if key in data_por_dia:
                    data_por_dia[key]["ts"].append(val)
                if val < stats_raw["ts"]["min"]:
                    stats_raw["ts"]["min"] = val
                if val > stats_raw["ts"]["max"]:
                    stats_raw["ts"]["max"] = val
                stats_raw["ts"]["sum"] += val
                stats_raw["ts"]["count"] += 1

        ta_list = ta_by_asig.get(asig.id, [])
        if ta_list:
            stats_raw["ta"]["model"] = clean_model.replace(" (Temperatura)", "")
            for l in ta_list:
                val = float(
                    l.ema
                    if l.ema is not None
                    else (
                        l.temperatura
                        if getattr(l, "temperatura", None) is not None
                        else l.valor
                    )
                )
                key = get_local_date_key(l.fecha)
                if key in data_por_dia:
                    data_por_dia[key]["ta"].append(val)
                if val < stats_raw["ta"]["min"]:
                    stats_raw["ta"]["min"] = val
                if val > stats_raw["ta"]["max"]:
                    stats_raw["ta"]["max"] = val
                stats_raw["ta"]["sum"] += val
                stats_raw["ta"]["count"] += 1

    riegos_recientes = data_repository.queryObtenerDatosHistoricoRiegosRecientes(
        db, fechaLimiteUtc, asignaciones_ids
    )

    riego_log = []
    for r in riegos_recientes:
        key = get_local_date_key(r.fecha)
        if key in data_por_dia:
            data_por_dia[key]["riegos"] += 1

        origen_str = "Auto"
        color_str = "#22c55e"
        tipo = (r.tipo_riego or "").lower()
        if "manual" in tipo:
            origen_str = "Manual"
            color_str = "#f59e0b"
        elif "ml" in tipo:
            origen_str = "ML"
            color_str = "#a855f7"

        r_local = (
            r.fecha.replace(tzinfo=pytz.utc).astimezone(user_tz)
            if r.fecha
            else datetime.now(user_tz)
        )
        fecha_str = r_local.strftime("%d/%m %H:%M")

        riego_log.append(
            {
                "id": str(r.id),
                "fecha": r_local.isoformat(),
                "fechaStr": fecha_str,
                "origen": origen_str,
                "colorOrigen": color_str,
                "litros": f"{float(r.cantidad_agua_litros):.1f}"
                if r.cantidad_agua_litros is not None
                else "--",
            }
        )

    chart_data = []
    for key, d in data_por_dia.items():
        hs_avg = round(sum(d["hs"]) / len(d["hs"]), 1) if d["hs"] else None
        ha_avg = round(sum(d["ha"]) / len(d["ha"]), 1) if d["ha"] else None
        ts_avg = round(sum(d["ts"]) / len(d["ts"]), 1) if d["ts"] else None
        ta_avg = round(sum(d["ta"]) / len(d["ta"]), 1) if d["ta"] else None

        chart_data.append(
            {
                "fecha": key,
                "label": d["label"],
                "humedadSuelo": hs_avg,
                "humedadAmbiente": ha_avg,
                "temperaturaSuelo": ts_avg,
                "temperaturaAmbiente": ta_avg,
                "riegos": d["riegos"] if d["riegos"] > 0 else None,
            }
        )

    def format_stat(stat, key):
        count = stat["count"]
        return {
            "sensor": stat["model"],
            "min": round(stat["min"], 1)
            if count > 0 and stat["min"] != float("inf")
            else None,
            "prom": round(stat["sum"] / count, 1) if count > 0 else None,
            "max": round(stat["max"], 1)
            if count > 0 and stat["max"] != float("-inf")
            else None,
        }

    stats = {
        "humedadSuelo": format_stat(stats_raw["hs"], "hs"),
        "humedadAmbiente": format_stat(stats_raw["ha"], "ha"),
        "temperaturaAmbiente": format_stat(stats_raw["ta"], "ta"),
        "temperaturaSuelo": format_stat(stats_raw["ts"], "ts"),
    }

    return {"chartData": chart_data, "stats": stats, "riegoLog": riego_log[:20]}


def obtener_datos_ml(db: Session, userId: int, idCultivo: int) -> dict:
    usr_mod = data_repository.queryObtenerDatosMlUsrMod(db, userId, idCultivo)

    if not usr_mod:
        default_model = data_repository.queryObtenerDatosMlDefaultModel(db)
        if not default_model:
            default_model = data_repository.queryObtenerDatosMlDefaultModel2(db)
        id_mod = default_model.id_modelo if default_model else 1
        usr_mod = cultivo_modelo(
            id_usuario=userId, id_cultivo=idCultivo, id_modelo=id_mod, activo=False
        )
        session_repository.add(db, usr_mod)
        session_repository.commit(db)
        session_repository.refresh(db, usr_mod)

    modelo_activo = None
    if usr_mod:
        modelo_activo = data_repository.queryObtenerDatosMlModeloActivo(db, usr_mod)

    asigs = data_repository.queryObtenerDatosMlAsigs(db, userId, idCultivo)

    ids_asig = [a.id for a in asigs]

    hum_suelo = data_repository.queryObtenerDatosMlHumSuelo(db, ids_asig)
    hum_amb = data_repository.queryObtenerDatosMlHumAmb(db, ids_asig)
    temp_suelo = data_repository.queryObtenerDatosMlTempSuelo(db, ids_asig)
    temp_amb = data_repository.queryObtenerDatosMlTempAmb(db, ids_asig)
    usuario = data_repository.queryObtenerDatosMlUsuario(db, userId)
    user_tz = _get_timezone(usuario.zona_horaria if usuario else None)

    datos_historicos = []

    for idx, hs in enumerate(reversed(hum_suelo)):
        ha = hum_amb[len(hum_amb) - 1 - idx] if idx < len(hum_amb) else None
        ts = temp_suelo[len(temp_suelo) - 1 - idx] if idx < len(temp_suelo) else None
        ta = temp_amb[len(temp_amb) - 1 - idx] if idx < len(temp_amb) else None

        hs_local = (
            hs.fecha.replace(tzinfo=pytz.utc).astimezone(user_tz)
            if hs.fecha
            else datetime.now(user_tz)
        )
        hora_str = hs_local.strftime("%H:%M")

        datos_historicos.append(
            {
                "hora": hora_str,
                "humSuelo": float(
                    hs.porcentaje if hs.porcentaje is not None else hs.valor
                )
                if hs
                else 0.0,
                "humAmb": float(
                    ha.porcentaje
                    if (ha and ha.porcentaje is not None)
                    else (ha.valor if ha else 0.0)
                ),
                "tempSuelo": float(
                    ts.temperatura
                    if (ts and getattr(ts, "temperatura", None) is not None)
                    else (ts.valor if ts else 0.0)
                ),
                "tempAmb": float(
                    ta.temperatura
                    if (ta and getattr(ta, "temperatura", None) is not None)
                    else (ta.valor if ta else 0.0)
                ),
            }
        )

    umbrales = data_repository.queryObtenerDatosMlUmbrales(db, userId, idCultivo)

    umbral_minimo = 40.0
    for u in umbrales:
        tipo_m = data_repository.queryObtenerDatosMlTipoM(db, u)
        if tipo_m and "suelo" in tipo_m.nombre.lower():
            umbral_minimo = (
                float(u.valor_minimo) if u.valor_minimo is not None else 40.0
            )
            break

    # Consultar las últimas 15 predicciones de ML para este cultivo
    preds = data_repository.queryObtenerDatosMlPreds(db, userId, idCultivo)

    lista_predicciones = []
    for p in preds:
        r = data_repository.queryObtenerDatosMlR(db, p)

        riego_detalles = None
        if r:
            riego_detalles = {
                "duracion_segundos": r.duracion_segundos,
                "cantidad_agua_litros": float(r.cantidad_agua_litros)
                if r.cantidad_agua_litros is not None
                else None,
                "estado": r.estado,
                "motivo_cierre": r.motivo_cierre,
            }

        p_local = (
            p.fecha.replace(tzinfo=pytz.utc).astimezone(user_tz)
            if p.fecha
            else datetime.now(user_tz)
        )
        fecha_str = p_local.strftime("%d/%m")
        hora_str = p_local.strftime("%H:%M")

        vars_in = p.variables_entrada or {}

        lista_predicciones.append(
            {
                "id": p.id_prediccion,
                "fecha": fecha_str,
                "hora": hora_str,
                "variables": {
                    "humedad_suelo": vars_in.get("humedad_suelo"),
                    "humedad_ambiente": vars_in.get("humedad_ambiente"),
                    "temperatura_ambiente": vars_in.get("temperatura_ambiente"),
                    "temperatura_suelo": vars_in.get("temperatura_suelo"),
                },
                "recomendacion": p.recomendacion,
                "probabilidad": float(p.probabilidad)
                if p.probabilidad is not None
                else None,
                "ejecutado": p.accion_ejecutada,
                "riego_detalles": riego_detalles,
            }
        )

    # Obtener modelos compatibles con la planta del cultivo
    cultivo_db = data_repository.queryObtenerDatosMlCultivoDb(db, idCultivo)
    id_planta_filtro = cultivo_db.id_planta if cultivo_db else None

    modelos_db = data_repository.queryObtenerDatosMlModelosDb(db)
    modelos_compatibles = []
    for m in modelos_db:
        if (
            id_planta_filtro is not None
            and m.id_planta is not None
            and m.id_planta != id_planta_filtro
        ):
            continue
        modelos_compatibles.append(
            {
                "id_modelo": m.id_modelo,
                "nombre_modelo": m.nombre_modelo,
                "algoritmo": m.algoritmo,
                "descripcion": m.descripcion,
                "version": m.version,
                "precision_modelo": float(m.precision_modelo)
                if m.precision_modelo is not None
                else None,
                "activo": (modelo_activo and modelo_activo.id_modelo == m.id_modelo)
                if modelo_activo
                else False,
            }
        )

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
        "reduccion_estres": 0.0,
    }

    # 1. Obtener todos los riegos del cultivo
    riegos_all = data_repository.queryObtenerDatosMlRiegosAll(db, ids_asig)

    t_manual = None
    t_programado = None
    t_ml = None

    for r in riegos_all:
        tipo = (r.tipo_riego or "").lower()
        if "manual" in tipo and t_manual is None:
            t_manual = r.fecha
        elif "programado" in tipo and t_programado is None:
            t_programado = r.fecha
        elif ("ml" in tipo or "automatico_ml" in tipo) and t_ml is None:
            t_ml = r.fecha

    # 2. Definir rango de tiempos para cada fase y calcular consumo
    now_utc = datetime.utcnow()

    manual_total_litros = 0.0
    programado_total_litros = 0.0
    ml_total_litros = 0.0

    for r in riegos_all:
        vol = (
            float(r.cantidad_agua_litros) if r.cantidad_agua_litros is not None else 0.0
        )
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

    comparativa["manual_litros"] = (
        round(manual_total_litros / dias_manual, 1) if dias_manual > 0 else 0.0
    )
    comparativa["programado_litros"] = (
        round(programado_total_litros / dias_prog, 1) if dias_prog > 0 else 0.0
    )
    comparativa["ml_litros"] = (
        round(ml_total_litros / dias_ml, 1) if dias_ml > 0 else 0.0
    )

    # 3. Obtener estrés hídrico de cada fase
    hum_records = data_repository.queryObtenerDatosMlHumRecords(db, ids_asig)

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

    comparativa["manual_estres"] = (
        round((manual_stressed / manual_total_readings) * 100, 1)
        if manual_total_readings > 0
        else 0.0
    )
    comparativa["programado_estres"] = (
        round((prog_stressed / prog_total_readings) * 100, 1)
        if prog_total_readings > 0
        else 0.0
    )
    comparativa["ml_estres"] = (
        round((ml_stressed / ml_total_readings) * 100, 1)
        if ml_total_readings > 0
        else 0.0
    )

    # Ahorros
    if comparativa["manual_litros"] > 0:
        comparativa["ahorro_agua"] = round(
            (
                (comparativa["manual_litros"] - comparativa["ml_litros"])
                / comparativa["manual_litros"]
            )
            * 100,
            1,
        )
    if comparativa["manual_estres"] > 0:
        comparativa["reduccion_estres"] = round(
            (
                (comparativa["manual_estres"] - comparativa["ml_estres"])
                / comparativa["manual_estres"]
            )
            * 100,
            1,
        )

    return {
        "modelo": {
            "nombre": modelo_activo.nombre_modelo if modelo_activo else "Sin modelo",
            "algoritmo": modelo_activo.algoritmo
            if modelo_activo
            else "Algoritmo no definido",
            "version": modelo_activo.version if modelo_activo else "1.0.0",
            "mae": float(modelo_activo.precision_modelo)
            if (modelo_activo and modelo_activo.precision_modelo is not None)
            else 0.0,
            "activo": bool(usr_mod.activo) if usr_mod else False,
        },
        "modelos": modelos_compatibles,
        "historial": datos_historicos,
        "umbral": umbral_minimo,
        "predicciones": lista_predicciones,
        "comparativa_fases": comparativa,
    }


def obtener_datos_dashboard_admin(db: Session, userId: int | None = None) -> dict:
    from datetime import datetime, timedelta

    usuario = (
        data_repository.queryObtenerDatosDashboardAdminUsuarios(db, userId)
        if userId
        else None
    )
    admin_tz = _get_timezone(usuario.zona_horaria if usuario else None)
    fecha_actual = datetime.now(admin_tz).replace(tzinfo=None)
    fecha_limite_7d = fecha_actual - timedelta(days=7)

    # 1. Contadores (Métricas)
    total_usuarios = data_repository.queryObtenerDatosDashboardAdminTotalUsuarios(db)
    total_dispositivos = (
        data_repository.queryObtenerDatosDashboardAdminTotalDispositivos(db)
    )
    total_dispositivos_activos = (
        data_repository.queryObtenerDatosDashboardAdminTotalDispositivosActivos(db)
    )
    total_cultivos_activos = (
        data_repository.queryObtenerDatosDashboardAdminTotalCultivosActivos(db)
    )
    alertas_pendientes = (
        data_repository.queryObtenerDatosDashboardAdminAlertasPendientes(db)
    )

    metricas = {
        "total_usuarios": total_usuarios,
        "total_dispositivos": total_dispositivos,
        "total_dispositivos_activos": total_dispositivos_activos,
        "total_cultivos_activos": total_cultivos_activos,
        "alertas_pendientes": alertas_pendientes,
    }

    # 2. Obtener logs recientes (Últimos 50)
    db_logs = data_repository.queryObtenerDatosDashboardAdminDbLogs(db)
    logs_res = []
    for l in db_logs:
        user_name = "Sistema"
        if l.id_usuario:
            usr = data_repository.queryObtenerDatosDashboardAdminUsr(db, l)
            if usr:
                user_name = f"{usr.nombre} {usr.apellido or ''}".strip()

        logs_res.append(
            {
                "id": l.id,
                "id_usuario": l.id_usuario,
                "usuario_nombre": user_name,
                "accion": l.accion,
                "modulo": l.modulo,
                "descripcion": l.descripcion,
                "ip_acceso": l.ip_acceso,
                "fecha": _to_timezone_iso(l.fecha, admin_tz),
            }
        )

    # 3. Obtener últimas 50 predicciones de ML
    db_preds = data_repository.queryObtenerDatosDashboardAdminDbPreds(db)
    preds_res = []
    for p in db_preds:
        user_name = "Desconocido"
        if p.id_usuario:
            usr = data_repository.queryObtenerDatosDashboardAdminUsr2(db, p)
            if usr:
                user_name = usr.nombre

        cult_name = "Desconocido"
        if p.id_cultivo:
            cult = data_repository.queryObtenerDatosDashboardAdminCult(db, p)
            if cult:
                cult_name = cult.nombre_planta

        mod_name = "Modelo General"
        if p.id_modelo:
            mod = data_repository.queryObtenerDatosDashboardAdminMod(db, p)
            if mod:
                mod_name = mod.nombre_modelo

        preds_res.append(
            {
                "id": p.id_prediccion,
                "id_usuario": p.id_usuario,
                "id_cultivo": p.id_cultivo,
                "usuario_nombre": user_name,
                "cultivo_nombre": cult_name,
                "modelo_nombre": mod_name,
                "recomendacion": p.recomendacion,
                "probabilidad": float(p.probabilidad)
                if p.probabilidad is not None
                else 0.0,
                "accion_ejecutada": bool(p.accion_ejecutada),
                "fecha": _to_timezone_iso(p.fecha, admin_tz),
            }
        )

    # 4. Estadísticas de modelos de ML
    db_models = data_repository.queryObtenerDatosDashboardAdminDbModels(db)
    models_res = []
    for m in db_models:
        total_pred_model = (
            data_repository.queryObtenerDatosDashboardAdminTotalPredModel(db, m)
        )
        models_res.append(
            {
                "id": m.id_modelo,
                "nombre_modelo": m.nombre_modelo,
                "algoritmo": m.algoritmo,
                "precision_modelo": float(m.precision_modelo)
                if m.precision_modelo is not None
                else None,
                "precision_score": float(m.precision_score)
                if m.precision_score is not None
                else None,
                "recall_score": float(m.recall_score)
                if m.recall_score is not None
                else None,
                "f1_score": float(m.f1_score) if m.f1_score is not None else None,
                "es_default": bool(m.es_default),
                "predicciones_totales": total_pred_model,
            }
        )

    # 5. Consumo semanal de agua global (últimos 7 días)
    consumo_map = {}
    for i in range(6, -1, -1):
        d = fecha_actual - timedelta(days=i)
        date_key = d.strftime("%Y-%m-%d")
        label = d.strftime("%d/%m")
        consumo_map[date_key] = {"fecha": label, "litros": 0.0, "riegos": 0}

    inicio_de_limite = _local_naive_to_utc_naive(
        fecha_limite_7d.replace(hour=0, minute=0, second=0, microsecond=0),
        admin_tz,
    )
    riegos_globales = data_repository.queryObtenerDatosDashboardAdminRiegosGlobales(
        db, inicio_de_limite
    )
    for r in riegos_globales:
        r_local = (
            _to_timezone(r.fecha, admin_tz).replace(tzinfo=None) if r.fecha else None
        )
        if r_local:
            date_key = r_local.strftime("%Y-%m-%d")
            if date_key in consumo_map:
                if r.cantidad_agua_litros is not None:
                    consumo_map[date_key]["litros"] += float(r.cantidad_agua_litros)
                consumo_map[date_key]["riegos"] += 1

    chart_data = list(consumo_map.values())

    # 6. Obtener listas de usuarios y cultivos para filtros
    db_all_users = data_repository.queryObtenerDatosDashboardAdminDbAllUsers(db)
    users_filter = [
        {
            "id": u.id_usuario,
            "nombre": u.nombre,
            "apellido": u.apellido,
            "correo": u.correo,
        }
        for u in db_all_users
    ]

    db_all_crops = data_repository.queryObtenerDatosDashboardAdminDbAllCrops(db)
    crops_filter = [
        {
            "id": c.id_cultivo,
            "nombre_planta": c.nombre_planta,
            "id_usuario": c.id_usuario,
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


from typing import List

from fastapi import HTTPException
from sqlalchemy.orm import Session

from src.main.core.access import (
    require_assignment_access,
    require_crop_access,
    require_telemetry_access,
)
from src.main.dtos.dashboardDto import (
    BombaToggleModel,
    HorarioCreateModel,
    HorarioToggleModel,
    HorarioUpdateModel,
    ModoOperacionModel,
    NotifConfigItemModel,
    NotifConfigListModel,
    NotifConfigUpdateModel,
    RelayDurationUpdateModel,
    TelemetriaBombaToggleModel,
    UmbralesUpdateModel,
    ValvulaToggleModel,
)
from src.main.service import controlServ as control_service
from src.main.service import dashboardServ as dashboard_service


def get_dashboard_dataServ(db: Session = None, current_user=None):
    try:
        return dashboard_service.obtener_datos_dashboard(db, current_user.id_usuario)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error interno del servidor")


def get_cultivos_baseServ(db: Session = None, current_user=None):
    try:
        rows = data_repository.queryGetCultivosBaseRows(db, current_user)
        return [
            {"id": row.id_cultivo, "nombre_planta": row.nombre_planta} for row in rows
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error interno del servidor")


def get_alertas_data_endpointServ(
    idCultivo: int, db: Session = None, current_user=None
):
    require_crop_access(db, current_user, idCultivo)
    try:
        return dashboard_service.obtener_datos_alertas(
            db, current_user.id_usuario, idCultivo
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error interno del servidor")


def get_historico_data_endpointServ(
    idCultivo: int, dias: int = 30, db: Session = None, current_user=None
):
    require_crop_access(db, current_user, idCultivo)
    try:
        return dashboard_service.obtener_datos_historico(
            db, current_user.id_usuario, idCultivo, dias
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error interno del servidor")


def get_ml_dashboard_data_endpointServ(
    idCultivo: int, db: Session = None, current_user=None
):
    require_crop_access(db, current_user, idCultivo)
    try:
        return dashboard_service.obtener_datos_ml(
            db, current_user.id_usuario, idCultivo
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error interno del servidor")


def get_control_dataServ(idCultivo: int, db: Session = None, current_user=None):
    require_crop_access(db, current_user, idCultivo)
    try:
        return control_service.obtener_datos_control(
            db, current_user.id_usuario, idCultivo, current_user.id_rol
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error interno del servidor")


def set_modo_operacionServ(
    data: ModoOperacionModel, db: Session = None, current_user=None
):
    modo = data.modo.lower()
    if modo not in ["manual", "predictivo", "programado"]:
        raise HTTPException(
            status_code=400,
            detail="Modo inválido. Debe ser manual, predictivo o programado.",
        )
    require_assignment_access(db, current_user, data.idBomba)
    require_crop_access(db, current_user, data.idCultivo)
    try:
        return control_service.establecer_modo_operacion(
            db, current_user.id_usuario, data.idBomba, data.modo, data.idCultivo
        )
    except Exception as e:
        logger.exception("Error en establecer_modo_operacion")
        raise HTTPException(
            status_code=500, detail=f"Error interno del servidor: {str(e)}"
        )


def toggle_bomba_manualServ(
    data: BombaToggleModel, db: Session = None, current_user=None
):
    require_assignment_access(db, current_user, data.idBomba)
    try:
        return control_service.conmutar_bomba_manual(
            db, current_user.id_usuario, data.idBomba, data.encender
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Error en toggle_bomba_manual")
        raise HTTPException(
            status_code=500, detail=f"Error interno del servidor: {str(e)}"
        )


def toggle_valvula_manualServ(
    data: ValvulaToggleModel, db: Session = None, current_user=None
):
    require_assignment_access(db, current_user, data.idBomba)
    try:
        return control_service.conmutar_valvula_manual(
            db, current_user.id_usuario, data.idBomba, data.abrir
        )
    except Exception as e:
        logger.exception("Error en toggle_valvula_manual")
        raise HTTPException(
            status_code=500, detail=f"Error interno del servidor: {str(e)}"
        )


def update_max_relay_durationServ(
    data: RelayDurationUpdateModel, db: Session = None, current_user=None
):
    require_crop_access(db, current_user, data.idCultivo)
    try:
        return control_service.actualizar_tiempo_maximo_rele(
            db,
            current_user.id_usuario,
            data.idCultivo,
            data.duracionMaxMinutos,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def agregar_horarioServ(
    data: HorarioCreateModel, db: Session = None, current_user=None
):
    require_assignment_access(db, current_user, data.idBomba)
    try:
        return control_service.crear_horario_riego(
            db,
            current_user.id_usuario,
            data.idBomba,
            data.hora,
            data.duracionMin,
            data.dias,
            data.nombre,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error interno del servidor")


def editar_horarioServ(
    id_horario: int, data: HorarioUpdateModel, db: Session = None, current_user=None
):
    try:
        res = control_service.actualizar_horario_riego(
            db,
            current_user.id_usuario,
            id_horario,
            data.hora,
            data.duracionMin,
            data.dias,
            data.nombre,
        )
        if res is None:
            raise HTTPException(status_code=404, detail="Horario no encontrado.")
        return res
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error interno del servidor")


def toggle_horarioServ(
    id_horario: int, data: HorarioToggleModel, db: Session = None, current_user=None
):
    try:
        res = control_service.conmutar_horario_riego(
            db, current_user.id_usuario, id_horario, data.activo
        )
        if res is None:
            raise HTTPException(status_code=404, detail="Horario no encontrado.")
        return res
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error interno del servidor")


def eliminar_horarioServ(id_horario: int, db: Session = None, current_user=None):
    try:
        res = control_service.eliminar_horario_riego(
            db, current_user.id_usuario, id_horario
        )
        if res is None:
            raise HTTPException(status_code=404, detail="Horario no encontrado.")
        return res
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error interno del servidor")


def toggle_bomba_by_telemetriaServ(
    data: TelemetriaBombaToggleModel, db: Session = None, current_user=None
):
    require_telemetry_access(db, current_user, data.idTelemetria)
    try:
        res = control_service.conmutar_bomba_por_telemetria(
            db, current_user.id_usuario, data.idTelemetria, data.estado
        )
        if res is None:
            raise HTTPException(
                status_code=404, detail="Registro de telemetría no encontrado"
            )
        return res
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error interno del servidor")


def update_umbralesServ(
    data: UmbralesUpdateModel, db: Session = None, current_user=None
):
    require_crop_access(db, current_user, data.idCultivo)
    try:
        return control_service.actualizar_umbrales_riego(
            db, current_user.id_usuario, data.idCultivo, data.updates
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error interno del servidor")


def get_notif_configServ(db: Session = None, current_user=None):
    try:
        tipos = data_repository.queryGetNotifConfigTipos(db)

        has_config = False
        configs = []
        for t in tipos:
            pref = data_repository.queryGetNotifConfigPref(db, current_user, t)

            if pref:
                has_config = True

            configs.append(
                NotifConfigItemModel(
                    id_tipo_alerta=t.id,
                    nombre=t.nombre,
                    canal_email=pref.canal_email if pref else False,
                    canal_dashboard=pref.canal_dashboard if pref else False,
                    recordatorio_minutos=(
                        pref.recordatorio_minutos
                        if pref and pref.recordatorio_minutos
                        else (
                            15
                            if t.severidad in {"critico", "critica", "emergencia"}
                            else 30
                        )
                    ),
                )
            )

        return NotifConfigListModel(configs=configs, has_config=has_config)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error interno del servidor")


def update_notif_configServ(
    data: NotifConfigUpdateModel, db: Session = None, current_user=None
):
    try:
        from src.main.model.models import configuracion_notificaciones

        for u in data.updates:
            pref = data_repository.queryUpdateNotifConfigPref(db, current_user, u)

            if pref:
                pref.canal_email = u.canal_email
                pref.canal_dashboard = u.canal_dashboard
                pref.recordatorio_minutos = u.recordatorio_minutos
            else:
                pref = configuracion_notificaciones(
                    id_usuario=current_user.id_usuario,
                    id_tipo_alerta=u.id_tipo_alerta,
                    canal_email=u.canal_email,
                    canal_dashboard=u.canal_dashboard,
                    recordatorio_minutos=u.recordatorio_minutos,
                    activo=True,
                )
                session_repository.add(db, pref)

        session_repository.commit(db)
        return {"success": True}
    except Exception as e:
        session_repository.rollback(db)
        raise HTTPException(status_code=500, detail="Error interno del servidor")
