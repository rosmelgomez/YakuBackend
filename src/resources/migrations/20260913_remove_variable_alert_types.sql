-- Desactivar tipos de alertas para las 4 variables de suelo/ambiente y nivel del tanque
UPDATE tipos_alerta 
SET activo = FALSE 
WHERE id IN (1, 2, 3, 4, 5, 6, 7, 8, 9, 10) 
   OR codigo LIKE 'ALERT_%';

-- Insertar tipo de alerta para Riego ML si no existe
INSERT INTO tipos_alerta (id, codigo, nombre, descripcion, severidad, activo)
SELECT 11, 'RIEGO_ML', 'Riego activado por IA', 'Notificación con los datos de las 4 variables analizadas por el modelo al iniciar el riego.', 'info', TRUE
WHERE NOT EXISTS (SELECT 1 FROM tipos_alerta WHERE codigo = 'RIEGO_ML');

-- Insertar tipo de alerta para Problemas e Incidencias de Riego si no existe
INSERT INTO tipos_alerta (id, codigo, nombre, descripcion, severidad, activo)
SELECT 12, 'PROBLEMA_RIEGO', 'Incidencias y problemas de riego', 'Problemas críticos: riego fallido, interrupción, parada sin confirmar o desconexión.', 'critica', TRUE
WHERE NOT EXISTS (SELECT 1 FROM tipos_alerta WHERE codigo = 'PROBLEMA_RIEGO');

-- Limpiar alertas y notificaciones históricas de variables de sensores y tanque
DELETE FROM notificaciones WHERE id_alerta IN (
    SELECT id FROM alertas WHERE id_tipo_metrica IS NOT NULL OR id_tipo_alerta IN (1, 2, 3, 4, 5, 6, 7, 8, 9, 10)
);
DELETE FROM alertas WHERE id_tipo_metrica IS NOT NULL OR id_tipo_alerta IN (1, 2, 3, 4, 5, 6, 7, 8, 9, 10);
