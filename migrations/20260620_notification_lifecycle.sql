BEGIN;

ALTER TABLE alertas
    ADD COLUMN IF NOT EXISTS ultima_notificacion_en TIMESTAMP,
    ADD COLUMN IF NOT EXISTS proxima_notificacion_en TIMESTAMP,
    ADD COLUMN IF NOT EXISTS cantidad_notificaciones INT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS ultimo_valor_detectado NUMERIC(10,2);

ALTER TABLE configuracion_notificaciones
    ADD COLUMN IF NOT EXISTS recordatorio_minutos INT;

ALTER TABLE notificaciones
    ADD COLUMN IF NOT EXISTS tipo_evento VARCHAR(20) NOT NULL DEFAULT 'activacion',
    ADD COLUMN IF NOT EXISTS intento INT NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS intentado_en TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP;

CREATE INDEX IF NOT EXISTS idx_alertas_ciclo_activo
    ON alertas (id_usuario, id_asignacion, id_tipo_metrica, estado);

UPDATE configuracion_notificaciones AS configuracion
SET recordatorio_minutos = CASE
    WHEN tipo.severidad IN ('critico', 'critica', 'emergencia') THEN 15
    ELSE 30
END
FROM tipos_alerta AS tipo
WHERE tipo.id = configuracion.id_tipo_alerta
  AND configuracion.recordatorio_minutos IS NULL;

WITH duplicadas AS (
    SELECT id,
           ROW_NUMBER() OVER (
               PARTITION BY id_usuario, id_asignacion, id_tipo_metrica, id_tipo_alerta
               ORDER BY fecha DESC, id DESC
           ) AS posicion
    FROM alertas
    WHERE estado IN ('pendiente', 'activa')
)
UPDATE alertas
SET estado = 'resuelta',
    resuelta_en = COALESCE(resuelta_en, CURRENT_TIMESTAMP),
    comentario = CONCAT_WS(' ', comentario, 'Cerrada automáticamente al consolidar alertas duplicadas.')
WHERE id IN (SELECT id FROM duplicadas WHERE posicion > 1);

CREATE UNIQUE INDEX IF NOT EXISTS uq_alerta_condicion_activa
    ON alertas (id_usuario, id_asignacion, id_tipo_metrica, id_tipo_alerta)
    WHERE estado IN ('pendiente', 'activa');

COMMIT;
