-- Migración para normalizar la tabla usuarios y registrar histórico de tokens
-- Fecha: 2026-09-13

-- 1. Crear tabla tokens_usuario
CREATE TABLE IF NOT EXISTS tokens_usuario (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_usuario INTEGER NOT NULL,
    tipo VARCHAR(30) NOT NULL,
    token VARCHAR(100) NOT NULL,
    creado_en TIMESTAMP WITHOUT TIME ZONE DEFAULT (now() at time zone 'utc') NOT NULL,
    expira_en TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    usado BOOLEAN DEFAULT FALSE NOT NULL,
    fecha_uso TIMESTAMP WITHOUT TIME ZONE,
    ip_origen VARCHAR(45),
    CONSTRAINT fk_tokens_usuario_usuario FOREIGN KEY (id_usuario) REFERENCES usuarios(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_tokens_usuario_token ON tokens_usuario(token);
CREATE INDEX IF NOT EXISTS idx_tokens_usuario_usuario_tipo ON tokens_usuario(id_usuario, tipo);
CREATE INDEX IF NOT EXISTS idx_tokens_usuario_vigente ON tokens_usuario(token, tipo, usado, expira_en);

-- 2. Eliminar índices previos si existen
DROP INDEX IF EXISTS idx_usuarios_token_verificacion;
DROP INDEX IF EXISTS idx_usuarios_token_recuperacion;

-- 3. Eliminar columnas de tokens de la tabla usuarios
ALTER TABLE usuarios
DROP COLUMN IF EXISTS token_verificacion CASCADE,
DROP COLUMN IF EXISTS token_verificacion_expira CASCADE,
DROP COLUMN IF EXISTS token_recuperacion CASCADE,
DROP COLUMN IF EXISTS token_recuperacion_expira CASCADE;
