INSERT INTO versiones_firmware (id,version,chip,tipo_dispositivo,descripcion,manifiesto,directorio,ubicacion_archivo,publicado,descontinuado,creado_por)
SELECT (SELECT COALESCE(MAX(id),0)+1 FROM versiones_firmware),'1.0.11','ESP32','riego_flujo',
'PENDIENTE DE COMPILAR: litrosRiego (evento) y motivo_cierre se resetean justo despues de transmitir el cierre, para que los heartbeats de inactividad (cada 30s) no repitan el litraje del ultimo riego como si fuera un ciclo nuevo. No publicar hasta reemplazar "segmentos" con los binarios compilados reales.',
'{"schema_version": 1, "version": "1.0.11", "chip": "ESP32", "tipo_dispositivo": "riego_flujo", "source_sha256": "2c9c337f00195511c6ce905690a61cf1cb31b1a7acfe15f8025cfdfaa08a67da", "segmentos": [], "pendiente_compilacion": true}'::jsonb,'esp32-flujo-1.0.11','firmware_store/esp32-flujo-1.0.11',false,false,
(SELECT MIN(id) FROM usuarios WHERE id_rol=1)
WHERE EXISTS (SELECT 1 FROM usuarios WHERE id_rol=1) AND NOT EXISTS
(SELECT 1 FROM versiones_firmware WHERE version='1.0.11' AND chip='ESP32' AND tipo_dispositivo='riego_flujo');
SELECT setval(pg_get_serial_sequence('versiones_firmware','id'),(SELECT MAX(id) FROM versiones_firmware));
