-- Migracion: Agregar columna offset_calibracion a la tabla asignaciones_iot
ALTER TABLE asignaciones_iot
ADD COLUMN IF NOT EXISTS offset_calibracion NUMERIC(6,2) DEFAULT 0;

UPDATE asignaciones_iot
SET offset_calibracion = 0
WHERE offset_calibracion IS NULL;
