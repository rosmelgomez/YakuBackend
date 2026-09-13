-- =========================================================
-- MIGRACION: Eliminar Nivel de Tanque, Nivel de Bateria y Caudal de Riego
-- de la configuracion de umbrales agricolas y umbrales de plantas.
-- =========================================================

DELETE FROM configuracion_umbrales 
WHERE id_tipo_metrica IN (
    SELECT id FROM tipos_metrica WHERE codigo IN ('NIVEL_AGUA', 'BAT_PCT', 'CAUDAL')
);

DELETE FROM umbrales_planta 
WHERE id_tipo_metrica IN (
    SELECT id FROM tipos_metrica WHERE codigo IN ('NIVEL_AGUA', 'BAT_PCT', 'CAUDAL')
);
