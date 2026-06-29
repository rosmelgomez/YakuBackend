ALTER TABLE riego
    ADD COLUMN IF NOT EXISTS segundos_acumulados INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS fecha_inicio TIMESTAMP,
    ADD COLUMN IF NOT EXISTS fecha_fin TIMESTAMP;

UPDATE riego
SET fecha_inicio = COALESCE(fecha_inicio, fecha)
WHERE fecha_inicio IS NULL;

UPDATE riego
SET fecha_fin = COALESCE(fecha_fin, fecha),
    segundos_acumulados = CASE
        WHEN COALESCE(segundos_acumulados, 0) > 0 THEN segundos_acumulados
        WHEN estado IS TRUE THEN COALESCE(duracion_segundos, 0)
        ELSE 0
    END
WHERE estado IS TRUE OR fecha_fin IS NULL;
