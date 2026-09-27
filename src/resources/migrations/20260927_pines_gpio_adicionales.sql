-- Migration: un componente puede ocupar varios GPIO (p.ej. LCD I2C usa SDA y SCL).
-- pin_gpio sigue siendo el pin principal (calibracion, firmware, control);
-- pines_gpio_adicionales guarda el resto de pines que usa el componente.
ALTER TABLE asignaciones_iot ADD COLUMN IF NOT EXISTS pines_gpio_adicionales INTEGER[] NOT NULL DEFAULT '{}';

UPDATE tipos_componente
SET descripcion = 'Pantalla LCD 16x2 I2C, direccion 0x27. Firmware de flujo: SDA GPIO13, SCL GPIO14. Sin metrica de captura; registrar SDA como pin principal y SCL como pin adicional.'
WHERE nombre_modelo = 'LCD 16x2 I2C';

-- LCD ya asignados con solo SDA (GPIO13) en firmware de flujo: completar SCL (GPIO14).
UPDATE asignaciones_iot a
SET pines_gpio_adicionales = ARRAY[14]
FROM componentes c
JOIN tipos_componente t ON t.id = c.id_tipo_componente
WHERE a.id_componente = c.id
  AND t.nombre_modelo = 'LCD 16x2 I2C'
  AND a.pin_gpio = 13
  AND a.pines_gpio_adicionales = '{}';
