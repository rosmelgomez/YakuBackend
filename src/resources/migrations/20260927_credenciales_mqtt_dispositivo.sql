-- Migration: credencial MQTT propia de cada dispositivo ESP32 y clave del
-- broker cifrada (src/main/core/secretCipher.py).

-- Un token Fernet ocupa mas que la clave en texto plano: se amplia la columna.
ALTER TABLE mqtt_config ALTER COLUMN password TYPE TEXT;

CREATE TABLE IF NOT EXISTS credenciales_mqtt_dispositivo (
    id                   SERIAL       PRIMARY KEY,
    id_dispositivo       INTEGER      NOT NULL UNIQUE REFERENCES dispositivos(id) ON DELETE CASCADE,
    username             VARCHAR(150) NOT NULL UNIQUE,
    password_cifrada     TEXT         NOT NULL,
    actualizado_por      INTEGER      REFERENCES usuarios(id) ON DELETE SET NULL,
    fecha_registro       TIMESTAMP    NOT NULL DEFAULT now(),
    fecha_actualizacion  TIMESTAMP    NOT NULL DEFAULT now()
);

COMMENT ON TABLE credenciales_mqtt_dispositivo IS 'Credencial MQTT de cada ESP32 (clave cifrada con CREDENTIALS_ENCRYPTION_KEY); el panel de firmware la envia al equipo al provisionarlo.';
