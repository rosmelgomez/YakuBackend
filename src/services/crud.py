from datetime import datetime
from sqlalchemy.orm import Session

from ..db.models import (
    telemetria_tanque,
    dispositivos,
    componentes,
    asignaciones_iot,
    configuracion_tanque,
    historial_modelos,
    humedad_ambiente,
    humedad_suelo,
    modelos_ml,
    temperatura_ambiente,
    temperatura_suelo,
    cultivo_modelo,
)
from ..schemas.telemetria import RiegoDatosModel


def crear_humedad_suelo(
    db: Session,
    id_asignacion: int,
    valor: float | None,
    porcentaje: float | None,
    ema: float | None = None,
    desviacion: float | None = None,
    valido: bool | None = True,
    fecha: datetime | None = None,
) -> humedad_suelo:
    registro = humedad_suelo(
        id_asignacion=id_asignacion,
        valor=valor,
        porcentaje=porcentaje,
        ema=ema,
        desviacion=desviacion,
        valido=valido if valido is not None else True,
        fecha=fecha or datetime.now(),
    )
    db.add(registro)
    db.commit()
    db.refresh(registro)
    return registro


def crear_humedad_ambiente(
    db: Session,
    id_asignacion: int,
    valor: float | None,
    porcentaje: float | None,
    ema: float | None = None,
    desviacion: float | None = None,
    valido: bool | None = True,
    fecha: datetime | None = None,
) -> humedad_ambiente:
    registro = humedad_ambiente(
        id_asignacion=id_asignacion,
        valor=valor,
        porcentaje=porcentaje,
        ema=ema,
        desviacion=desviacion,
        valido=valido if valido is not None else True,
        fecha=fecha or datetime.now(),
    )
    db.add(registro)
    db.commit()
    db.refresh(registro)
    return registro


def crear_temperatura_ambiente(
    db: Session,
    id_asignacion: int,
    valor: float | None,
    temperatura: float | None,
    ema: float | None = None,
    desviacion: float | None = None,
    valido: bool | None = True,
    fecha: datetime | None = None,
) -> temperatura_ambiente:
    registro = temperatura_ambiente(
        id_asignacion=id_asignacion,
        valor=valor,
        temperatura=temperatura,
        ema=ema,
        desviacion=desviacion,
        valido=valido if valido is not None else True,
        fecha=fecha or datetime.now(),
    )
    db.add(registro)
    db.commit()
    db.refresh(registro)
    return registro


def crear_temperatura_suelo(
    db: Session,
    id_asignacion: int,
    valor: float | None,
    temperatura: float | None,
    ema: float | None = None,
    desviacion: float | None = None,
    valido: bool | None = True,
    fecha: datetime | None = None,
) -> temperatura_suelo:
    registro = temperatura_suelo(
        id_asignacion=id_asignacion,
        valor=valor,
        temperatura=temperatura,
        ema=ema,
        desviacion=desviacion,
        valido=valido if valido is not None else True,
        fecha=fecha or datetime.now(),
    )
    db.add(registro)
    db.commit()
    db.refresh(registro)
    return registro


