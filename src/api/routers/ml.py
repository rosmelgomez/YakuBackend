from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, List

import joblib
import logging
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...services.repositories import ml as ml_repository
from ...db.database import SessionLocal
from ...db.models import modelos_ml
from ...schemas.ml import PrediccionRiegoModel
from ...core.bff_auth import get_current_user_or_bff
from ..dependencies import get_db
from ...ml_training import train_models

router = APIRouter(prefix="/ml", tags=["Machine Learning"])
logger = logging.getLogger(__name__)
ML_ROOT = Path(__file__).resolve().parents[2] / "ml_artifacts"
MODEL_ALIASES = {
    "randomforest": ("RandomForest", ML_ROOT / "Ramdom Forest" / "modelo_riego_tomato_rf.joblib"),
    "rf": ("RandomForest", ML_ROOT / "Ramdom Forest" / "modelo_riego_tomato_rf.joblib"),
    "xgboost": ("XGBoost", ML_ROOT / "XGBoost" / "modelo_riego_tomato_xgb.joblib"),
    "xgb": ("XGBoost", ML_ROOT / "XGBoost" / "modelo_riego_tomato_xgb.joblib"),
    "default": ("Default", ML_ROOT / "dataset" / "modelo_riego.joblib"),
}

def resolver_ruta_modelo(nombre_modelo: str) -> Path:
    normalizado = nombre_modelo.strip().lower()
    alias = MODEL_ALIASES.get(normalizado)
    if alias is not None:
        ruta_alias = alias[1]
        if ruta_alias.exists():
            return ruta_alias

    candidato = Path(nombre_modelo).name
    matches = list(ML_ROOT.rglob(candidato))
    if matches:
        return matches[0]

    matches = list(ML_ROOT.rglob(f"{candidato}.joblib"))
    if matches:
        return matches[0]

    raise FileNotFoundError(f"No se encontro el modelo entrenado {nombre_modelo} en {ML_ROOT}")


def normalizar_modelo_seleccionado(nombre_modelo: str) -> tuple[str, str]:
    normalizado = nombre_modelo.strip().lower()
    alias = MODEL_ALIASES.get(normalizado)
    if alias is not None:
        return alias[0], alias[0]

    candidato = Path(nombre_modelo)
    if candidato.is_file():
        lower_name = candidato.name.lower()
        if "xgb" in lower_name:
            return "XGBoost", "XGBoost"
        if "rf" in lower_name:
            return "RandomForest", "RandomForest"
        return candidato.stem, candidato.stem

    return nombre_modelo, nombre_modelo


@lru_cache(maxsize=16)
def cargar_modelo_riego_desde_ruta(model_path: str):
    ruta = Path(model_path)
    if not ruta.exists():
        raise FileNotFoundError(f"No se encontro el modelo entrenado en {ruta}")
    return joblib.load(ruta)


def cargar_modelo_riego(db: Session, id_usuario: int | None = None, id_cultivo: int | None = None):
    modelo = ml_repository.obtener_modelo_activo(db, id_usuario=id_usuario, id_cultivo=id_cultivo)
    if modelo is None:
        raise FileNotFoundError("No hay un modelo activo seleccionado")

    nombre_resuelto = modelo.ruta_archivo or modelo.algoritmo or modelo.nombre_modelo
    ruta = resolver_ruta_modelo(nombre_resuelto)
    return cargar_modelo_riego_desde_ruta(str(ruta)), modelo, ruta


class ModelInfo(BaseModel):
    id_modelo: int
    nombre_modelo: str
    algoritmo: str
    descripcion: str | None = None
    version: str | None = None
    precision_modelo: float | None = None
    activo: bool = False


