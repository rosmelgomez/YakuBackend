INSERT INTO versiones_firmware (
    version,
    chip,
    tipo_dispositivo,
    descripcion,
    manifiesto,
    directorio,
    ubicacion_archivo,
    publicado,
    descontinuado,
    creado_por
)
SELECT
    '1.1.7',
    'ESP32',
    'riego',
    'ESP32 riego: mide distancia continuamente y publica MQTT de riego solo al inicio y fin de la bomba.',
    '{
      "schema_version": 1,
      "version": "1.1.7",
      "chip": "ESP32",
      "tipo_dispositivo": "riego",
      "segmentos": [
        {
          "nombre": "boot_app0.bin",
          "direccion": "0xe000",
          "tamano": 8192,
          "sha256": "f94c5d786a7a8fab06ac5d10e33bf37711a6697636dc037559ea19cc410a17f0"
        },
        {
          "nombre": "esp32.ino.bootloader.bin",
          "direccion": "0x1000",
          "tamano": 23520,
          "sha256": "2d8c700ad2d27b419dc44c0bea82b6339664a4088dbed264f0be00e17bc4959d"
        },
        {
          "nombre": "esp32.ino.partitions.bin",
          "direccion": "0x8000",
          "tamano": 3072,
          "sha256": "148b959cbff1c38aa8e1d5c0ba9d612c54997b945e56a63f41223eef650653a1"
        },
        {
          "nombre": "esp32.ino.bin",
          "direccion": "0x10000",
          "tamano": 1034288,
          "sha256": "dc837aa834a99722df0ca1caad5ff2e52b30a7b2b39219ae526f5dfab7d133d8"
        }
      ]
    }'::jsonb,
    'esp32-riego-1.1.7',
    'firmware_store/esp32-riego-1.1.7',
    TRUE,
    FALSE,
    usuario_admin.id
FROM (
    SELECT id
    FROM usuarios
    WHERE id_rol = 1
    ORDER BY id
    LIMIT 1
) AS usuario_admin
ON CONFLICT (version, chip, tipo_dispositivo) DO UPDATE
SET descripcion = EXCLUDED.descripcion,
    manifiesto = EXCLUDED.manifiesto,
    directorio = EXCLUDED.directorio,
    ubicacion_archivo = EXCLUDED.ubicacion_archivo,
    publicado = TRUE,
    descontinuado = FALSE,
    fecha_descontinuado = NULL;

UPDATE versiones_firmware
SET publicado = FALSE,
    descontinuado = TRUE,
    fecha_descontinuado = COALESCE(fecha_descontinuado, now() AT TIME ZONE 'utc')
WHERE chip = 'ESP32'
  AND tipo_dispositivo = 'riego'
  AND version <> '1.1.7'
  AND EXISTS (
      SELECT 1
      FROM versiones_firmware
      WHERE chip = 'ESP32'
        AND tipo_dispositivo = 'riego'
        AND version = '1.1.7'
        AND publicado = TRUE
        AND descontinuado = FALSE
  );
