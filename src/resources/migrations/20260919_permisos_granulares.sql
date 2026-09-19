-- Migration: Permisos granulares por usuario, adicionales al rol (HU-31)
-- El catalogo (que permisos existen) y su siembra/depuracion vive en
-- src/main/service/permisoServ.py::CATALOGO_PERMISOS, sincronizado en cada
-- arranque por bootstrapRep.ensure_permisos_schema().
CREATE TABLE IF NOT EXISTS permisos_catalogo (
    id           SERIAL       PRIMARY KEY,
    codigo       VARCHAR(50)  UNIQUE NOT NULL,
    nombre       VARCHAR(100) NOT NULL,
    descripcion  TEXT
);

CREATE TABLE IF NOT EXISTS usuario_permisos (
    id              SERIAL     PRIMARY KEY,
    id_usuario      INTEGER    NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    id_permiso      INTEGER    NOT NULL REFERENCES permisos_catalogo(id) ON DELETE CASCADE,
    otorgado_por    INTEGER    REFERENCES usuarios(id),
    fecha_otorgado  TIMESTAMP  DEFAULT now(),
    CONSTRAINT uq_usuario_permiso UNIQUE (id_usuario, id_permiso)
);

CREATE INDEX IF NOT EXISTS idx_usuario_permisos_usuario ON usuario_permisos(id_usuario);

COMMENT ON TABLE permisos_catalogo IS 'Catalogo fijo de permisos granulares delegables a usuarios no administradores.';
COMMENT ON TABLE usuario_permisos IS 'Permisos granulares otorgados puntualmente a un usuario, ademas de su rol.';
