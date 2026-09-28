-- Reparacion unica (27/09/2026): la migracion 20260624 vacio las asignaciones al
-- reiniciar el backend y la limpieza de filas base borro las filas 5 y 7.
-- Reconstruido con: telemetria por id_asignacion (1 hum. suelo, 2 temp. amb.,
-- 3 hum. amb., 4 temp. suelo), fila 6 = actuador (riego, horario, config. actuador),
-- y pines del firmware de flujo (valvula GPIO25, flujo GPIO27, LCD SDA13/SCL14).
-- Quedan inactivas: se activan desde Control de Riego.
BEGIN;

-- Colector A (dispositivo 2)
UPDATE asignaciones_iot SET id_componente = 1, id_tipo_metrica = 1, pin_gpio = 17, pines_gpio_adicionales = '{}' WHERE id = 1 AND id_dispositivo = 2; -- Higrometro -> HUM_SUELO
UPDATE asignaciones_iot SET id_componente = 2, id_tipo_metrica = 3, pin_gpio = 15, pines_gpio_adicionales = '{}' WHERE id = 2 AND id_dispositivo = 2; -- DHT22 -> TEMP_AMB
UPDATE asignaciones_iot SET id_componente = 2, id_tipo_metrica = 2, pin_gpio = 15, pines_gpio_adicionales = '{}' WHERE id = 3 AND id_dispositivo = 2; -- DHT22 -> HUM_AMB
UPDATE asignaciones_iot SET id_componente = 3, id_tipo_metrica = 4, pin_gpio = 16, pines_gpio_adicionales = '{}' WHERE id = 4 AND id_dispositivo = 2; -- DS18B20 -> TEMP_SUELO

-- Flujometro A (dispositivo 3)
INSERT INTO asignaciones_iot (id, id_usuario, id_dispositivo, id_componente, id_cultivo, id_tipo_metrica, pin_gpio, pines_gpio_adicionales, activo)
SELECT 5, 2, 3, 4, 2, 7, 27, '{}', FALSE
WHERE NOT EXISTS (SELECT 1 FROM asignaciones_iot WHERE id = 5);                                                 -- YF-S201 -> CAUDAL
UPDATE asignaciones_iot SET id_componente = 5, id_tipo_metrica = NULL, pin_gpio = 25, pines_gpio_adicionales = '{}' WHERE id = 6 AND id_dispositivo = 3; -- Rele -> actuador (valvula)
INSERT INTO asignaciones_iot (id, id_usuario, id_dispositivo, id_componente, id_cultivo, id_tipo_metrica, pin_gpio, pines_gpio_adicionales, activo)
SELECT 7, 2, 3, 6, 2, NULL, 13, '{14}', FALSE
WHERE NOT EXISTS (SELECT 1 FROM asignaciones_iot WHERE id = 7);                                                 -- LCD I2C SDA13 / SCL14

SELECT setval(pg_get_serial_sequence('asignaciones_iot', 'id'), (SELECT MAX(id) FROM asignaciones_iot));

COMMIT;
