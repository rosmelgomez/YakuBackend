from functools import lru_cache
from pathlib import Path
from typing import Any, Generator, List

import joblib
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..services import crud
from ..models.database import SessionLocal
from ..models.models import modelos_ml
from ..schemas.schemas import PrediccionRiegoModel
from ..core.bff_auth import get_current_user_or_bff

router = APIRouter(prefix="/ml", tags=["Machine Learning"])
ML_ROOT = Path(__file__).resolve().parents[1] / "ML"
MODEL_ALIASES = {
    "randomforest": ("RandomForest", ML_ROOT / "Ramdom Forest" / "modelo_riego_rf.joblib"),
    "rf": ("RandomForest", ML_ROOT / "Ramdom Forest" / "modelo_riego_rf.joblib"),
    "xgboost": ("XGBoost", ML_ROOT / "XGBoost" / "modelo_riego_xgb.joblib"),
    "xgb": ("XGBoost", ML_ROOT / "XGBoost" / "modelo_riego_xgb.joblib"),
    "default": ("Default", ML_ROOT / "dataset" / "modelo_riego.joblib"),
}


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def resolver_ruta_modelo(nombre_modelo: str) -> Path:
    normalizado = nombre_modelo.strip().lower()
    alias = MODEL_ALIASES.get(normalizado)
    if alias is not None:
        ruta_alias = alias[1]
        if ruta_alias.exists():
            return ruta_alias

    candidato = Path(nombre_modelo)
    if candidato.is_file():
        return candidato

    matches = list(ML_ROOT.rglob(nombre_modelo))
    if matches:
        return matches[0]

    matches = list(ML_ROOT.rglob(f"{nombre_modelo}.joblib"))
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
    modelo = crud.obtener_modelo_activo(db, id_usuario=id_usuario, id_cultivo=id_cultivo)
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
    """Lista modelos de ML registrados en la base de datos indicando si están activos."""
    modelos_db = crud.listar_modelos_ml(db)
    modelo_activo_db = crud.obtener_modelo_activo(db, id_usuario=current_user.id_usuario, id_cultivo=id_cultivo)

    encontrados = []
    for m in modelos_db:
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
    modelo = crud.obtener_modelo_activo(db, id_usuario=current_user.id_usuario, id_cultivo=id_cultivo)
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
        modelo_guardado = crud.registrar_seleccion_modelo_por_id(
            db=db,
            id_usuario=current_user.id_usuario,
            id_modelo=id_modelo_ml,
            id_cultivo=id_cultivo
        )
        cargar_modelo_riego_desde_ruta.cache_clear()
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc)) from exc

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
            from ..models.models import usuarios
            primer_usuario = db.query(usuarios).order_by(usuarios.id_usuario.asc()).first()
            if primer_usuario:
                id_usuario = primer_usuario.id_usuario
            else:
                raise ValueError("No se encontraron usuarios registrados en la base de datos")

        modelo, modelo_db, ruta = cargar_modelo_riego(db, id_usuario=id_usuario, id_cultivo=id_cultivo)
        entrada = pd.DataFrame(
            [
                {
                    "humedad_suelo": data.humedad_suelo,
                    "humedad_ambiente": data.humedad_ambiente,
                    "temperatura_ambiente": data.temperatura_ambiente,
                    "temperatura_suelo": data.temperatura_suelo,
                }
            ]
        )

        prediccion = int(modelo.predict(entrada)[0])
        recomendacion = "regar" if prediccion == 1 else "no_regar"
        respuesta: dict[str, Any] = {
            "riego": prediccion,
            "mensaje": "Riego activado" if prediccion == 1 else "Riego desactivado",
            "modelo_activo": modelo_db.nombre_modelo,
            "ruta_modelo": str(ruta),
        }

        if hasattr(modelo, "predict_proba"):
            respuesta["probabilidad_riego"] = float(modelo.predict_proba(entrada)[0][1])
        else:
            respuesta["probabilidad_riego"] = None

        # Intentar buscar el cultivo activo del usuario
        if id_cultivo is None:
            from ..models.models import asignaciones_iot
            query_asig = db.query(asignaciones_iot).filter(
                asignaciones_iot.id_usuario == id_usuario,
                asignaciones_iot.activo == True
            )
            if id_dispositivo is not None:
                query_asig = query_asig.filter(asignaciones_iot.id_dispositivo == id_dispositivo)
            asig_db = query_asig.first()
            if asig_db:
                id_cultivo = asig_db.id_cultivo

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
            crud.registrar_prediccion_ml(
                db=db,
                id_usuario=id_usuario,
                id_modelo=modelo_db.id_modelo,
                variables_entrada={
                    "humedad_suelo": data.humedad_suelo,
                    "humedad_ambiente": data.humedad_ambiente,
                    "temperatura_ambiente": data.temperatura_ambiente,
                    "temperatura_suelo": data.temperatura_suelo,
                },
                recomendacion=recomendacion,
                probabilidad=respuesta["probabilidad_riego"],
                id_cultivo=id_cultivo,
                accion_ejecutada=accion_ejecutada,
                fuente_accion=fuente_accion,
            )

        return respuesta
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
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
