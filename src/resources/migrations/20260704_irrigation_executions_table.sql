-- Migration: Add ejecuciones_riego table and new columns to riego
ALTER TABLE riego ADD COLUMN IF NOT EXISTS segundos_acumulados INT DEFAULT 0;
ALTER TABLE riego ADD COLUMN IF NOT EXISTS fecha_inicio TIMESTAMP;
ALTER TABLE riego ADD COLUMN IF NOT EXISTS fecha_fin TIMESTAMP;

CREATE TABLE IF NOT EXISTS ejecuciones_riego (
    id                   SERIAL       PRIMARY KEY,
    id_riego             BIGINT       NOT NULL REFERENCES riego(id) ON DELETE CASCADE,
    fecha_inicio         TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_fin            TIMESTAMP,
    distancia_inicial_cm NUMERIC(6,2),
    distancia_final_cm   NUMERIC(6,2),
    duracion_segundos    INT          DEFAULT 0,
    cantidad_agua_litros NUMERIC(10,2) DEFAULT 0.0,
    motivo_cierre        VARCHAR(50)
);

CREATE INDEX IF NOT EXISTS idx_ejecuciones_riego_riego ON ejecuciones_riego(id_riego);
CREATE INDEX IF NOT EXISTS idx_ejecuciones_riego_fecha ON ejecuciones_riego(fecha_inicio DESC);

COMMENT ON TABLE ejecuciones_riego IS 'Historial individual de arranques/paradas de bomba durante una sesion de riego.';
