-- Ciclo del cultivo: fecha de cosecha estimada, finalizacion y recordatorio.
-- Un cultivo finalizado conserva todo su historial (riegos, lecturas,
-- auditoria); solo libera sus dispositivos y deja de evaluarse.
ALTER TABLE cultivos ADD COLUMN IF NOT EXISTS fecha_cosecha_estimada DATE;
ALTER TABLE cultivos ADD COLUMN IF NOT EXISTS fecha_finalizacion TIMESTAMP;
ALTER TABLE cultivos ADD COLUMN IF NOT EXISTS cosecha_notificada BOOLEAN DEFAULT FALSE;

INSERT INTO tipos_alerta (id, codigo, nombre, descripcion, severidad, activo)
SELECT (SELECT COALESCE(MAX(id), 0) + 1 FROM tipos_alerta), 'COSECHA_CULTIVO', 'Fecha de cosecha alcanzada', 'Recordatorio al agricultor cuando su cultivo llega a la fecha de cosecha estimada para que lo finalice.', 'info', TRUE
WHERE NOT EXISTS (SELECT 1 FROM tipos_alerta WHERE codigo = 'COSECHA_CULTIVO');

SELECT setval(pg_get_serial_sequence('tipos_alerta', 'id'), (SELECT MAX(id) FROM tipos_alerta));
