-- Reentrenamiento de los modelos de Lechuga (RandomForest y XGBoost).
--
-- Motivo: los modelos anteriores se entrenaron con una "humedad_suelo"
-- sintetica derivada de TDS (ppm) de un dataset hidroponico, normalizada al
-- rango ~280-520. El sensor real de produccion (esp32-s3.ino) envia
-- humedad_suelo como porcentaje genuino 0-100%. Esa discrepancia de escala
-- hacia que cualquier lectura real de campo cayera fuera de la distribucion
-- de entrenamiento, produciendo decisiones sin logica (ej. "NO REGAR" con
-- suelo real al 2.85% de humedad).
--
-- Se reentreno con un dataset real de humedad de suelo + riego (Pump Data
-- 0/1 medido, no una regla sintetica), reescalando la humedad de suelo cruda
-- a 0-100% con la misma semantica que el sensor real (mayor % = mas humedo).
-- Importancia de variables resultante: humedad_suelo ~99%, el resto <1% --
-- confirma que la humedad de suelo es, por mucho, la variable dominante
-- para decidir el riego, como es de esperar agronomicamente.
UPDATE modelos_ml SET
    descripcion = 'Modelo predictivo RandomForest para cultivo de Lechugas. Reentrenado con dataset real de humedad de suelo + riego (Pump Data), humedad de suelo reescalada a 0-100% para coincidir con el sensor real de produccion.',
    precision_modelo = 100.00,
    precision_score = 1.0000,
    recall_score = 1.0000,
    f1_score = 1.0000,
    version = '1.0.1',
    fecha_entrenamiento = '2026-09-21 00:00:00'
WHERE nombre_modelo = 'Random Forest Lechugas' AND algoritmo = 'RandomForest';

UPDATE modelos_ml SET
    descripcion = 'Modelo predictivo XGBoost para cultivo de Lechugas. Reentrenado con dataset real de humedad de suelo + riego (Pump Data), humedad de suelo reescalada a 0-100% para coincidir con el sensor real de produccion.',
    precision_modelo = 100.00,
    precision_score = 1.0000,
    recall_score = 1.0000,
    f1_score = 1.0000,
    version = '1.0.1',
    fecha_entrenamiento = '2026-09-21 00:00:00'
WHERE nombre_modelo = 'XGBoost Lechugas' AND algoritmo = 'XGBoost';
