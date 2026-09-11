-- Modelo del LCD utilizado por el firmware; las unidades físicas se registran en inventario.
INSERT INTO tipos_componente (id, nombre_modelo, categoria, id_tipo_metrica, descripcion)
SELECT COALESCE(MAX(id), 0) + 1, 'LCD 16x2 I2C', 'pantalla', NULL,
    'Pantalla LCD 16x2 I2C, direccion 0x27. Firmware de flujo: SDA GPIO13, SCL GPIO14. Sin metrica de captura; registrar SDA como pin principal.'
FROM tipos_componente
HAVING NOT EXISTS (SELECT 1 FROM tipos_componente WHERE nombre_modelo = 'LCD 16x2 I2C');
SELECT setval(pg_get_serial_sequence('tipos_componente', 'id'), (SELECT MAX(id) FROM tipos_componente));
