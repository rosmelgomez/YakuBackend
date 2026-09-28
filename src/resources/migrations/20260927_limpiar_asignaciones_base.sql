-- Al asignar un dispositivo se creaba una fila base en asignaciones_iot (solo
-- usuario/cultivo) y cada componente agregaba otra, dejando siempre una fila de
-- mas. Desde ahora el primer componente reutiliza la fila base; aqui se borran
-- las filas base sobrantes que ya existen.
-- Solo se borra si: no tiene componente, metrica ni pin; el mismo dispositivo
-- tiene otra fila del mismo agricultor y cultivo (el vinculo no se pierde); y
-- nada la referencia (las FK borran en cascada, asi que no se toca ningun dato).
DELETE FROM asignaciones_iot b
WHERE b.id_componente IS NULL
  AND b.id_tipo_metrica IS NULL
  AND b.pin_gpio IS NULL
  AND EXISTS (SELECT 1 FROM asignaciones_iot o WHERE o.id_dispositivo = b.id_dispositivo AND o.id_usuario = b.id_usuario AND o.id_cultivo IS NOT DISTINCT FROM b.id_cultivo AND o.id <> b.id)
  AND NOT EXISTS (SELECT 1 FROM configuracion_actuador x WHERE x.id_asignacion = b.id)
  AND NOT EXISTS (SELECT 1 FROM humedad_suelo x WHERE x.id_asignacion = b.id)
  AND NOT EXISTS (SELECT 1 FROM humedad_ambiente x WHERE x.id_asignacion = b.id)
  AND NOT EXISTS (SELECT 1 FROM temperatura_ambiente x WHERE x.id_asignacion = b.id)
  AND NOT EXISTS (SELECT 1 FROM temperatura_suelo x WHERE x.id_asignacion = b.id)
  AND NOT EXISTS (SELECT 1 FROM telemetria_tanque x WHERE x.id_asignacion = b.id)
  AND NOT EXISTS (SELECT 1 FROM lecturas_bateria x WHERE x.id_asignacion = b.id)
  AND NOT EXISTS (SELECT 1 FROM riego x WHERE x.id_asignacion = b.id)
  AND NOT EXISTS (SELECT 1 FROM horarios_riego x WHERE x.id_asignacion = b.id)
  AND NOT EXISTS (SELECT 1 FROM alertas x WHERE x.id_asignacion = b.id);
