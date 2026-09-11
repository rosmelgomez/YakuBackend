-- Normaliza fuentes sin modificar IDs, asignaciones ni historial.
ALTER TABLE fuentes_agua DROP CONSTRAINT IF EXISTS check_tanque_dims;
ALTER TABLE fuentes_agua DROP CONSTRAINT IF EXISTS ck_fuentes_agua_tipo;
ALTER TABLE fuentes_agua DROP CONSTRAINT IF EXISTS ck_fuentes_agua_config;
UPDATE fuentes_agua SET tipo = 'conexion_directa' WHERE lower(trim(tipo)) IN ('manguera', 'conexion_directa');
UPDATE fuentes_agua SET tipo = 'tanque' WHERE lower(trim(tipo)) = 'tanque';
UPDATE fuentes_agua SET capacidad_litros = NULL, altura_tanque_cm = NULL, altura_seguridad_cm = NULL WHERE tipo = 'conexion_directa';
ALTER TABLE fuentes_agua ADD CONSTRAINT ck_fuentes_agua_tipo CHECK (tipo IN ('tanque', 'conexion_directa'));
ALTER TABLE fuentes_agua ADD CONSTRAINT ck_fuentes_agua_config CHECK ((tipo = 'conexion_directa' AND capacidad_litros IS NULL AND altura_tanque_cm IS NULL AND altura_seguridad_cm IS NULL) OR (tipo = 'tanque' AND capacidad_litros IS NOT NULL AND capacidad_litros > 0 AND capacidad_litros <= 99999999.99 AND altura_tanque_cm IS NOT NULL AND altura_tanque_cm > 0 AND altura_tanque_cm <= 9999.99 AND (altura_seguridad_cm IS NULL OR (altura_seguridad_cm >= 0 AND altura_seguridad_cm < altura_tanque_cm))));
