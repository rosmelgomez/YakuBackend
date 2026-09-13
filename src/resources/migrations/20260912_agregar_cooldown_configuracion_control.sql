-- Migracion: Agregar columna cooldown_minutos a la tabla configuracion_control
ALTER TABLE configuracion_control 
ADD COLUMN IF NOT EXISTS cooldown_minutos INT DEFAULT 30;

UPDATE configuracion_control 
SET cooldown_minutos = 30 
WHERE cooldown_minutos IS NULL;
