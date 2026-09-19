"""Registra en la base de datos los modelos multi-cultivo entrenados por
mlTrainingServ.train_multicrop_models (ver `python -m src.main.service.mlTrainingServ --multicrop`).

Uso (con la base de datos levantada y accesible mediante las variables de
entorno del backend):

    python -m src.main.service.seedMulticropModelsServ

Es idempotente: si ya existe una `planta` o un `modelos_ml` para un cultivo,
actualiza sus métricas en vez de duplicarlo.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from src.main.db.databaseConexion import SessionLocal
from src.main.model.models import modelos_ml, plantas
from src.main.service.mlTrainingServ import MULTICROP_CROPS

logger = logging.getLogger(__name__)

ML_ROOT = Path(__file__).resolve().parents[2] / "resources" / "ml_artifacts"
REPORT_PATH = ML_ROOT / "training_report_multicrop.json"

# `tipo` conserva el slug en inglés (usado como clave interna y para el matching
# con Crop_Type del dataset y con la búsqueda de reentrenamiento por nombre/tipo);
# `nombre` es el nombre de la especie mostrado al usuario, en español.
CROP_NAME_ES = {
    "sugarcane": "Caña de azúcar",
    "rice": "Arroz",
    "maize": "Maíz",
    "wheat": "Trigo",
    "cotton": "Algodón",
    "potato": "Papa",
}


def _get_or_create_planta(db, crop: str) -> plantas:
    nombre_es = CROP_NAME_ES.get(crop, crop.capitalize())
    planta = (
        db.query(plantas)
        .filter(plantas.tipo.ilike(crop))
        .first()
    )
    if planta is None:
        planta = plantas(nombre=nombre_es, tipo=crop, descripcion=f"Cultivo de {nombre_es.lower()} (dataset multi-cultivo)")
        db.add(planta)
        db.flush()
        logger.info("Planta creada: %s (id=%s)", nombre_es, planta.id_planta)
    else:
        planta.nombre = nombre_es
    return planta


def _upsert_modelo(db, planta: plantas, crop: str, algorithm: str, metrics: dict) -> modelos_ml:
    nombre_es = CROP_NAME_ES.get(crop, crop.capitalize())
    algo_db_name = "RandomForest" if algorithm == "rf" else "XGBoost"
    folder = "Ramdom Forest" if algorithm == "rf" else "XGBoost"
    filename = f"modelo_riego_{crop}_{algorithm}.joblib"
    nombre_modelo = f"{algo_db_name} {nombre_es} (multi-cultivo)"

    modelo = (
        db.query(modelos_ml)
        .filter(modelos_ml.nombre_modelo == nombre_modelo)
        .first()
    )
    if modelo is None:
        modelo = modelos_ml(nombre_modelo=nombre_modelo)
        db.add(modelo)

    modelo.id_planta = planta.id_planta
    modelo.algoritmo = algo_db_name
    modelo.descripcion = (
        f"Modelo entrenado con etiqueta real de riego (Irrigation_Need) del dataset "
        f"multi-cultivo, cultivo {nombre_es.lower()}."
    )
    modelo.ruta_archivo = filename
    modelo.ruta = str((Path(folder) / filename))
    modelo.precision_modelo = round(metrics["accuracy"] * 100, 2)
    modelo.precision_score = round(metrics["precision"], 4)
    modelo.recall_score = round(metrics["recall"], 4)
    modelo.f1_score = round(metrics["f1"], 4)
    modelo.version = "1.0.0"
    modelo.estado = "activo"
    modelo.es_default = False
    db.flush()
    return modelo


def seed() -> None:
    if not REPORT_PATH.exists():
        raise FileNotFoundError(
            f"No se encontró {REPORT_PATH}. Ejecuta primero: "
            "python -m src.main.service.mlTrainingServ --multicrop"
        )
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    by_crop_algo = {(r["cultivo"], r["algoritmo"]): r for r in report}

    db = SessionLocal()
    try:
        for crop in MULTICROP_CROPS:
            planta = _get_or_create_planta(db, crop)
            for algorithm in ("rf", "xgb"):
                metrics = by_crop_algo.get((crop, algorithm))
                if not metrics:
                    logger.warning("Sin métricas para %s/%s, se omite", crop, algorithm)
                    continue
                modelo = _upsert_modelo(db, planta, crop, algorithm, metrics)
                logger.info(
                    "Registrado modelo %s (id=%s) para planta %s",
                    modelo.nombre_modelo,
                    modelo.id_modelo,
                    planta.nombre,
                )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    seed()
