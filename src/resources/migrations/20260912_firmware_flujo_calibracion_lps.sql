INSERT INTO versiones_firmware (id,version,chip,tipo_dispositivo,descripcion,manifiesto,directorio,ubicacion_archivo,publicado,descontinuado,creado_por)
SELECT (SELECT COALESCE(MAX(id),0)+1 FROM versiones_firmware),'1.0.7','ESP32','riego_flujo',
'Caudal L/s en LCD y serie; calibracion volumetrica persistente por USB; MQTT compatible',
'{"schema_version": 1, "version": "1.0.7", "chip": "ESP32", "tipo_dispositivo": "riego_flujo", "source_sha256": "1a0f71ead43f79fb0999494b641854d7b3c5784887ec4c3b9965c93f6418de44", "segmentos": [{"nombre": "esp32-sensor-flujo.ino.bootloader.bin", "direccion": 4096, "tamano": 24992, "sha256": "427f96e10c620c4f062dab15da54fc45494d897e8397ae6f3aecc98c42d7e379"}, {"nombre": "esp32-sensor-flujo.ino.partitions.bin", "direccion": 32768, "tamano": 3072, "sha256": "148b959cbff1c38aa8e1d5c0ba9d612c54997b945e56a63f41223eef650653a1"}, {"nombre": "boot_app0.bin", "direccion": 57344, "tamano": 8192, "sha256": "f94c5d786a7a8fab06ac5d10e33bf37711a6697636dc037559ea19cc410a17f0"}, {"nombre": "esp32-sensor-flujo.ino.bin", "direccion": 65536, "tamano": 1046960, "sha256": "13a24a25a4125bfa30b23a67c989a70036032f9594660398729a5b3d459a6abc"}]}'::jsonb,'esp32-flujo-1.0.7','firmware_store/esp32-flujo-1.0.7',true,false,
(SELECT MIN(id) FROM usuarios WHERE id_rol=1)
WHERE EXISTS (SELECT 1 FROM usuarios WHERE id_rol=1) AND NOT EXISTS
(SELECT 1 FROM versiones_firmware WHERE version='1.0.7' AND chip='ESP32' AND tipo_dispositivo='riego_flujo');
SELECT setval(pg_get_serial_sequence('versiones_firmware','id'),(SELECT MAX(id) FROM versiones_firmware));
