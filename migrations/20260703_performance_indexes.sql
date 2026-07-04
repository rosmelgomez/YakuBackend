CREATE INDEX IF NOT EXISTS idx_hum_suelo_asig_valido_fecha
    ON humedad_suelo (id_asignacion, valido, fecha DESC);

CREATE INDEX IF NOT EXISTS idx_hum_amb_asig_valido_fecha
    ON humedad_ambiente (id_asignacion, valido, fecha DESC);

CREATE INDEX IF NOT EXISTS idx_temp_suelo_asig_valido_fecha
    ON temperatura_suelo (id_asignacion, valido, fecha DESC);

CREATE INDEX IF NOT EXISTS idx_temp_amb_asig_valido_fecha
    ON temperatura_ambiente (id_asignacion, valido, fecha DESC);

CREATE INDEX IF NOT EXISTS idx_tel_tanque_asig_fecha
    ON telemetria_tanque (id_asignacion, fecha DESC);

CREATE INDEX IF NOT EXISTS idx_riego_asig_estado_fecha
    ON riego (id_asignacion, estado, fecha DESC);

CREATE INDEX IF NOT EXISTS idx_alertas_asig_estado_fecha
    ON alertas (id_asignacion, estado, fecha DESC);

CREATE INDEX IF NOT EXISTS idx_alertas_usuario_estado_fecha
    ON alertas (id_usuario, estado, fecha DESC);

CREATE INDEX IF NOT EXISTS idx_asignaciones_usuario_cultivo
    ON asignaciones_iot (id_usuario, id_cultivo);
