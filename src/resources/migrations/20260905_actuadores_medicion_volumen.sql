-- Migracion aditiva: conserva las asignaciones y todo el historial existente.
ALTER TABLE tipos_dispositivo ADD COLUMN IF NOT EXISTS metodo_medicion VARCHAR(20);
UPDATE tipos_dispositivo SET metodo_medicion = 'proximidad',
    nombre = 'ESP32 (Actuador con proximidad)',
    descripcion = 'Bomba y sensor de proximidad: estima litros por cambio de nivel del tanque.'
WHERE id = 2 AND metodo_medicion IS NULL;
INSERT INTO tipos_dispositivo (id, nombre, descripcion, metodo_medicion)
SELECT COALESCE(MAX(id), 0) + 1, 'ESP32 (Actuador con flujometro)',
    'Valvula y YF-S201: mide volumen por pulsos y caudal en litros/minuto.', 'flujometro'
FROM tipos_dispositivo
HAVING NOT EXISTS (SELECT 1 FROM tipos_dispositivo WHERE metodo_medicion = 'flujometro');
SELECT setval(pg_get_serial_sequence('tipos_dispositivo', 'id'), (SELECT MAX(id) FROM tipos_dispositivo));

ALTER TABLE telemetria_tanque ADD COLUMN IF NOT EXISTS metodo_medicion VARCHAR(20) NOT NULL DEFAULT 'proximidad';
ALTER TABLE telemetria_tanque ALTER COLUMN distancia_cm DROP NOT NULL;
ALTER TABLE telemetria_tanque ADD COLUMN IF NOT EXISTS litros_riego NUMERIC(14,4) CHECK (litros_riego >= 0);
ALTER TABLE telemetria_tanque ADD COLUMN IF NOT EXISTS litros_acumulados NUMERIC(16,4) CHECK (litros_acumulados >= 0);
ALTER TABLE telemetria_tanque ADD COLUMN IF NOT EXISTS caudal_l_min NUMERIC(12,4) CHECK (caudal_l_min >= 0);
ALTER TABLE telemetria_tanque ADD COLUMN IF NOT EXISTS pulsos_riego BIGINT CHECK (pulsos_riego >= 0);
ALTER TABLE telemetria_tanque ADD COLUMN IF NOT EXISTS pulsos_por_litro NUMERIC(12,4) CHECK (pulsos_por_litro > 0);
ALTER TABLE ejecuciones_riego ADD COLUMN IF NOT EXISTS metodo_medicion VARCHAR(20);

-- Solo los registros que ya se marcaron no_aplica pertenecen al firmware directo.
UPDATE telemetria_tanque SET metodo_medicion = 'flujometro', distancia_cm = NULL
WHERE estado_nivel = 'no_aplica' AND metodo_medicion = 'proximidad';

INSERT INTO tipos_metrica (id, codigo, nombre, unidad, descripcion)
SELECT COALESCE(MAX(id), 0) + 1, 'CAUDAL', 'Caudal de riego', 'L/min',
    'Caudal medido por el flujometro; el volumen del ciclo se almacena en litros.'
FROM tipos_metrica
HAVING NOT EXISTS (SELECT 1 FROM tipos_metrica WHERE codigo = 'CAUDAL');
SELECT setval(pg_get_serial_sequence('tipos_metrica', 'id'), (SELECT MAX(id) FROM tipos_metrica));
INSERT INTO tipos_componente (id, nombre_modelo, categoria, id_tipo_metrica, descripcion)
SELECT COALESCE(MAX(id), 0) + 1, 'Flujometro YF-S201', 'sensor',
    (SELECT id FROM tipos_metrica WHERE codigo = 'CAUDAL' LIMIT 1),
    'Sensor de pulsos para medir caudal y volumen de agua utilizado.'
FROM tipos_componente
HAVING NOT EXISTS (SELECT 1 FROM tipos_componente WHERE nombre_modelo = 'Flujometro YF-S201');
SELECT setval(pg_get_serial_sequence('tipos_componente', 'id'), (SELECT MAX(id) FROM tipos_componente));
