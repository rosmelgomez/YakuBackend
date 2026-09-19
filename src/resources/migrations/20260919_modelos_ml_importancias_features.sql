-- Migration: Importancia de variables del modelo activo (HU-24)
ALTER TABLE modelos_ml ADD COLUMN IF NOT EXISTS importancias_features JSONB;

COMMENT ON COLUMN modelos_ml.importancias_features IS 'Peso relativo (feature_importances_) de cada variable de entrada en el modelo entrenado.';
