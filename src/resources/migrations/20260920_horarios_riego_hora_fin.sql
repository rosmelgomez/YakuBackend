-- Migration: Horarios de riego definidos por rango "de hora a hora" (HU-17)
-- Antes solo se pedia hora de inicio + duracion en minutos; ahora el usuario
-- define directamente hora_inicio y hora_fin, y la duracion se calcula sola.
ALTER TABLE horarios_riego ADD COLUMN IF NOT EXISTS hora_fin TIME;

-- Backfill de filas existentes (si las hubiera) sumando la duracion ya guardada.
UPDATE horarios_riego
SET hora_fin = (hora_inicio + (duracion_segundos || ' seconds')::interval)::time
WHERE hora_fin IS NULL;

ALTER TABLE horarios_riego ALTER COLUMN hora_fin SET NOT NULL;
