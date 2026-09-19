-- Migration: Configuracion administrable del broker MQTT (HU-08)
CREATE TABLE IF NOT EXISTS mqtt_config (
    id                   SERIAL       PRIMARY KEY,
    host                 VARCHAR(255) NOT NULL,
    port                 INTEGER      NOT NULL DEFAULT 8883,
    username             VARCHAR(150),
    password             VARCHAR(255),
    usar_tls             BOOLEAN      DEFAULT true,
    actualizado_por      INTEGER      REFERENCES usuarios(id),
    fecha_actualizacion  TIMESTAMP    DEFAULT now()
);

COMMENT ON TABLE mqtt_config IS 'Configuracion del broker MQTT editable desde el panel de administracion (fila unica).';
