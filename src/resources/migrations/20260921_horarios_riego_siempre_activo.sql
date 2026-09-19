-- Migration: Horario "Siempre activo" (deja que la IA decida en cualquier
-- momento, sin franja horaria fija) y columnas de hora/duracion ahora
-- opcionales para ese caso.
ALTER TABLE horarios_riego ADD COLUMN IF NOT EXISTS siempre_activo BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE horarios_riego ALTER COLUMN hora_inicio DROP NOT NULL;
ALTER TABLE horarios_riego ALTER COLUMN hora_fin DROP NOT NULL;
ALTER TABLE horarios_riego ALTER COLUMN duracion_segundos DROP NOT NULL;
