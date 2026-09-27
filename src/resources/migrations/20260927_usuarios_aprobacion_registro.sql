-- Aprobacion de solicitudes de registro: los agricultores que se registran desde
-- fuera de la plataforma quedan en 'pendiente' hasta que un administrador los
-- apruebe o rechace. Los usuarios existentes y los creados por un administrador
-- se consideran aprobados.
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS estado_aprobacion VARCHAR(20) NOT NULL DEFAULT 'aprobado';
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS motivo_rechazo TEXT;
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS fecha_revision TIMESTAMP;
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS revisado_por INT REFERENCES usuarios(id) ON DELETE SET NULL;

-- run_migrations() separa sentencias por ';' al final de linea: sin bloques DO $$.
ALTER TABLE usuarios DROP CONSTRAINT IF EXISTS ck_usuarios_estado_aprobacion;
ALTER TABLE usuarios ADD CONSTRAINT ck_usuarios_estado_aprobacion
    CHECK (estado_aprobacion IN ('pendiente', 'aprobado', 'rechazado'));

CREATE INDEX IF NOT EXISTS idx_usuarios_aprobacion_pendiente
    ON usuarios(fecha_registro) WHERE estado_aprobacion = 'pendiente';
