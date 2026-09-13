-- Migracion para ampliar la tabla usuarios con informacion personal y tokens de verificacion
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS dni VARCHAR(20);
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS fecha_nacimiento DATE;
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS direccion VARCHAR(255);
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS fecha_modificacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS token_verificacion VARCHAR(100);
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS token_verificacion_expira TIMESTAMP;

-- Crear indices unicos y de busqueda rapida
CREATE UNIQUE INDEX IF NOT EXISTS uq_usuarios_dni ON usuarios(dni) WHERE dni IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_usuarios_token_verificacion ON usuarios(token_verificacion) WHERE token_verificacion IS NOT NULL;
