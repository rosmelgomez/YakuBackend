ALTER TABLE versiones_firmware
    ADD COLUMN IF NOT EXISTS ubicacion_archivo VARCHAR(500),
    ADD COLUMN IF NOT EXISTS descontinuado BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS fecha_descontinuado TIMESTAMP;

UPDATE versiones_firmware
SET ubicacion_archivo = COALESCE(ubicacion_archivo, directorio)
WHERE ubicacion_archivo IS NULL;
