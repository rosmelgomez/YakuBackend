from functools import lru_cache
from pathlib import Path
from typing import Any, Generator, List

import joblib
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..Model import crud
from ..Model.conexion import SessionLocal
from ..Model.model import modelos_ml
from ..Model.schemas import PrediccionRiegoModel
from .auth_router import get_current_user

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


def cargar_modelo_riego(db: Session, id_usuario: int | None = None):
    modelo = crud.obtener_modelo_activo(db, id_usuario=id_usuario)
    if modelo is None:
        raise FileNotFoundError("No hay un modelo activo seleccionado")

    nombre_resuelto = modelo.algoritmo or modelo.nombre_modelo
    ruta = resolver_ruta_modelo(nombre_resuelto)
    return cargar_modelo_riego_desde_ruta(str(ruta)), modelo, ruta


class ModelInfo(BaseModel):
    name: str
    path: str
    active: bool = False


@router.get("/models", response_model=List[ModelInfo])
def listar_modelos(db: Session = Depends(get_db)):
    """Lista modelos entrenados encontrados bajo `src/ML` con patrón `modelo_riego*.joblib`."""
    modelo_activo = crud.obtener_modelo_activo(db)
    activo_ruta = None
    if modelo_activo is not None:
        try:
            activo_ruta = resolver_ruta_modelo(modelo_activo.algoritmo or modelo_activo.nombre_modelo)
        except FileNotFoundError:
            activo_ruta = None
    encontrados = []
    for p in ML_ROOT.rglob("modelo_riego*.joblib"):
        encontrados.append(ModelInfo(name=p.name, path=str(p), active=(activo_ruta == p)))
    return encontrados


class ModelSelect(BaseModel):
    model_name: str


class ModelSelectionResponse(BaseModel):
    status: str
    selected: str
    model_id: int


@router.get("/models/active", response_model=ModelInfo)
def modelo_activo(db: Session = Depends(get_db)):
    modelo = crud.obtener_modelo_activo(db)
    if modelo is None:
        raise HTTPException(status_code=404, detail="No hay modelo activo")

    ruta = resolver_ruta_modelo(modelo.nombre_modelo)
    return ModelInfo(name=modelo.nombre_modelo, path=str(ruta), active=True)


@router.post("/models/select", response_model=ModelSelectionResponse)
def seleccionar_modelo(
    body: ModelSelect,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Selecciona un modelo por nombre y lo registra como activo para la predicción de riego."""
    try:
        source = resolver_ruta_modelo(body.model_name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    nombre_modelo, algoritmo = normalizar_modelo_seleccionado(body.model_name)
    try:
        modelo_guardado = crud.registrar_seleccion_modelo(
            db=db,
            id_usuario=current_user.id_usuario,
            nombre_modelo=nombre_modelo,
            algoritmo=algoritmo,
            descripcion=f"Modelo seleccionado desde {source.name}",
            version=None,
        )
        cargar_modelo_riego_desde_ruta.cache_clear()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {"status": "ok", "selected": source.name, "model_id": modelo_guardado.id_modelo}


def obtener_prediccion_riego(data: PrediccionRiegoModel, db: Session, id_usuario: int | None = None) -> dict[str, Any]:
    try:
        modelo, modelo_db, ruta = cargar_modelo_riego(db, id_usuario=id_usuario)
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

        crud.registrar_prediccion_ml(
            db=db,
            id_modelo=modelo_db.id_modelo,
            humedad_suelo=data.humedad_suelo,
            humedad_ambiente=data.humedad_ambiente,
            temperatura_ambiente=data.temperatura_ambiente,
            temperatura_suelo=data.temperatura_suelo,
            recomendacion=recomendacion,
            probabilidad=respuesta["probabilidad_riego"],
        )

        return respuesta
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Error al consultar el modelo de riego") from exc


@router.post("/prediccion")
def predecir_riego(data: PrediccionRiegoModel, db: Session = Depends(get_db)):
    return obtener_prediccion_riego(data, db)
