-- DESACTIVADA (27/09/2026). Era una limpieza unica de asignaciones historicas, pero
-- run_migrations() ejecuta todas las migraciones en CADA arranque y esta suponia
-- que cada dispositivo conserva una fila base (sin componente): si no la
-- encontraba, vaciaba componente, pin y metrica de todas sus asignaciones.
-- Desde que el primer componente ocupa la fila base, eso borraba las asignaciones
-- vigentes en cada reinicio. La limpieza ya se aplico en su momento; no se repite.
SELECT 1;
