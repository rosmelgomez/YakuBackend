-- El historial en el dashboard (campana de notificaciones) ahora se
-- entrega siempre; deja de depender de una preferencia por tipo de alerta.
ALTER TABLE configuracion_notificaciones DROP COLUMN IF EXISTS canal_dashboard;