def crear_datos_riego(
    db: Session,
    data: RiegoDatosModel,
) -> None:
    # Obtener los IDs de asignación entrantes
    ids = {
        data.humedad_suelo.id_asignacion,
        data.humedad_ambiente.id_asignacion,
        data.temperatura_ambiente.id_asignacion,
        data.temperatura_suelo.id_asignacion,
    }
    # Consultar cuáles de estos IDs realmente existen en asignaciones_iot
    valid_ids = {
        r[0] for r in db.query(asignaciones_iot.id).filter(asignaciones_iot.id.in_(ids)).all()
    }

    if data.humedad_suelo.id_asignacion in valid_ids:
        crear_humedad_suelo(
            db,
            id_asignacion=data.humedad_suelo.id_asignacion,
            valor=data.humedad_suelo.valor,
            porcentaje=data.humedad_suelo.porcentaje,
            ema=data.humedad_suelo.ema,
            desviacion=data.humedad_suelo.desviacion,
            valido=data.humedad_suelo.valido,
            fecha=data.humedad_suelo.fecha,
        )
    if data.humedad_ambiente.id_asignacion in valid_ids:
        crear_humedad_ambiente(
            db,
            id_asignacion=data.humedad_ambiente.id_asignacion,
            valor=data.humedad_ambiente.valor,
            porcentaje=data.humedad_ambiente.porcentaje,
            ema=data.humedad_ambiente.ema,
            desviacion=data.humedad_ambiente.desviacion,
            valido=data.humedad_ambiente.valido,
            fecha=data.humedad_ambiente.fecha,
        )
    if data.temperatura_ambiente.id_asignacion in valid_ids:
        crear_temperatura_ambiente(
            db,
            id_asignacion=data.temperatura_ambiente.id_asignacion,
            valor=data.temperatura_ambiente.valor,
            temperatura=data.temperatura_ambiente.temperatura,
            ema=data.temperatura_ambiente.ema,
            desviacion=data.temperatura_ambiente.desviacion,
            valido=data.temperatura_ambiente.valido,
            fecha=data.temperatura_ambiente.fecha,
        )
    if data.temperatura_suelo.id_asignacion in valid_ids:
        crear_temperatura_suelo(
            db,
            id_asignacion=data.temperatura_suelo.id_asignacion,
            valor=data.temperatura_suelo.valor,
            temperatura=data.temperatura_suelo.temperatura,
            ema=data.temperatura_suelo.ema,
            desviacion=data.temperatura_suelo.desviacion,
            valido=data.temperatura_suelo.valido,
            fecha=data.temperatura_suelo.fecha,
        )


def listar_humedad_suelo(db: Session) -> list[humedad_suelo]:
    return db.query(humedad_suelo).order_by(humedad_suelo.id.desc()).all()


def listar_humedad_ambiente(db: Session) -> list[humedad_ambiente]:
    return db.query(humedad_ambiente).order_by(humedad_ambiente.id.desc()).all()


def listar_temperatura_ambiente(db: Session) -> list[temperatura_ambiente]:
    return db.query(temperatura_ambiente).order_by(temperatura_ambiente.id.desc()).all()


def listar_temperatura_suelo(db: Session) -> list[temperatura_suelo]:
    return db.query(temperatura_suelo).order_by(temperatura_suelo.id.desc()).all()


