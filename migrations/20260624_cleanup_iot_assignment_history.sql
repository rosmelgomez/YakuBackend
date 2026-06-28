-- Limpia asignaciones históricas de componentes que podían reaparecer al reasignar dispositivos.
-- Mantiene solo el ciclo vigente: última asignación base del dispositivo y componentes creados después.

WITH latest_base AS (
    SELECT id_dispositivo, MAX(id) AS latest_base_id
    FROM asignaciones_iot
    WHERE id_componente IS NULL
      AND id_usuario IS NOT NULL
      AND id_cultivo IS NOT NULL
    GROUP BY id_dispositivo
)
UPDATE asignaciones_iot AS a
SET activo = FALSE,
    id_componente = NULL,
    pin_gpio = NULL,
    id_tipo_metrica = NULL,
    id_fuente_agua = NULL
FROM dispositivos AS d
LEFT JOIN latest_base AS lb ON lb.id_dispositivo = d.id
WHERE a.id_dispositivo = d.id
  AND a.id_componente IS NOT NULL
  AND (
      d.estado <> 'asignado'
      OR lb.latest_base_id IS NULL
      OR a.id <= lb.latest_base_id
  );

WITH latest_base AS (
    SELECT id_dispositivo, MAX(id) AS latest_base_id
    FROM asignaciones_iot
    WHERE id_componente IS NULL
      AND id_usuario IS NOT NULL
      AND id_cultivo IS NOT NULL
    GROUP BY id_dispositivo
),
ranked AS (
    SELECT
        a.id,
        ROW_NUMBER() OVER (
            PARTITION BY a.id_dispositivo, a.id_componente, a.id_tipo_metrica
            ORDER BY a.id DESC
        ) AS rn
    FROM asignaciones_iot AS a
    JOIN latest_base AS lb ON lb.id_dispositivo = a.id_dispositivo
    WHERE a.id > lb.latest_base_id
      AND a.id_componente IS NOT NULL
)
UPDATE asignaciones_iot AS a
SET activo = FALSE,
    id_componente = NULL,
    pin_gpio = NULL,
    id_tipo_metrica = NULL,
    id_fuente_agua = NULL
FROM ranked AS r
WHERE a.id = r.id
  AND r.rn > 1;
