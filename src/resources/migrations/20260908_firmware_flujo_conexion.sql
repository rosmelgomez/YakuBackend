INSERT INTO versiones_firmware (id,version,chip,tipo_dispositivo,descripcion,manifiesto,directorio,ubicacion_archivo,publicado,descontinuado,creado_por)
SELECT (SELECT COALESCE(MAX(id),0)+1 FROM versiones_firmware),'1.0.2','ESP32','riego_flujo',
'Reconecta WiFi y MQTT, reintenta configuracion y diagnostica comandos por serie',
'{"schema_version": 1, "version": "1.0.2", "chip": "ESP32", "tipo_dispositivo": "riego_flujo", "source_sha256": "a7cbaf07b8aee16db0b730fc1264cbbf83fc684d73cab912a260f6370944bc9d", "segmentos": [{"nombre": "esp32-sensor-flujo.ino.bootloader.bin", "direccion": 4096, "tamano": 24992, "sha256": "427f96e10c620c4f062dab15da54fc45494d897e8397ae6f3aecc98c42d7e379"}, {"nombre": "esp32-sensor-flujo.ino.partitions.bin", "direccion": 32768, "tamano": 3072, "sha256": "148b959cbff1c38aa8e1d5c0ba9d612c54997b945e56a63f41223eef650653a1"}, {"nombre": "boot_app0.bin", "direccion": 57344, "tamano": 8192, "sha256": "f94c5d786a7a8fab06ac5d10e33bf37711a6697636dc037559ea19cc410a17f0"}, {"nombre": "esp32-sensor-flujo.ino.bin", "direccion": 65536, "tamano": 1043520, "sha256": "b7fe58ee657e4f4cc0b57fd16db8548dd79696110e6b10e9a8f975ae4cb2024f"}]}'::jsonb,'esp32-flujo-1.0.2','firmware_store/esp32-flujo-1.0.2',true,false,
(SELECT MIN(id) FROM usuarios WHERE id_rol=1)
WHERE EXISTS (SELECT 1 FROM usuarios WHERE id_rol=1) AND NOT EXISTS
(SELECT 1 FROM versiones_firmware WHERE version='1.0.2' AND chip='ESP32' AND tipo_dispositivo='riego_flujo');
UPDATE versiones_firmware SET publicado=false,descontinuado=true,fecha_descontinuado=COALESCE(fecha_descontinuado,CURRENT_TIMESTAMP)
WHERE tipo_dispositivo='riego_flujo' AND chip='ESP32' AND version='1.0.1'
AND EXISTS (SELECT 1 FROM versiones_firmware WHERE tipo_dispositivo='riego_flujo' AND version='1.0.2');
SELECT setval(pg_get_serial_sequence('versiones_firmware','id'),(SELECT MAX(id) FROM versiones_firmware));