def crear_telemetria_tanque(
    db: Session,
    id_asignacion: int,
    distancia_cm: float,
    estado_bomba: str,
    motivo_cierre: str | None = None,
    fecha: datetime | None = None,
) -> telemetria_tanque:
    asig = db.query(asignaciones_iot).filter(asignaciones_iot.id == id_asignacion).first()
    
    # 1. Obtener la fuente de agua asociada a la asignación del sensor o dispositivo
    fuente = None
    if asig and asig.id_fuente_agua is not None:
        from ..db.models import fuentes_agua
        fuente = db.query(fuentes_agua).filter(fuentes_agua.id == asig.id_fuente_agua).first()
    
    if fuente is None and asig:
        # Buscar en cualquier asignación del mismo dispositivo que tenga fuente de agua
        otro_asig = db.query(asignaciones_iot).filter(
            asignaciones_iot.id_dispositivo == asig.id_dispositivo,
            asignaciones_iot.id_fuente_agua != None
        ).first()
        if otro_asig:
            from ..db.models import fuentes_agua
            fuente = db.query(fuentes_agua).filter(fuentes_agua.id == otro_asig.id_fuente_agua).first()

    altura_tanque = 30.0  # valor por defecto si no está configurado
    if fuente is not None and fuente.altura_tanque_cm is not None:
        altura_tanque = float(fuente.altura_tanque_cm)

    # Buscar configuración del tanque (actuador) del dispositivo asignado
    config = None
    control_asig = None
    if asig:
        config = db.query(configuracion_tanque).filter(configuracion_tanque.id_asignacion == asig.id).first()
        if config is not None:
            control_asig = asig
        else:
            control_asig = db.query(asignaciones_iot).join(
                configuracion_tanque,
                configuracion_tanque.id_asignacion == asignaciones_iot.id,
            ).filter(
                asignaciones_iot.id_dispositivo == asig.id_dispositivo,
            ).first()
            if control_asig:
                config = db.query(configuracion_tanque).filter(
                    configuracion_tanque.id_asignacion == control_asig.id
                ).first()

    # Obtener estado de bomba anterior para detectar transiciones
    ultimo_registro = db.query(telemetria_tanque).filter(
        telemetria_tanque.id_asignacion == id_asignacion
    ).order_by(telemetria_tanque.id.desc()).first()
    bomba_anterior = ultimo_registro.bomba_encendida if ultimo_registro else False

    valvula_abierta = False
    bomba_encendida = (estado_bomba == "ON")
    if config is not None:
        config.bomba_encendida = (estado_bomba == "ON")
        db.add(config)
        valvula_abierta = config.valvula_abierta
        bomba_encendida = config.bomba_encendida

    nivel_agua_cm = max(altura_tanque - distancia_cm, 0.0)
    porcentaje_nivel = max(0.0, min((nivel_agua_cm / altura_tanque) * 100.0, 100.0))

    # Determinar estado_nivel
    estado_nivel = "optimo"
    if porcentaje_nivel <= 0.0:
        estado_nivel = "sin_agua"
    elif porcentaje_nivel < 20.0:
        estado_nivel = "critico"
    elif porcentaje_nivel < 50.0:
        estado_nivel = "bajo"

    registro = telemetria_tanque(
        id_asignacion=id_asignacion,
        distancia_cm=distancia_cm,
        nivel_agua_cm=nivel_agua_cm,
        porcentaje_nivel=porcentaje_nivel,
        estado_nivel=estado_nivel,
        valvula_abierta=valvula_abierta,
        bomba_encendida=bomba_encendida,
        fuente_control="automatico",
        fecha=fecha or datetime.now(),
    )
    db.add(registro)
    db.flush()

    # Lógica de registro en la tabla 'riego'
    event_asig = control_asig or asig
    if event_asig:
        from ..db.models import riego, predicciones_ml
        
        # 1. Transición de OFF a ON (Inicio de Riego)
        if bomba_encendida and not bomba_anterior:
            tipo = "manual"
            id_modelo = None
            id_pred = None
            
            # A. Verificar si el modo Predictivo (ML) está activo y hay predicción reciente
            from ..db.models import cultivo_modelo
            usr_mod = db.query(cultivo_modelo).filter(
                cultivo_modelo.id_usuario == event_asig.id_usuario,
                cultivo_modelo.id_cultivo == event_asig.id_cultivo,
                cultivo_modelo.activo == True
            ).first()
            
            if usr_mod:
                import datetime as dt
                hace_5_min = datetime.now() - dt.timedelta(minutes=5)
                pred = db.query(predicciones_ml).filter(
                    predicciones_ml.id_usuario == event_asig.id_usuario,
                    predicciones_ml.fecha >= hace_5_min,
                    predicciones_ml.recomendacion == "regar"
                ).order_by(predicciones_ml.id_prediccion.desc()).first()
                
                if pred:
                    tipo = "automatico_ml"
                    id_modelo = pred.id_modelo
                    id_pred = pred.id_prediccion
            
            # B. Si no es ML, verificar si coincide con un Riego Programado activo
            if tipo == "manual":
                from ..db.models import programacion_riego
                now = datetime.now()
                current_weekday = now.weekday()
                day_attrs = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo']
                day_attr = day_attrs[current_weekday]
                
                # Buscar programaciones activas hoy para este dispositivo
                programaciones_hoy = db.query(programacion_riego).filter(
                    programacion_riego.id_asignacion == event_asig.id,
                    programacion_riego.activo == True,
                    getattr(programacion_riego, day_attr) == True
                ).all()
                
                for pr in programaciones_hoy:
                    h_start = pr.hora_inicio
                    diff_mins = abs((now.hour * 60 + now.minute) - (h_start.hour * 60 + h_start.minute))
                    if diff_mins <= 2:
                        tipo = "programado"
                        break
            
            riego_activo = db.query(riego).filter(
                riego.id_asignacion == event_asig.id,
                riego.estado == False,
            ).order_by(riego.id.desc()).first()
            if riego_activo is None:
                nuevo_riego = riego(
                    id_asignacion=event_asig.id,
                    id_usuario=event_asig.id_usuario,
                    id_modelo=id_modelo,
                    id_prediccion=id_pred,
                    tipo_riego=tipo,
                    duracion_segundos=0,
                    cantidad_agua_litros=0.0,
                    estado=False,  # En progreso (activo)
                    fecha=datetime.now()
                )
                db.add(nuevo_riego)
            
        # 2. Transición de ON a OFF (Fin de Riego)
        elif not bomba_encendida and bomba_anterior:
            riego_activo = db.query(riego).filter(
                riego.id_asignacion == event_asig.id,
                riego.estado == False
            ).order_by(riego.id.desc()).first()
            
            if riego_activo:
                duracion = int((datetime.now() - riego_activo.fecha).total_seconds())
                
                # Calcular consumo de agua basado en el cambio de nivel del tanque
                import datetime as dt
                tel_inicio = db.query(telemetria_tanque).filter(
                    telemetria_tanque.id_asignacion == id_asignacion,
                    telemetria_tanque.bomba_encendida == True,
                    telemetria_tanque.fecha >= (riego_activo.fecha - dt.timedelta(seconds=5))
                ).order_by(telemetria_tanque.id.asc()).first()
                
                litros = 0.0
                if tel_inicio and fuente and fuente.capacidad_litros and fuente.altura_tanque_cm:
                    delta_distancia = float(distancia_cm) - float(tel_inicio.distancia_cm)
                    if delta_distancia > 0:
                        litros_por_cm = float(fuente.capacidad_litros) / float(fuente.altura_tanque_cm)
                        litros = delta_distancia * litros_por_cm
                
                riego_activo.duracion_segundos = max(duracion, 1)
                riego_activo.cantidad_agua_litros = max(litros, 0.0)
                riego_activo.estado = True  # Completado
                riego_activo.motivo_cierre = motivo_cierre or "sistema"
                db.add(riego_activo)

    db.commit()
    db.refresh(registro)
    return registro