@router.get("/models", response_model=List[ModelInfo])
def listar_modelos(
    id_cultivo: int | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """Lista modelos de ML registrados en la base de datos indicando si están activos y compatibles con el cultivo."""
    # Obtener el id_planta del cultivo para filtrar los modelos compatibles
    id_planta_filtro = None
    if id_cultivo is not None:
        from ...db.models import cultivos
        cultivo_db = db.query(cultivos).filter(cultivos.id_cultivo == id_cultivo).first()
        if cultivo_db:
            id_planta_filtro = cultivo_db.id_planta

    modelos_db = ml_repository.listar_modelos_ml(db)
    modelo_activo_db = ml_repository.obtener_modelo_activo(db, id_usuario=current_user.id_usuario, id_cultivo=id_cultivo)

    encontrados = []
    for m in modelos_db:
        # Filtrar modelos: si el cultivo tiene planta, solo mostrar modelos asociados a esa planta o globales (id_planta es NULL)
        if id_planta_filtro is not None and m.id_planta is not None and m.id_planta != id_planta_filtro:
            continue

        es_activo = False
        if modelo_activo_db and modelo_activo_db.id_modelo == m.id_modelo:
            es_activo = True

        encontrados.append(ModelInfo(
            id_modelo=m.id_modelo,
            nombre_modelo=m.nombre_modelo,
            algoritmo=m.algoritmo,
            descripcion=m.descripcion,
            version=m.version,
            precision_modelo=float(m.precision_modelo) if m.precision_modelo is not None else None,
            activo=es_activo
        ))
    return encontrados


class ModelSelect(BaseModel):
    model_name: str


class ModelSelectionResponse(BaseModel):
    status: str
    selected: str
    model_id: int


@router.get("/models/active", response_model=ModelInfo)
def modelo_activo(
    id_cultivo: int | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """Obtiene los detalles del modelo de ML activo para el usuario actual y cultivo."""
    modelo = ml_repository.obtener_modelo_activo(db, id_usuario=current_user.id_usuario, id_cultivo=id_cultivo)
    if modelo is None:
        raise HTTPException(status_code=404, detail="No hay modelo activo para el usuario")

    return ModelInfo(
        id_modelo=modelo.id_modelo,
        nombre_modelo=modelo.nombre_modelo,
        algoritmo=modelo.algoritmo,
        descripcion=modelo.descripcion,
        version=modelo.version,
        precision_modelo=float(modelo.precision_modelo) if modelo.precision_modelo is not None else None,
        activo=True
    )


@router.post("/models/select/{id_modelo_ml}", response_model=ModelSelectionResponse)
def seleccionar_modelo(
    id_modelo_ml: int, 
    id_cultivo: int | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """Selecciona un modelo de ML por su ID y lo registra como activo para el usuario y cultivo."""
    try:
        modelo_guardado = ml_repository.registrar_seleccion_modelo_por_id(
            db=db,
            id_usuario=current_user.id_usuario,
            id_modelo=id_modelo_ml,
            id_cultivo=id_cultivo
        )
        cargar_modelo_riego_desde_ruta.cache_clear()
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Error interno del servidor") from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Error interno del servidor") from exc

    return {
        "status": "ok",
        "selected": modelo_guardado.nombre_modelo,
        "model_id": modelo_guardado.id_modelo
    }


def obtener_prediccion_riego(
    data: PrediccionRiegoModel,
    db: Session,
    id_usuario: int | None = None,
    id_dispositivo: int | None = None,
    id_cultivo: int | None = None,
    accion_ejecutada: bool | None = None,
    fuente_accion: str | None = None,
    persistir: bool = True,
) -> dict[str, Any]:
    try:
        if id_usuario is None:
            from ...db.models import usuarios
            primer_usuario = db.query(usuarios).order_by(usuarios.id_usuario.asc()).first()
            if primer_usuario:
                id_usuario = primer_usuario.id_usuario
            else:
                raise ValueError("No se encontraron usuarios registrados en la base de datos")

        # Intentar buscar el cultivo activo del usuario
        if id_cultivo is None:
            from ...db.models import asignaciones_iot
            query_asig = db.query(asignaciones_iot).filter(
                asignaciones_iot.id_usuario == id_usuario,
                asignaciones_iot.activo == True
            )
            if id_dispositivo is not None:
                query_asig = query_asig.filter(asignaciones_iot.id_dispositivo == id_dispositivo)
            asig_db = query_asig.first()
            if asig_db:
                id_cultivo = asig_db.id_cultivo

        modelo, modelo_db, ruta = cargar_modelo_riego(db, id_usuario=id_usuario, id_cultivo=id_cultivo)
        
        # Verificar cuántas características espera el modelo
        n_features = 4
        if hasattr(modelo, "n_features_in_"):
            n_features = modelo.n_features_in_
        elif hasattr(modelo, "feature_names_in_"):
            n_features = len(modelo.feature_names_in_)

        etapa_num = 1  # Por defecto: crecimiento (vegetativo)
        if id_cultivo is not None:
            from ...db.models import cultivos
            cultivo_db = db.query(cultivos).filter(cultivos.id_cultivo == id_cultivo).first()
            if cultivo_db and cultivo_db.etapa_crecimiento:
                etapas_dict = {
                    "semillero": 0, "sowing": 0,
                    "crecimiento": 1, "vegetative": 1,
                    "floracion": 2, "flowering": 2,
                    "cosecha": 3, "harvest": 3
                }
                etapa_str = str(cultivo_db.etapa_crecimiento).strip().lower()
                etapa_num = etapas_dict.get(etapa_str, 1)

        if n_features >= 13:
            features_dict = {
                "humedad_suelo": data.humedad_suelo,
                "humedad_ambiente": data.humedad_ambiente,
                "temperatura_ambiente": data.temperatura_ambiente,
                "temperatura_suelo": data.temperatura_suelo,
                "etapa_crecimiento": etapa_num,
                "ph_suelo": 6.5,
                "carbono_organico": 1.0,
                "conductividad_electrica": 1.5,
                "lluvia": 0.0,
                "horas_sol": 8.0,
                "velocidad_viento": 10.0,
                "mulch_yes": 0,
                "riego_previo": 0.0,
            }
        elif n_features == 5:
            features_dict = {
                "humedad_suelo": data.humedad_suelo,
                "humedad_ambiente": data.humedad_ambiente,
                "temperatura_ambiente": data.temperatura_ambiente,
                "temperatura_suelo": data.temperatura_suelo,
                "etapa_crecimiento": etapa_num,
            }
        else:
            features_dict = {
                "humedad_suelo": data.humedad_suelo,
                "humedad_ambiente": data.humedad_ambiente,
                "temperatura_ambiente": data.temperatura_ambiente,
                "temperatura_suelo": data.temperatura_suelo,
            }

        entrada = pd.DataFrame([features_dict])

        prediccion = int(modelo.predict(entrada)[0])
        recomendacion = "regar" if prediccion == 1 else "no_regar"
        respuesta: dict[str, Any] = {
            "riego": prediccion,
            "recomendacion": recomendacion,
            "mensaje": "Riego activado" if prediccion == 1 else "Riego desactivado",
            "id_modelo": modelo_db.id_modelo,
            "modelo_activo": modelo_db.nombre_modelo,
            "ruta_modelo": str(ruta),
            "variables": features_dict,
        }

        if hasattr(modelo, "predict_proba"):
            respuesta["probabilidad_riego"] = float(modelo.predict_proba(entrada)[0][1])
        else:
            respuesta["probabilidad_riego"] = None
        respuesta["probabilidad"] = respuesta["probabilidad_riego"]

        if recomendacion == "regar":
            if accion_ejecutada is None:
                accion_ejecutada = True
            if fuente_accion is None:
                fuente_accion = "sistema_ml"
        else:
            if accion_ejecutada is None:
                accion_ejecutada = False
            if fuente_accion is None:
                fuente_accion = "sistema_ml"

        if persistir:
            prediccion_db = ml_repository.registrar_prediccion_ml(
                db=db,
                id_usuario=id_usuario,
                id_modelo=modelo_db.id_modelo,
                variables_entrada=features_dict,
                recomendacion=recomendacion,
                probabilidad=respuesta["probabilidad_riego"],
                id_cultivo=id_cultivo,
                accion_ejecutada=accion_ejecutada,
                fuente_accion=fuente_accion,
            )
            respuesta["id_prediccion"] = prediccion_db.id_prediccion
            respuesta["fecha"] = prediccion_db.fecha.isoformat() if prediccion_db.fecha else None
        else:
            respuesta["id_prediccion"] = None
            respuesta["fecha"] = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

        return respuesta
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail="Error interno del servidor") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Error al consultar el modelo de riego") from exc


@router.post("/prediccion")
def predecir_riego(
    data: PrediccionRiegoModel,
    id_cultivo: int | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    return obtener_prediccion_riego(
        data, db, id_usuario=current_user.id_usuario, id_cultivo=id_cultivo, persistir=False
    )


def tarea_reentrenamiento(db_session_factory, current_user_id: int):
    db = db_session_factory()
    try:
        dataset_path = ML_ROOT / "dataset" / "tomato irrigation dataset.csv"
        training_result = train_models(
            dataset_path,
            ML_ROOT,
            algorithms=("rf",),
            crops=("tomato",),
        )[0]
        accuracy = training_result.accuracy

        model_record = db.query(modelos_ml).filter(modelos_ml.algoritmo == "RandomForest").first()
        if not model_record:
            model_record = modelos_ml(
                nombre_modelo="Random Forest Climatológico",
                algoritmo="RandomForest",
                descripcion="Modelo Random Forest reentrenado con datos históricos del huerto.",
                ruta_archivo="modelo_riego_tomato_rf.joblib",
                precision_modelo=accuracy,
                version="1.1.0",
                estado="activo",
                creado_por=current_user_id,
                fecha_entrenamiento=datetime.now()
            )
            db.add(model_record)
        else:
            v_parts = model_record.version.split('.') if model_record.version else ["1", "0", "0"]
            try:
                v_parts[-1] = str(int(v_parts[-1]) + 1)
            except ValueError:
                v_parts[-1] = "1"
            nueva_version = ".".join(v_parts)
            
            model_record.precision_modelo = accuracy
            model_record.version = nueva_version
            model_record.fecha_entrenamiento = datetime.now()
            db.add(model_record)

        db.flush()
        from ...db.models import historial_modelos
        historial = historial_modelos(
            id_usuario=current_user_id,
            id_modelo=model_record.id_modelo,
            accion="reentrenado",
            descripcion=f"Modelo Random Forest reentrenado con éxito. Precisión: {accuracy:.3f}. Versión {model_record.version}."
        )
        db.add(historial)
        db.commit()

        cargar_modelo_riego_desde_ruta.cache_clear()
        logger.info("Reentrenamiento de IA completado", extra={"accuracy": accuracy})
    except Exception as err:
        db.rollback()
        logger.exception("Fallo en reentrenamiento de IA")
    finally:
        db.close()


@router.post("/models/retrain")
def reentrenar_modelo_ia(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """
    Encola una tarea en segundo plano para reentrenar el modelo Random Forest.
    """
    if current_user.id_rol != 1:
        raise HTTPException(status_code=403, detail="Solo administradores pueden reentrenar modelos.")

    background_tasks.add_task(tarea_reentrenamiento, SessionLocal, current_user.id_usuario)

    return {"status": "ok", "message": "Reentrenamiento del modelo encolado con éxito en segundo plano."}


class DbTrainingRequest(BaseModel):
    crop: str = "tomato"
    algorithm: str = "rf"


def ejecutar_entrenamiento_db(db_session_factory, crop: str, algorithm: str, current_user_id: int):
    db = db_session_factory()
    try:
        from sqlalchemy import text, func
        # 1. Resolver id_planta del cultivo
        from ...db.models import plantas, modelos_ml, historial_modelos
        from ...ml_training import CROP_PROFILES, FEATURES, TRAINING_REQUIRED_COLUMNS, build_labels, _make_model, load_training_data
        
        crop_norm = crop.strip().lower()
        if crop_norm == "tomato":
            nombre_busqueda = "Tomate"
        elif crop_norm == "lettuce":
            nombre_busqueda = "Lechuga"
        else:
            nombre_busqueda = crop
            
        planta_db = db.query(plantas).filter(
            (func.lower(plantas.nombre).like(f"%{nombre_busqueda.lower()}%")) |
            (func.lower(plantas.tipo).like(f"%{nombre_busqueda.lower()}%"))
        ).first()
        
        id_planta = planta_db.id_planta if planta_db else None
        
        # 2. Consultar datos de telemetria en base de datos
        sql = """
        SELECT 
            date_trunc('hour', hs.fecha) as fecha_hora,
            AVG(hs.valor) as humedad_suelo,
            AVG(ha.valor) as humedad_ambiente,
            AVG(ta.temperatura) as temperatura_ambiente,
            AVG(ts.temperatura) as temperatura_suelo
        FROM humedad_suelo hs
        JOIN asignaciones_iot a ON hs.id_asignacion = a.id
        JOIN cultivos c ON a.id_cultivo = c.id
        LEFT JOIN humedad_ambiente ha ON ha.id_asignacion = a.id AND date_trunc('hour', ha.fecha) = date_trunc('hour', hs.fecha)
        LEFT JOIN temperatura_ambiente ta ON ta.id_asignacion = a.id AND date_trunc('hour', ta.fecha) = date_trunc('hour', hs.fecha)
        LEFT JOIN temperatura_suelo ts ON ts.id_asignacion = a.id AND date_trunc('hour', ts.fecha) = date_trunc('hour', hs.fecha)
        WHERE c.id_planta = :id_planta OR :id_planta IS NULL
        GROUP BY date_trunc('hour', hs.fecha)
        ORDER BY fecha_hora ASC
        """
        
        params = {"id_planta": id_planta}
        result = db.execute(text(sql), params).fetchall()
        
        # 3. Cargar dataset
        if len(result) < 50:
            logger.info("Pocos datos en base de datos. Usando dataset predeterminado para el cultivo.")
            dataset_path = ML_ROOT / "dataset" / "tomato irrigation dataset.csv"
            df_clean = load_training_data(dataset_path)
        else:
            logger.info(f"Cargados {len(result)} registros de telemetría desde la base de datos.")
            df_db = pd.DataFrame(result, columns=["fecha_hora", "humedad_suelo", "humedad_ambiente", "temperatura_ambiente", "temperatura_suelo"])
            df_db["etapa_crecimiento"] = 1
            df_clean = df_db.dropna(subset=TRAINING_REQUIRED_COLUMNS).copy()
            
        # 4. Generar etiquetas de entrenamiento
        profile = CROP_PROFILES.get(crop_norm)
        if not profile:
            from ...ml_training import CropProfile
            profile = CropProfile(350.0, 65.0, 25.0, 24.0)
            
        labels = build_labels(df_clean, profile, crop_norm)
        
        # 5. Partición
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
        
        X = df_clean[FEATURES]
        y = labels
        
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y if y.nunique() == 2 else None
        )
        
        # 6. Entrenar modelo
        model = _make_model(algorithm, random_state=42)
        model.fit(X_train, y_train)
        
        preds = model.predict(X_test)
        acc = float(accuracy_score(y_test, preds))
        prec = float(precision_score(y_test, preds, zero_division=0))
        rec = float(recall_score(y_test, preds, zero_division=0))
        f1 = float(f1_score(y_test, preds, zero_division=0))
        
        # 7. Guardar modelo físicamente con nombre único
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        algorithm_name = "rf" if algorithm == "rf" else "xgb"
        filename = f"modelo_riego_{crop_norm}_{algorithm_name}_{timestamp}.joblib"
        folder = "Ramdom Forest" if algorithm == "rf" else "XGBoost"
        
        output_dir = ML_ROOT / folder
        output_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = output_dir / filename
        
        joblib.dump(model, artifact_path)
        logger.info(f"Modelo guardado físicamente en {artifact_path}")
        
        # 8. Guardar registro en la base de datos (NUEVO REGISTRO)
        version_num = "2.0.0"
        ultimo_modelo = db.query(modelos_ml).filter(
            modelos_ml.algoritmo == ("RandomForest" if algorithm == "rf" else "XGBoost"),
            modelos_ml.id_planta == id_planta
        ).order_by(modelos_ml.id_modelo.desc()).first()
        
        if ultimo_modelo and ultimo_modelo.version:
            v_parts = ultimo_modelo.version.split('.')
            try:
                v_parts[-1] = str(int(v_parts[-1]) + 1)
                version_num = ".".join(v_parts)
            except ValueError:
                version_num = "2.0.0"
                
        algo_db_name = "RandomForest" if algorithm == "rf" else "XGBoost"
        crop_display = crop_norm.capitalize()
        
        model_record = modelos_ml(
            id_planta=id_planta,
            nombre_modelo=f"{algo_db_name} {crop_display} - BD {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            algoritmo=algo_db_name,
            descripcion=f"Modelo entrenado dinámicamente desde telemetría de BD para {crop_display}.",
            ruta_archivo=filename,
            ruta=str(artifact_path.relative_to(ML_ROOT.parent)),
            precision_modelo=acc,
            precision_score=prec,
            recall_score=rec,
            f1_score=f1,
            version=version_num,
            es_default=False,
            estado="activo",
            creado_por=current_user_id,
            fecha_entrenamiento=datetime.now()
        )
        
        db.add(model_record)
        db.flush()
        
        historial = historial_modelos(
            id_usuario=current_user_id,
            id_modelo=model_record.id_modelo,
            accion="entrenado",
            descripcion=f"Modelo {algo_db_name} ({crop_display}) entrenado desde base de datos. Métricas - Accuracy: {acc:.3f}, Precision: {prec:.3f}, Recall: {rec:.3f}, F1: {f1:.3f}. Archivo: {filename}."
        )
        db.add(historial)
        db.commit()
        
        cargar_modelo_riego_desde_ruta.cache_clear()
        logger.info(f"Entrenamiento completado y guardado en BD con ID {model_record.id_modelo}")
        
    except Exception as err:
        db.rollback()
        logger.exception("Fallo en entrenamiento desde base de datos")
    finally:
        db.close()


@router.post("/models/train-db")
def entrenar_desde_db(
    request: DbTrainingRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """
    Encola una tarea en segundo plano para entrenar un modelo a partir de los datos históricos de telemetría de la base de datos.
    Cada entrenamiento genera un nuevo registro persistido en la base de datos y un archivo de modelo físico único.
    """
    if current_user.id_rol != 1:
        raise HTTPException(status_code=403, detail="Solo administradores pueden entrenar modelos.")

    background_tasks.add_task(
        ejecutar_entrenamiento_db,
        SessionLocal,
        request.crop,
        request.algorithm,
        current_user.id_usuario
    )

    return {
        "status": "ok",
        "message": f"Entrenamiento del modelo ({request.algorithm}) para {request.crop} iniciado en segundo plano."
    }


@router.post("/predict-live/{id_cultivo}")
def ejecutar_prediccion_en_vivo(
    id_cultivo: int,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user_or_bff)
):
    try:
        from src.db.models import asignaciones_iot, dispositivos
        from src.services.irrigation import find_pump_assignment

        # Buscar la asignacion real de bomba/configuracion_tanque para este cultivo.
        # En un mismo dispositivo pueden existir asignaciones de nivel, bomba y valvula.
        asig = find_pump_assignment(db, current_user.id_usuario, id_cultivo)

        if not asig:
            raise HTTPException(status_code=400, detail="No se encontro una asignacion de bomba para este cultivo.")

        sensor_asigs = db.query(asignaciones_iot).join(dispositivos).filter(
            asignaciones_iot.id_cultivo == id_cultivo,
            dispositivos.id_tipo == 1
        ).all()
        sensor_asig_ids = [sa.id for sa in sensor_asigs]

        if not sensor_asig_ids:
            raise HTTPException(status_code=400, detail="No se encontraron asignaciones de sensores para este cultivo.")

        from src.db.models import humedad_suelo, humedad_ambiente, temperatura_ambiente, temperatura_suelo
        h_suelo = db.query(humedad_suelo).filter(humedad_suelo.id_asignacion.in_(sensor_asig_ids)).order_by(humedad_suelo.id.desc()).first()
        h_amb = db.query(humedad_ambiente).filter(humedad_ambiente.id_asignacion.in_(sensor_asig_ids)).order_by(humedad_ambiente.id.desc()).first()
        t_amb = db.query(temperatura_ambiente).filter(temperatura_ambiente.id_asignacion.in_(sensor_asig_ids)).order_by(temperatura_ambiente.id.desc()).first()
        t_suelo = db.query(temperatura_suelo).filter(temperatura_suelo.id_asignacion.in_(sensor_asig_ids)).order_by(temperatura_suelo.id.desc()).first()

        pred_input = PrediccionRiegoModel(
            humedad_suelo=float(h_suelo.valor) if h_suelo and h_suelo.valor is not None else 0.0,
            humedad_ambiente=float(h_amb.valor) if h_amb and h_amb.valor is not None else 0.0,
            temperatura_ambiente=float(t_amb.temperatura) if t_amb and t_amb.temperatura is not None else 0.0,
            temperatura_suelo=float(t_suelo.temperatura) if t_suelo and t_suelo.temperatura is not None else 0.0,
        )

        resultado = obtener_prediccion_riego(
            data=pred_input,
            db=db,
            id_usuario=current_user.id_usuario,
            id_cultivo=id_cultivo,
            id_dispositivo=asig.id_dispositivo
        )

        if resultado.get("recomendacion") == "regar":
            from src.services.irrigation import start_irrigation
            start_irrigation(
                db=db,
                assignment=asig,
                irrigation_type="automatico_ml",
                model_id=resultado.get("id_modelo"),
                prediction_id=resultado.get("id_prediccion")
            )

        return {
            "status": "ok",
            "recomendacion": resultado.get("recomendacion"),
            "probabilidad": resultado.get("probabilidad"),
            "fecha": resultado.get("fecha"),
            "variables": resultado.get("variables"),
            "nombre_modelo": resultado.get("modelo_activo")
        }
    except HTTPException:
        raise
    except FileNotFoundError as fnf_exc:
        db.rollback()
        logger.warning(f"Archivo de modelo no encontrado en prediccion ML en vivo: {fnf_exc}")
        raise HTTPException(status_code=400, detail=str(fnf_exc))
    except ValueError as val_exc:
        db.rollback()
        logger.warning(f"Error de validacion o de seguridad en prediccion ML en vivo: {val_exc}")
        raise HTTPException(status_code=400, detail=str(val_exc))
    except Exception as exc:
        db.rollback()
        logger.exception("Error ejecutando prediccion ML en vivo", extra={"id_cultivo": id_cultivo, "user_id": getattr(current_user, "id_usuario", None)})
        raise HTTPException(status_code=500, detail="Error ejecutando prediccion ML en vivo") from exc
