-- Avisos tecnicos para el administrador:
--  * RED_NODO_DESCONECTADO (HU-22): un nodo asignado lleva mas de 10 min sin
--    reportar por MQTT. Se resuelve solo cuando el nodo vuelve a reportar.
--  * FALLA_HARDWARE (HU-21): el actuador reporto un error electrico al
--    accionar el rele/valvula.
INSERT INTO tipos_alerta (id, codigo, nombre, descripcion, severidad, activo)
SELECT (SELECT COALESCE(MAX(id), 0) + 1 FROM tipos_alerta), 'RED_NODO_DESCONECTADO', 'Nodo desconectado de la red', 'Aviso al administrador cuando un nodo IoT deja de reportar por MQTT más de 10 minutos.', 'critica', TRUE
WHERE NOT EXISTS (SELECT 1 FROM tipos_alerta WHERE codigo = 'RED_NODO_DESCONECTADO');

INSERT INTO tipos_alerta (id, codigo, nombre, descripcion, severidad, activo)
SELECT (SELECT COALESCE(MAX(id), 0) + 1 FROM tipos_alerta), 'FALLA_HARDWARE', 'Falla de hardware en actuador', 'Aviso al administrador cuando el microcontrolador reporta un error eléctrico al accionar el relé o la válvula.', 'critica', TRUE
WHERE NOT EXISTS (SELECT 1 FROM tipos_alerta WHERE codigo = 'FALLA_HARDWARE');

SELECT setval(pg_get_serial_sequence('tipos_alerta', 'id'), (SELECT MAX(id) FROM tipos_alerta));
