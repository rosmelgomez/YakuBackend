INSERT INTO versiones_firmware (id,version,chip,tipo_dispositivo,descripcion,manifiesto,directorio,ubicacion_archivo,publicado,descontinuado,creado_por)
SELECT (SELECT COALESCE(MAX(id),0)+1 FROM versiones_firmware),'1.0.2','ESP32-S3','sensores',
'PENDIENTE DE COMPILAR: EMA de humedad de suelo arranca con la primera lectura real (antes subia desde 0% tras cada reinicio); higrometro desconectado se marca invalido; solo se publica cuando hay una lectura nueva; filtros reiniciados al reactivar la captura.',
'{"schema_version": 1, "version": "1.0.2", "chip": "ESP32-S3", "tipo_dispositivo": "sensores", "source_sha256": "8420446b311c617be17e9ea91e3811e4e6f9c5e652bb95d96d30c85b14c9b4db", "segmentos": [], "pendiente_compilacion": true}'::jsonb,'esp32-s3-1.0.2','firmware_store/esp32-s3-1.0.2',false,false,
(SELECT MIN(id) FROM usuarios WHERE id_rol=1)
WHERE EXISTS (SELECT 1 FROM usuarios WHERE id_rol=1) AND NOT EXISTS
(SELECT 1 FROM versiones_firmware WHERE version='1.0.2' AND chip='ESP32-S3' AND tipo_dispositivo='sensores');
SELECT setval(pg_get_serial_sequence('versiones_firmware','id'),(SELECT MAX(id) FROM versiones_firmware));
