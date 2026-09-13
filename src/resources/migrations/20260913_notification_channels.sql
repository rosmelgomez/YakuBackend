-- Do not opt existing users into a new device-notification preference.
ALTER TABLE configuracion_notificaciones ADD COLUMN IF NOT EXISTS canal_push BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE configuracion_notificaciones ALTER COLUMN canal_email SET DEFAULT FALSE;
UPDATE configuracion_notificaciones SET canal_email = FALSE WHERE canal_email IS DISTINCT FROM FALSE;
