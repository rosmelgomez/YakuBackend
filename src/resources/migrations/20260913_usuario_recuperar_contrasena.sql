-- Migración para soporte de recuperación de contraseñas por código de correo
-- Fecha: 2026-09-13

ALTER TABLE usuarios 
ADD COLUMN IF NOT EXISTS token_recuperacion VARCHAR(100),
ADD COLUMN IF NOT EXISTS token_recuperacion_expira TIMESTAMP;

CREATE INDEX IF NOT EXISTS idx_usuarios_token_recuperacion ON usuarios(token_recuperacion);
