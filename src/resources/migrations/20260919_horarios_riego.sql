-- Migration: Horarios fijos de riego (HU-17)
CREATE TABLE IF NOT EXISTS horarios_riego (
    id                  SERIAL      PRIMARY KEY,
    id_asignacion       INTEGER     NOT NULL REFERENCES asignaciones_iot(id) ON DELETE CASCADE,
    id_usuario          INTEGER     NOT NULL REFERENCES usuarios(id),
    hora_inicio         TIME        NOT NULL,
    duracion_segundos   INTEGER     NOT NULL,
    dias_semana         JSON        NOT NULL DEFAULT '[]',
    activo              BOOLEAN     DEFAULT true,
    fecha_creacion      TIMESTAMP   DEFAULT now(),
    ultima_ejecucion    TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_horarios_riego_asignacion ON horarios_riego(id_asignacion);
CREATE INDEX IF NOT EXISTS idx_horarios_riego_usuario ON horarios_riego(id_usuario);

COMMENT ON TABLE horarios_riego IS 'Horarios fijos (hora, duracion, dias de la semana) que el scheduler ejecuta automaticamente.';
