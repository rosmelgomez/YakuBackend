UPDATE versiones_firmware
SET publicado = FALSE,
    descontinuado = TRUE,
    fecha_descontinuado = COALESCE(fecha_descontinuado, now() AT TIME ZONE 'utc')
WHERE chip = 'ESP32'
  AND tipo_dispositivo = 'riego'
  AND version IN ('1.0.1', '1.1.1', '1.1.2', '1.1.3', '1.1.4');