def listar_telemetria_tanque(db: Session) -> list[telemetria_tanque]:
    return db.query(telemetria_tanque).order_by(telemetria_tanque.id.desc()).all()


def obtener_modelo_por_nombre(db: Session, nombre_modelo: str) -> modelos_ml | None:
    return db.query(modelos_ml).filter(modelos_ml.nombre_modelo == nombre_modelo).first()


def listar_modelos_ml(db: Session) -> list[modelos_ml]:
    return db.query(modelos_ml).order_by(modelos_ml.id_modelo.desc()).all()


def obtener_modelo_activo(db: Session, id_usuario: int | None = None, id_cultivo: int | None = None) -> modelos_ml | None:
    # 1. Intentar obtener el modelo asignado al usuario y cultivo específico (activo o inactivo)
    if id_usuario is not None and id_cultivo is not None:
        asignacion = db.query(cultivo_modelo).filter(
            cultivo_modelo.id_usuario == id_usuario,
            cultivo_modelo.id_cultivo == id_cultivo
        ).order_by(cultivo_modelo.fecha_asignacion.desc()).first()
        
        if asignacion is not None:
            modelo = db.query(modelos_ml).filter(modelos_ml.id_modelo == asignacion.id_modelo).first()
            if modelo is not None:
                return modelo

    # 2. Si no se especificó cultivo, intentar obtener cualquier modelo activo globalmente del usuario
    if id_usuario is not None and id_cultivo is None:
        asignacion = db.query(cultivo_modelo).filter(
            cultivo_modelo.id_usuario == id_usuario,
            cultivo_modelo.activo.is_(True)
        ).order_by(cultivo_modelo.fecha_asignacion.desc()).first()
        
        if asignacion is not None:
            modelo = db.query(modelos_ml).filter(modelos_ml.id_modelo == asignacion.id_modelo).first()
            if modelo is not None:
                return modelo

    # 3. Intentar obtener cualquier modelo activo globalmente en la tabla
    if id_cultivo is None:
        asignacion_global = db.query(cultivo_modelo).filter(
            cultivo_modelo.activo.is_(True)
        ).order_by(cultivo_modelo.fecha_asignacion.desc()).first()
        
        if asignacion_global is not None:
            modelo = db.query(modelos_ml).filter(modelos_ml.id_modelo == asignacion_global.id_modelo).first()
            if modelo is not None:
                return modelo

    # 4. Fallback al modelo marcado como default
    return db.query(modelos_ml).filter(modelos_ml.es_default.is_(True)).first()


