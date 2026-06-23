"""Entrenamiento reproducible de los modelos de riego de Yaku.

El dataset disponible no contiene una etiqueta real de riego ni muestras separadas
por cultivo. Por ello, las etiquetas se generan con perfiles agronómicos explícitos.
Antes de usar estos modelos para decisiones críticas deben validarse con datos de
campo etiquetados por un especialista.
"""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier


logger = logging.getLogger(__name__)
FEATURES = [
    "humedad_suelo",
    "humedad_ambiente",
    "temperatura_ambiente",
    "temperatura_suelo",
    "etapa_crecimiento",
]
STAGES = {
    "initial stage": 0,
    "development stage": 1,
    "mid stage": 2,
    "last stage": 3,
}


@dataclass(frozen=True)
class CropProfile:
    humedad_suelo_max: float
    humedad_ambiente_min: float
    temperatura_ambiente_min: float
    temperatura_suelo_min: float


@dataclass(frozen=True)
class TrainingResult:
    algoritmo: str
    cultivo: str
    artefacto: str
    muestras: int
    positivos: int
    accuracy: float
    precision: float
    recall: float
    f1: float


CROP_PROFILES = {
    "tomato": CropProfile(350.0, 65.0, 25.0, 24.0),
    "lettuce": CropProfile(360.0, 60.0, 22.0, 21.0),
}


def load_training_data(dataset_path: Path) -> pd.DataFrame:
    data = pd.read_csv(dataset_path)
    data.columns = data.columns.str.strip()
    data = data.rename(columns={
        "Temperature [_ C]": "temperatura_ambiente",
        "Humidity [%]": "humedad_ambiente",
        "Soil moisture": "humedad_suelo",
        "Crop Coefficient stage": "etapa_original",
    })
    required = {"temperatura_ambiente", "humedad_ambiente", "humedad_suelo", "etapa_original"}
    missing = required.difference(data.columns)
    if missing:
        raise ValueError(f"El dataset no contiene las columnas requeridas: {sorted(missing)}")

    data["temperatura_suelo"] = data["temperatura_ambiente"] - 1.5
    data["etapa_crecimiento"] = data["etapa_original"].astype(str).str.strip().str.lower().map(STAGES)
    data = data.dropna(subset=FEATURES).copy()
    if data.empty:
        raise ValueError("El dataset no contiene filas válidas para entrenamiento")
    return data


def build_labels(data: pd.DataFrame, profile: CropProfile, crop: str) -> pd.Series:
    if crop == "lettuce":
        stage_adjustment = data["etapa_crecimiento"].map({0: -10.0, 1: 0.0, 2: 15.0, 3: -5.0}).fillna(0.0)
        dry_soil = data["humedad_suelo"] < (profile.humedad_suelo_max + stage_adjustment)
        climatic_demand = (
            (data["temperatura_ambiente"] > profile.temperatura_ambiente_min)
            | (data["humedad_ambiente"] < profile.humedad_ambiente_min)
            | (data["temperatura_suelo"] > profile.temperatura_suelo_min)
        )
        return (dry_soil & climatic_demand).astype(int)
    else:
        stage_adjustment = data["etapa_crecimiento"].map({0: -20.0, 1: 0.0, 2: 25.0, 3: -10.0}).fillna(0.0)
        dry_soil = data["humedad_suelo"] < (profile.humedad_suelo_max + stage_adjustment)
        climatic_demand = (
            (data["temperatura_ambiente"] > profile.temperatura_ambiente_min)
            | (data["humedad_ambiente"] < profile.humedad_ambiente_min)
            | (data["temperatura_suelo"] > profile.temperatura_suelo_min)
        )
        return (dry_soil & climatic_demand).astype(int)


def _make_model(algorithm: str, random_state: int):
    if algorithm == "rf":
        return RandomForestClassifier(
            n_estimators=200,
            min_samples_leaf=2,
            class_weight="balanced",
            random_state=random_state,
            n_jobs=-1,
        )
    if algorithm == "xgb":
        return XGBClassifier(
            n_estimators=200,
            max_depth=5,
            learning_rate=0.05,
            subsample=0.9,
            colsample_bytree=0.9,
            objective="binary:logistic",
            eval_metric="logloss",
            random_state=random_state,
            n_jobs=-1,
            verbosity=0,
        )
    raise ValueError(f"Algoritmo no soportado: {algorithm}")


def _artifact_path(output_root: Path, algorithm: str, crop: str) -> Path:
    folder = "Ramdom Forest" if algorithm == "rf" else "XGBoost"
    return output_root / folder / f"modelo_riego_{crop}_{algorithm}.joblib"


def train_models(
    dataset_path: Path,
    output_root: Path,
    algorithms: Iterable[str] = ("rf", "xgb"),
    crops: Iterable[str] = tuple(CROP_PROFILES),
    random_state: int = 42,
    test_size: float = 0.2,
) -> list[TrainingResult]:
    data = load_training_data(dataset_path)
    results: list[TrainingResult] = []

    for crop in crops:
        if crop not in CROP_PROFILES:
            raise ValueError(f"Cultivo no soportado: {crop}")
        labels = build_labels(data, CROP_PROFILES[crop], crop)
        if labels.nunique() != 2:
            raise ValueError(f"Las etiquetas de {crop} no contienen ambas clases")

        x_train, x_test, y_train, y_test = train_test_split(
            data[FEATURES],
            labels,
            test_size=test_size,
            random_state=random_state,
            stratify=labels,
        )
        for algorithm in algorithms:
            model = _make_model(algorithm, random_state)
            model.fit(x_train, y_train)
            predictions = model.predict(x_test)
            artifact = _artifact_path(output_root, algorithm, crop)
            artifact.parent.mkdir(parents=True, exist_ok=True)
            temporary = artifact.with_suffix(".joblib.tmp")
            joblib.dump(model, temporary)
            temporary.replace(artifact)

            result = TrainingResult(
                algoritmo=algorithm,
                cultivo=crop,
                artefacto=str(artifact.relative_to(output_root)),
                muestras=len(data),
                positivos=int(labels.sum()),
                accuracy=float(accuracy_score(y_test, predictions)),
                precision=float(precision_score(y_test, predictions, zero_division=0)),
                recall=float(recall_score(y_test, predictions, zero_division=0)),
                f1=float(f1_score(y_test, predictions, zero_division=0)),
            )
            results.append(result)
            logger.info("Modelo entrenado", extra={"algorithm": algorithm, "crop": crop, "f1": result.f1})

    report_path = output_root / "training_report.json"
    report_path.write_text(
        json.dumps([asdict(result) for result in results], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return results


def main() -> int:
    root = Path(__file__).resolve().parent / "ml_artifacts"
    parser = argparse.ArgumentParser(description="Entrena los modelos Random Forest y XGBoost de Yaku")
    parser.add_argument("--dataset", type=Path, default=root / "dataset" / "tomato irrigation dataset.csv")
    parser.add_argument("--output", type=Path, default=root)
    parser.add_argument("--algorithm", choices=("all", "rf", "xgb"), default="all")
    parser.add_argument("--crop", choices=("all", *CROP_PROFILES), default="all")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    algorithms = ("rf", "xgb") if args.algorithm == "all" else (args.algorithm,)
    crops = tuple(CROP_PROFILES) if args.crop == "all" else (args.crop,)
    train_models(args.dataset, args.output, algorithms=algorithms, crops=crops)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
