-- Migration: Add per-user read/cleared state to alertas so the notification
-- feed is authoritative in the backend and stays in sync across devices.
ALTER TABLE alertas ADD COLUMN IF NOT EXISTS notificacion_leida BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE alertas ADD COLUMN IF NOT EXISTS notificacion_eliminada BOOLEAN NOT NULL DEFAULT FALSE;