def registrar_seleccion_modelo(
    db: Session,
    id_usuario: int,
    nombre_modelo: str,
    algoritmo: str | None = None,
    descripcion: str | None = None,
    version: str | None = None,
    id_cultivo: int | None = None,
) -> modelos_ml:
    modelo = obtener_modelo_por_nombre(db, nombre_modelo)
    if modelo is None:
        modelo = modelos_ml(
            nombre_modelo=nombre_modelo,
            algoritmo=algoritmo or "desconocido",
            descripcion=descripcion,
            version=version,
            estado="activo",
        )
        db.add(modelo)
        db.flush()
    else:
        modelo.estado = "activo"
        if algoritmo:
            modelo.algoritmo = algoritmo
        if descripcion is not None:
            modelo.descripcion = descripcion
        if version is not None:
            modelo.version = version

    query = db.query(cultivo_modelo).filter(
        cultivo_modelo.id_usuario == id_usuario,
        cultivo_modelo.activo.is_(True),
    )
    if id_cultivo is not None:
        query = query.filter(cultivo_modelo.id_cultivo == id_cultivo)
    query.update({cultivo_modelo.activo: False}, synchronize_session=False)

    asignacion = cultivo_modelo(id_usuario=id_usuario, id_cultivo=id_cultivo, id_modelo=modelo.id_modelo, activo=True)
    historial = historial_modelos(
        id_usuario=id_usuario,
        id_modelo=modelo.id_modelo,
        accion="seleccionado",
        descripcion=f"Modelo {nombre_modelo} seleccionado por el usuario para el cultivo {id_cultivo}"
    )

    db.add_all([asignacion, historial])
    db.commit()
    db.refresh(modelo)
    return modelo


def registrar_seleccion_modelo_por_id(
    db: Session,
    id_usuario: int,
    id_modelo: int,
    id_cultivo: int | None = None,
) -> modelos_ml:
    modelo = db.query(modelos_ml).filter(modelos_ml.id_modelo == id_modelo).first()
    if modelo is None:
        raise ValueError("Modelo ML no encontrado")

    query = db.query(cultivo_modelo).filter(
        cultivo_modelo.id_usuario == id_usuario,
        cultivo_modelo.activo.is_(True),
    )
    if id_cultivo is not None:
        query = query.filter(cultivo_modelo.id_cultivo == id_cultivo)
    query.update({cultivo_modelo.activo: False}, synchronize_session=False)

    asignacion = cultivo_modelo(id_usuario=id_usuario, id_cultivo=id_cultivo, id_modelo=id_modelo, activo=True)
    historial = historial_modelos(
        id_usuario=id_usuario,
        id_modelo=id_modelo,
        accion="seleccionado",
        descripcion=f"Modelo {modelo.nombre_modelo} seleccionado por el usuario por ID {id_modelo} para el cultivo {id_cultivo}"
    )

    db.add_all([asignacion, historial])
    db.commit()
    db.refresh(modelo)
    return modelo


def registrar_prediccion_ml(
    db: Session,
    id_usuario: int,
    id_modelo: int,
    variables_entrada: dict,
    recomendacion: str,
    probabilidad: float | None,
    id_cultivo: int | None = None,
    accion_ejecutada: bool | None = None,
    fuente_accion: str | None = None,
) -> None:
    from ..db.models import predicciones_ml

    prediccion = predicciones_ml(
        id_usuario=id_usuario,
        id_modelo=id_modelo,
        variables_entrada=variables_entrada,
        recomendacion=recomendacion,
        probabilidad=probabilidad,
        id_cultivo=id_cultivo,
        accion_ejecutada=accion_ejecutada,
        fuente_accion=fuente_accion,
    )
    db.add(prediccion)
    db.commit()
