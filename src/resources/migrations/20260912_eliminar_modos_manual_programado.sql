-- =========================================================
-- MIGRACION: Eliminar Modos Manual y Programado
-- Dejar Machine Learning (ML) como el único modo de operación por defecto
-- =========================================================

-- 1. Eliminar la tabla de horarios y programación de riego
DROP TABLE IF EXISTS programacion_riego CASCADE;

-- 2. Asegurar que los modelos ML asignados a cultivos estén activos por defecto
UPDATE cultivo_modelo SET activo = true WHERE activo = false;
