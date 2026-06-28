UPDATE versiones_firmware
SET publicado = FALSE,
    descontinuado = TRUE,
    fecha_descontinuado = COALESCE(fecha_descontinuado, NOW())
WHERE chip = 'ESP32'
  AND tipo_dispositivo = 'riego'
  AND descontinuado = FALSE;

INSERT INTO versiones_firmware
    (version, chip, tipo_dispositivo, descripcion, manifiesto, directorio, ubicacion_archivo, publicado, descontinuado, creado_por)
VALUES
    (
        '1.1.0',
        'ESP32',
        'riego',
        'Captura nivel de tanque periodicamente y usa la configuracion de tanque asociada a las asignaciones.',
        '{"schema_version":1,"version":"1.1.0","chip":"ESP32","tipo_dispositivo":"riego","segmentos":[{"nombre":"esp32.ino.bootloader.bin","direccion":4096,"sha256":"f508dfe30f34c2490ec08caaa96f20dc2853f66a0a92f6fb759b205e82924f29","tamano":25024},{"nombre":"esp32.ino.partitions.bin","direccion":32768,"sha256":"148b959cbff1c38aa8e1d5c0ba9d612c54997b945e56a63f41223eef650653a1","tamano":3072},{"nombre":"boot_app0.bin","direccion":57344,"sha256":"f94c5d786a7a8fab06ac5d10e33bf37711a6697636dc037559ea19cc410a17f0","tamano":8192},{"nombre":"esp32.ino.bin","direccion":65536,"sha256":"3750be54abfc20d1507b6c123c11ac40c991ad0b4e48df7cbbd0f06b31998a49","tamano":1032720}]}'::jsonb,
        'esp32-riego-1.1.0',
        'esp32-riego-1.1.0',
        TRUE,
        FALSE,
        1
    )
ON CONFLICT ON CONSTRAINT uq_firmware_release DO UPDATE
SET descripcion = EXCLUDED.descripcion,
    manifiesto = EXCLUDED.manifiesto,
    directorio = EXCLUDED.directorio,
    ubicacion_archivo = EXCLUDED.ubicacion_archivo,
    publicado = TRUE,
    descontinuado = FALSE,
    fecha_descontinuado = NULL;
