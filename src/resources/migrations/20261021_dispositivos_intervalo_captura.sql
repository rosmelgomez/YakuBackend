-- Migration: intervalo entre mediciones configurable por dispositivo.
-- Cada agricultor puede necesitar un muestreo distinto (1 min, 2 min, ...).
-- El administrador lo fija en el Gestor de firmware; el backend lo envia en la
-- configuracion MQTT (captura_segundos) y el firmware S3 >= 1.0.5 lo aplica.
-- Rango 10 s - 60 min: el DHT22 necesita >= 2 s entre lecturas y la WMO/OMS
-- trabajan con promedios de 1 a 15 min para temperatura y humedad.
-- (Una sola sentencia: el CHECK solo se crea junto con la columna, asi la
-- migracion es idempotente aunque bootstrap la re-ejecute en cada arranque.)
ALTER TABLE dispositivos ADD COLUMN IF NOT EXISTS intervalo_captura_segundos INT NOT NULL DEFAULT 60 CHECK (intervalo_captura_segundos BETWEEN 10 AND 3600);
