UPDATE riego AS r
SET estado = TRUE,
    fecha_fin = COALESCE(r.fecha_fin, NOW()),
    fecha = COALESCE(r.fecha_fin, NOW()),
    motivo_cierre = COALESCE(r.motivo_cierre, 'asignacion_no_bomba')
WHERE r.estado IS FALSE
  AND NOT EXISTS (
      SELECT 1
      FROM configuracion_tanque AS ct
      WHERE ct.id_asignacion = r.id_asignacion
  );
