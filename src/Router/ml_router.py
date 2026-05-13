from functools import lru_cache
from pathlib import Path

import joblib
import pandas as pd
from fastapi import APIRouter, HTTPException

from ..Model.schemas import PrediccionRiegoModel

router = APIRouter(prefix="/ml", tags=["Machine Learning"])
MODELO_RIEGO_PATH = Path(__file__).resolve().parents[1] / "ML" / "modelo_riego.joblib"


@lru_cache(maxsize=1)
def cargar_modelo_riego():
    if not MODELO_RIEGO_PATH.exists():
        raise FileNotFoundError(f"No se encontro el modelo entrenado en {MODELO_RIEGO_PATH}")
    return joblib.load(MODELO_RIEGO_PATH)


@router.post("/prediccion")
def predecir_riego(data: PrediccionRiegoModel):
    try:
        modelo = cargar_modelo_riego()
        entrada = pd.DataFrame([
            {
                "humedad_suelo": data.humedad_suelo,
                "humedad_ambiente": data.humedad_ambiente,
                "temperatura_ambiente": data.temperatura_ambiente,
                "temperatura_suelo": data.temperatura_suelo,
            }
        ])

        prediccion = int(modelo.predict(entrada)[0])
        respuesta = {"riego": prediccion, "mensaje": "Riego activado" if prediccion == 1 else "Riego desactivado"}

        if hasattr(modelo, "predict_proba"):
            respuesta["probabilidad_riego"] = float(modelo.predict_proba(entrada)[0][1])

        return respuesta
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Error al consultar el modelo de riego") from exc
