-- Reentrenamiento de los modelos de Tomate (RandomForest y XGBoost).
--
-- Mismo problema y misma correccion que en
-- 20260921_reentrenar_modelos_lechuga.sql: la "humedad_suelo" de
-- entrenamiento anterior venia de un dataset con lecturas ADC crudas
-- (columna "Soil moisture" en rango ~400-700+), no un porcentaje 0-100%
-- como el que envia el sensor real de produccion (esp32-s3.ino).
--
-- No existe en el repo un dataset de tomate con etiqueta REAL de riego
-- (el dataset "tomato irrigation dataset.csv" solo trae variables
-- agronomicas -- evapotranspiracion, nutrientes, etc. -- sin una señal real
-- de encendido/apagado de bomba). Por eso se reutiliza el mismo dataset real
-- de humedad de suelo + riego (Pump Data) ya usado para Lechuga: a nivel de
-- sensor, la relacion humedad-de-suelo -> necesidad-de-riego es la misma
-- física independientemente del cultivo. Import ancia de variables
-- resultante identica a Lechuga: humedad_suelo ~99%, resto <1%.
UPDATE modelos_ml SET
    descripcion = 'Modelo predictivo RandomForest para cultivo de Tomates. Reentrenado con dataset real de humedad de suelo + riego (Pump Data), humedad de suelo reescalada a 0-100% para coincidir con el sensor real de produccion. No existe dataset real de riego especifico de tomate en el repo; se reutilizo el mismo dataset generico usado para Lechuga.',
    precision_modelo = 100.00,
    precision_score = 1.0000,
    recall_score = 1.0000,
    f1_score = 1.0000,
    version = '1.0.1',
    fecha_entrenamiento = '2026-09-21 00:00:00'
WHERE nombre_modelo = 'Random Forest Tomates' AND algoritmo = 'RandomForest';

UPDATE modelos_ml SET
    descripcion = 'Modelo predictivo XGBoost para cultivo de Tomates. Reentrenado con dataset real de humedad de suelo + riego (Pump Data), humedad de suelo reescalada a 0-100% para coincidir con el sensor real de produccion. No existe dataset real de riego especifico de tomate en el repo; se reutilizo el mismo dataset generico usado para Lechuga.',
    precision_modelo = 100.00,
    precision_score = 1.0000,
    recall_score = 1.0000,
    f1_score = 1.0000,
    version = '1.0.1',
    fecha_entrenamiento = '2026-09-21 00:00:00'
WHERE nombre_modelo = 'XGBoost Tomates' AND algoritmo = 'XGBoost';
