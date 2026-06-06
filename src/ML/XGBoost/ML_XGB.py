from pathlib import Path

import joblib
import pandas as pd
from xgboost import XGBClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import train_test_split

# Desactivar la notacion cientifica
pd.options.display.float_format = '{:.3f}'.format


BASE_DIR = Path(__file__).resolve().parent
# Prefer a dataset placed alongside this script (mirrors ML_RF),
# otherwise fall back to the shared dataset folder `src/ML/dataset`.
candidate_local = BASE_DIR / "tomato irrigation dataset.csv"
candidate_shared = BASE_DIR.parent / "dataset" / "tomato irrigation dataset.csv"

if candidate_local.exists():
    DATASET_ORIGEN = candidate_local
elif candidate_shared.exists():
    DATASET_ORIGEN = candidate_shared
else:
    # keep original path so pandas will raise a clear FileNotFoundError
    DATASET_ORIGEN = candidate_shared

# Output files are created inside this XGBoost folder so each algorithm keeps its own artifacts
DATASET_NUEVO = BASE_DIR / "dataset_con_riego_xgb.csv"
MODELO_SALIDA = BASE_DIR / "modelo_riego_xgb.joblib"


df = pd.read_csv(DATASET_ORIGEN)
df.columns = df.columns.str.strip()
df = df.rename(columns={
    "Temperature [_ C]": "temperatura_ambiente",
    "Humidity [%]": "humedad_ambiente",
    "Soil moisture": "humedad_suelo",
})

if "temperatura_ambiente" not in df.columns:
    raise ValueError("El dataset no contiene la columna de temperatura ambiente esperada.")

if "humedad_ambiente" not in df.columns:
    raise ValueError("El dataset no contiene la columna de humedad ambiente esperada.")

if "humedad_suelo" not in df.columns:
    raise ValueError("El dataset no contiene la columna de humedad de suelo esperada.")

# El CSV original no trae temperatura de suelo; se aproxima para mantener el esquema del modelo.
df["temperatura_suelo"] = (df["temperatura_ambiente"] - 1.5).round(3)

df["Riego"] = (
    (df["humedad_suelo"] < 350)
    & (
        (df["temperatura_ambiente"] > 25)
        | (df["humedad_ambiente"] < 65)
        | (df["temperatura_suelo"] > 24)
    )
).astype(int)

dataset_entrenamiento = df[
    [
        "humedad_suelo",
        "humedad_ambiente",
        "temperatura_ambiente",
        "temperatura_suelo",
        "Riego",
    ]
]

dataset_entrenamiento.to_csv(DATASET_NUEVO, index=False)

X = dataset_entrenamiento.drop(columns=["Riego"])
y = dataset_entrenamiento["Riego"]

X_train, X_test, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.2,
    random_state=42,
    stratify=y,
)

modelo = XGBClassifier(use_label_encoder=False, eval_metric='logloss', random_state=42)
modelo.fit(X_train, y_train)

y_pred = modelo.predict(X_test)

print(f"Accuracy: {accuracy_score(y_test, y_pred):.3f}")
print("Confusion matrix:")
print(confusion_matrix(y_test, y_pred))
print("Classification report:")
print(classification_report(y_test, y_pred))

joblib.dump(modelo, MODELO_SALIDA)
