UPDATE configuracion_control
SET duracion_riego_max_seg = LEAST(GREATEST(COALESCE(duracion_riego_max_seg, 600), 60), 1800);

ALTER TABLE configuracion_control
    ALTER COLUMN duracion_riego_max_seg SET DEFAULT 600;

ALTER TABLE configuracion_control
    DROP CONSTRAINT IF EXISTS ck_config_control_duracion_rele;

ALTER TABLE configuracion_control
    ADD CONSTRAINT ck_config_control_duracion_rele
    CHECK (duracion_riego_max_seg BETWEEN 60 AND 1800);
