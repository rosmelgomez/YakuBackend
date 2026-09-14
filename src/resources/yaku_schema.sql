-- =========================================================
-- BASE DE DATOS: YAKU v4.0
-- Sistema Inteligente de Riego IoT + ML
-- PostgreSQL 15
-- Mejoras v4.0 (Sin sesiones de seguridad):
-- - id_usuario directo en alertas y riego
-- - bomba/valvula movidos a telemetria_tanque
-- - dias_semana como columnas booleanas (ORM-friendly)
-- - fuentes_agua sin duplicacion con configuracion_tanque
-- - lecturas_bateria con BIGSERIAL
-- - tabla reporte_consumo_agua para metricas de ahorro
-- =========================================================


-- =========================================================
-- 1. ROLES
-- =========================================================
CREATE TABLE roles (
    id          SERIAL PRIMARY KEY,
    nombre      VARCHAR(50)  NOT NULL UNIQUE,  -- 'administrador', 'agricultor'
    descripcion TEXT
);

COMMENT ON TABLE roles IS 'Roles del sistema: administrador y agricultor.';


-- =========================================================
-- 2. USUARIOS
-- =========================================================
CREATE TABLE usuarios (
    id             SERIAL PRIMARY KEY,
    nombre         VARCHAR(100) NOT NULL,
    apellido       VARCHAR(100),
    correo         VARCHAR(100) NOT NULL UNIQUE,
    contrasena     VARCHAR(255) NOT NULL,
    id_rol         INT          NOT NULL REFERENCES roles(id),
    telefono       VARCHAR(20),
    zona_horaria   VARCHAR(50)  DEFAULT 'America/Lima',
    verificado     BOOLEAN      DEFAULT FALSE,
    estado         BOOLEAN      DEFAULT TRUE,
    ultimo_acceso  TIMESTAMP,
    fecha_registro TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    dni            VARCHAR(20)  UNIQUE,
    fecha_nacimiento DATE,
    direccion      VARCHAR(255),
    fecha_modificacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_usuarios_correo ON usuarios(correo);
CREATE INDEX idx_usuarios_rol    ON usuarios(id_rol);

COMMENT ON TABLE usuarios IS 'Perfiles, credenciales y preferencias de cada usuario del sistema.';

-- ---------------------------------------------------------
-- 2.1 TOKENS DE USUARIO (HISTÓRICO Y AUDITORÍA)
-- ---------------------------------------------------------
CREATE TABLE tokens_usuario (
    id         INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_usuario INT          NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    tipo       VARCHAR(30)  NOT NULL, -- 'verificacion' | 'recuperacion'
    token      VARCHAR(100) NOT NULL,
    creado_en  TIMESTAMP    DEFAULT CURRENT_TIMESTAMP NOT NULL,
    expira_en  TIMESTAMP    NOT NULL,
    usado      BOOLEAN      DEFAULT FALSE NOT NULL,
    fecha_uso  TIMESTAMP,
    ip_origen  VARCHAR(45)
);

CREATE INDEX idx_tokens_usuario_token ON tokens_usuario(token);
CREATE INDEX idx_tokens_usuario_usuario_tipo ON tokens_usuario(id_usuario, tipo);
CREATE INDEX idx_tokens_usuario_vigente ON tokens_usuario(token, tipo, usado, expira_en);

COMMENT ON TABLE tokens_usuario IS 'Historial y auditoria de tokens y codigos de verificacion y recuperacion emitidos.';


-- =========================================================
-- 3. DISPOSITIVOS
-- =========================================================
CREATE TABLE tipos_dispositivo (
    id          SERIAL PRIMARY KEY,
    nombre      VARCHAR(100) NOT NULL,  -- 'ESP32-S3 Sensores', 'ESP32 Actuadores'
    descripcion TEXT,
    metodo_medicion VARCHAR(20)
);

CREATE TABLE dispositivos (
    id                    SERIAL PRIMARY KEY,
    id_tipo               INT          NOT NULL REFERENCES tipos_dispositivo(id),
    nombre                VARCHAR(100) NOT NULL,
    mac_address           VARCHAR(100) UNIQUE,
    client_id_mqtt        VARCHAR(100) UNIQUE,
    topic_pub             VARCHAR(150),
    topic_sub             VARCHAR(150),
    ubicacion             VARCHAR(150),
    estado                VARCHAR(20)  DEFAULT 'activo',  -- 'activo','inactivo','mantenimiento'
    ultimo_ping           TIMESTAMP,
    firmware_version      VARCHAR(20),
    fecha_registro        TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE tipos_dispositivo IS 'Tipos de microcontrolador: ESP32-S3 Sensores y ESP32 Actuadores.';
COMMENT ON TABLE dispositivos       IS 'Instancias fisicas de cada microcontrolador con su configuracion MQTT.';


-- =========================================================
-- 4. CATALOGO DE METRICAS
-- =========================================================
CREATE TABLE tipos_metrica (
    id             SERIAL PRIMARY KEY,
    codigo         VARCHAR(50)  NOT NULL UNIQUE,
    nombre         VARCHAR(100) NOT NULL,
    unidad         VARCHAR(20)  NOT NULL,
    descripcion    TEXT,
    fecha_registro TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE tipos_metrica IS 'Catalogo maestro de variables fisicas medibles: humedad, temperatura, nivel agua, bateria, etc.';


-- =========================================================
-- 5. COMPONENTES E INVENTARIO FISICO
-- =========================================================
CREATE TABLE tipos_componente (
    id              SERIAL PRIMARY KEY,
    nombre_modelo   VARCHAR(100) NOT NULL UNIQUE,  -- 'DHT22', 'DS18B20', 'HC-SR04', 'Rele 5V'
    categoria       VARCHAR(30)  NOT NULL,          -- 'sensor', 'actuador', 'bateria'
    id_tipo_metrica INT          REFERENCES tipos_metrica(id),
    descripcion     TEXT
);

CREATE TABLE componentes (
    id                 SERIAL PRIMARY KEY,
    id_tipo_componente INT         NOT NULL REFERENCES tipos_componente(id) ON DELETE CASCADE,
    numero_serie       VARCHAR(100) UNIQUE,
    estado             VARCHAR(20)  DEFAULT 'activo',  -- 'activo','dañado','retirado'
    fecha_registro     TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE tipos_componente IS 'Modelos de hardware periferico: sensores, actuadores y baterias.';
COMMENT ON TABLE componentes       IS 'Inventario fisico de componentes disponibles para asignacion.';


-- =========================================================
-- 6. FUENTES DE AGUA
-- Datos estaticos del deposito (sin duplicar con telemetria)
-- =========================================================
CREATE TABLE fuentes_agua (
    id                     SERIAL PRIMARY KEY,
    id_usuario             INT          NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    nombre                 VARCHAR(100) NOT NULL,
    tipo                   VARCHAR(30)  NOT NULL,    -- 'tanque', 'conexion_directa'
    capacidad_litros       NUMERIC(10,2),            -- NULL si es conexion_directa
    altura_tanque_cm       NUMERIC(6,2),             -- altura total del tanque
    altura_seguridad_cm    NUMERIC(6,2),             -- altura/distancia sensor→techo del tanque
    activo                 BOOLEAN      DEFAULT TRUE,
    fecha_registro         TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_fuentes_agua_tipo CHECK (tipo IN ('tanque', 'conexion_directa')),
    CONSTRAINT ck_fuentes_agua_config CHECK ((tipo = 'conexion_directa' AND capacidad_litros IS NULL AND altura_tanque_cm IS NULL AND altura_seguridad_cm IS NULL) OR (tipo = 'tanque' AND capacidad_litros IS NOT NULL AND capacidad_litros > 0 AND capacidad_litros <= 99999999.99 AND altura_tanque_cm IS NOT NULL AND altura_tanque_cm > 0 AND altura_tanque_cm <= 9999.99 AND (altura_seguridad_cm IS NULL OR (altura_seguridad_cm >= 0 AND altura_seguridad_cm < altura_tanque_cm))))
);

COMMENT ON TABLE fuentes_agua IS 'Depositos y suministros de agua registrados. Datos estaticos de configuracion.';


-- =========================================================
-- 7. PLANTAS Y CULTIVOS
-- =========================================================
CREATE TABLE plantas (
    id          SERIAL PRIMARY KEY,
    nombre      VARCHAR(100) NOT NULL,
    tipo        VARCHAR(50),
    descripcion TEXT
);

-- Umbrales ideales por especie y metrica
CREATE TABLE umbrales_planta (
    id              SERIAL PRIMARY KEY,
    id_planta       INT          NOT NULL REFERENCES plantas(id) ON DELETE CASCADE,
    id_tipo_metrica INT          NOT NULL REFERENCES tipos_metrica(id),
    valor_minimo    NUMERIC(10,2),
    valor_maximo    NUMERIC(10,2),
    UNIQUE(id_planta, id_tipo_metrica)
);

CREATE TABLE regiones (
    id     SERIAL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE provincias (
    id        SERIAL PRIMARY KEY,
    id_region INT          NOT NULL REFERENCES regiones(id) ON DELETE CASCADE,
    nombre    VARCHAR(100) NOT NULL,
    UNIQUE(id_region, nombre)
);

CREATE TABLE distritos (
    id           SERIAL PRIMARY KEY,
    id_provincia INT          NOT NULL REFERENCES provincias(id) ON DELETE CASCADE,
    nombre       VARCHAR(100) NOT NULL,
    UNIQUE(id_provincia, nombre)
);

CREATE TABLE cultivos (
    id                SERIAL PRIMARY KEY,
    id_usuario        INT          NOT NULL REFERENCES usuarios(id),
    id_planta         INT          REFERENCES plantas(id),
    id_fuente_agua    INT          REFERENCES fuentes_agua(id) ON DELETE SET NULL,
    id_distrito       INT          REFERENCES distritos(id) ON DELETE SET NULL,
    lugar             VARCHAR(255),
    nombre_planta     VARCHAR(100) NOT NULL,
    etapa_crecimiento VARCHAR(50),   -- 'semillero','crecimiento','floracion','cosecha'
    area_m2           NUMERIC(10,2),
    fecha_siembra     DATE,
    estado            VARCHAR(20)   DEFAULT 'activo',
    fecha_registro    TIMESTAMP     DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_cultivos_usuario ON cultivos(id_usuario);

COMMENT ON TABLE plantas         IS 'Catalogo botanico de especies vegetales.';
COMMENT ON TABLE umbrales_planta IS 'Limites ideales de cada variable por especie vegetal.';
COMMENT ON TABLE cultivos        IS 'Siembras activas del agricultor vinculadas a su fuente de agua.';


-- =========================================================
-- 8. ASIGNACIONES IOT CENTRALIZADAS
-- Tabla pivote: une usuario + dispositivo + componente + cultivo
-- =========================================================
CREATE TABLE asignaciones_iot (
    id             SERIAL PRIMARY KEY,
    id_usuario     INT          NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    id_dispositivo INT          NOT NULL REFERENCES dispositivos(id) ON DELETE CASCADE,
    id_componente  INT          REFERENCES componentes(id) ON DELETE SET NULL,
    id_fuente_agua INT          REFERENCES fuentes_agua(id) ON DELETE SET NULL,
    id_cultivo     INT          REFERENCES cultivos(id) ON DELETE SET NULL,
    id_tipo_metrica INT          REFERENCES tipos_metrica(id) ON DELETE SET NULL,
    pin_gpio       INT,
    activo         BOOLEAN      DEFAULT FALSE,
    fecha_registro TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_asignaciones_usuario     ON asignaciones_iot(id_usuario);
CREATE INDEX idx_asignaciones_dispositivo ON asignaciones_iot(id_dispositivo);
CREATE INDEX idx_asignaciones_cultivo     ON asignaciones_iot(id_cultivo);
CREATE UNIQUE INDEX unique_active_component_metric_assignment ON asignaciones_iot (id_componente, id_tipo_metrica) WHERE (activo = true);

COMMENT ON TABLE asignaciones_iot IS 'Matriz central que vincula usuario, dispositivo, componente, cultivo y pin GPIO.';


-- =========================================================
-- 9. CONFIGURACION DEL TANQUE
-- Estado en tiempo real del actuador (separado de fuentes_agua)
-- Solo bomba/valvula van aqui — datos fisicos van en fuentes_agua
-- =========================================================
CREATE TABLE configuracion_tanque (
    id_asignacion  INT       PRIMARY KEY REFERENCES asignaciones_iot(id) ON DELETE CASCADE,
    valvula_abierta BOOLEAN  DEFAULT FALSE,
    bomba_encendida BOOLEAN  DEFAULT FALSE,
    actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE configuracion_tanque IS 'Estado actual del actuador (valvula y bomba) vinculado a la asignacion IoT.';


-- =========================================================
-- 10. LECTURAS DE TELEMETRIA
-- Vinculadas a asignaciones_iot (no a sensores directos)
-- =========================================================

-- 10.1 Humedad del suelo (sensor capacitivo)
CREATE TABLE humedad_suelo (
    id            BIGSERIAL     PRIMARY KEY,
    id_asignacion INT           NOT NULL REFERENCES asignaciones_iot(id) ON DELETE CASCADE,
    valor         NUMERIC(10,2),
    porcentaje    NUMERIC(10,2),
    ema           NUMERIC(10,2),
    desviacion    NUMERIC(8,3),
    valido        BOOLEAN       DEFAULT TRUE,
    fecha         TIMESTAMP     DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_hum_suelo_asignacion ON humedad_suelo(id_asignacion);
CREATE INDEX idx_hum_suelo_fecha      ON humedad_suelo(fecha DESC);

-- 10.2 Humedad ambiente (DHT22)
CREATE TABLE humedad_ambiente (
    id            BIGSERIAL     PRIMARY KEY,
    id_asignacion INT           NOT NULL REFERENCES asignaciones_iot(id) ON DELETE CASCADE,
    valor         NUMERIC(10,2),
    porcentaje    NUMERIC(10,2),
    ema           NUMERIC(10,2),
    desviacion    NUMERIC(8,3),
    valido        BOOLEAN       DEFAULT TRUE,
    fecha         TIMESTAMP     DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_hum_amb_asignacion ON humedad_ambiente(id_asignacion);
CREATE INDEX idx_hum_amb_fecha      ON humedad_ambiente(fecha DESC);

-- 10.3 Temperatura ambiente (DHT22)
CREATE TABLE temperatura_ambiente (
    id            BIGSERIAL     PRIMARY KEY,
    id_asignacion INT           NOT NULL REFERENCES asignaciones_iot(id) ON DELETE CASCADE,
    valor         NUMERIC(10,2),
    temperatura   NUMERIC(10,2),
    ema           NUMERIC(10,2),
    desviacion    NUMERIC(8,3),
    valido        BOOLEAN       DEFAULT TRUE,
    fecha         TIMESTAMP     DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_temp_amb_asignacion ON temperatura_ambiente(id_asignacion);
CREATE INDEX idx_temp_amb_fecha      ON temperatura_ambiente(fecha DESC);

-- 10.4 Temperatura suelo (DS18B20)
CREATE TABLE temperatura_suelo (
    id            BIGSERIAL     PRIMARY KEY,
    id_asignacion INT           NOT NULL REFERENCES asignaciones_iot(id) ON DELETE CASCADE,
    valor         NUMERIC(10,2),
    temperatura   NUMERIC(10,2),
    ema           NUMERIC(10,2),
    desviacion    NUMERIC(8,3),
    valido        BOOLEAN       DEFAULT TRUE,
    fecha         TIMESTAMP     DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_temp_suelo_asignacion ON temperatura_suelo(id_asignacion);
CREATE INDEX idx_temp_suelo_fecha      ON temperatura_suelo(fecha DESC);

-- 10.5 Telemetria tanque (HC-SR04 + estado bomba/valvula en tiempo real)
-- estado_bomba y valvula_abierta van aqui como registro historico
CREATE TABLE telemetria_tanque (
    id               BIGSERIAL     PRIMARY KEY,
    id_asignacion    INT           NOT NULL REFERENCES asignaciones_iot(id) ON DELETE CASCADE,
    metodo_medicion VARCHAR(20) NOT NULL DEFAULT 'proximidad',
    distancia_cm     NUMERIC(10,2),
    litros_riego NUMERIC(14,4) CHECK (litros_riego >= 0),
    litros_acumulados NUMERIC(16,4) CHECK (litros_acumulados >= 0),
    caudal_l_min NUMERIC(12,4) CHECK (caudal_l_min >= 0),
    pulsos_riego BIGINT CHECK (pulsos_riego >= 0),
    pulsos_por_litro NUMERIC(12,4) CHECK (pulsos_por_litro > 0),
    nivel_agua_cm    NUMERIC(10,2),
    porcentaje_nivel NUMERIC(10,2),
    estado_nivel     VARCHAR(20),   -- 'optimo','bajo','critico','sin_agua'
    valvula_abierta  BOOLEAN       DEFAULT FALSE,
    bomba_encendida  BOOLEAN       DEFAULT FALSE,
    fuente_control   VARCHAR(30),   -- 'automatico','manual','prediccion_ml'
    fecha            TIMESTAMP     DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_tel_tanque_asignacion ON telemetria_tanque(id_asignacion);
CREATE INDEX idx_tel_tanque_fecha      ON telemetria_tanque(fecha DESC);
CREATE INDEX idx_tel_tanque_nivel      ON telemetria_tanque(estado_nivel);

-- 10.6 Lecturas de bateria (opcional — usar si ESP32 opera con bateria)
CREATE TABLE lecturas_bateria (
    id            BIGSERIAL    PRIMARY KEY,
    id_asignacion INT          NOT NULL REFERENCES asignaciones_iot(id) ON DELETE CASCADE,
    porcentaje    NUMERIC(5,2) NOT NULL,
    voltaje       NUMERIC(4,2),
    fecha         TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_bateria_asignacion ON lecturas_bateria(id_asignacion);
CREATE INDEX idx_bateria_fecha      ON lecturas_bateria(fecha DESC);

COMMENT ON TABLE humedad_suelo      IS 'Lecturas del sensor capacitivo de humedad del suelo con filtro EMA.';
COMMENT ON TABLE humedad_ambiente   IS 'Lecturas del DHT22 — humedad relativa ambiental.';
COMMENT ON TABLE temperatura_ambiente IS 'Lecturas del DHT22 — temperatura del aire.';
COMMENT ON TABLE temperatura_suelo  IS 'Lecturas del DS18B20 — temperatura radicular (12 bits).';
COMMENT ON TABLE telemetria_tanque  IS 'Metricas del deposito: nivel, porcentaje y estado del actuador en cada lectura.';
COMMENT ON TABLE lecturas_bateria   IS 'Opcional: historial de carga si el ESP32 opera con bateria de campo.';


-- =========================================================
-- 11. UMBRALES Y CONFIGURACION DE CONTROL
-- =========================================================
CREATE TABLE configuracion_umbrales (
    id              SERIAL PRIMARY KEY,
    id_usuario      INT          NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    id_cultivo      INT          REFERENCES cultivos(id) ON DELETE CASCADE,
    id_tipo_metrica INT          NOT NULL REFERENCES tipos_metrica(id),
    valor_minimo    NUMERIC(10,2),
    valor_maximo    NUMERIC(10,2),
    actualizado_en  TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(id_usuario, id_cultivo, id_tipo_metrica)
);

CREATE TABLE configuracion_control (
    id                     SERIAL PRIMARY KEY,
    id_usuario             INT          NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    id_cultivo             INT          REFERENCES cultivos(id) ON DELETE CASCADE,
    duracion_riego_max_seg INT          DEFAULT 600
                                           CHECK (duracion_riego_max_seg BETWEEN 60 AND 1800),
    cooldown_minutos       INT          DEFAULT 30
                                           CHECK (cooldown_minutos BETWEEN 1 AND 1440),
    confianza_ml_minima    NUMERIC(4,3) DEFAULT 0.70,
    actualizado_en         TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(id_usuario, id_cultivo)
);

COMMENT ON TABLE configuracion_umbrales IS 'Umbrales personalizados por usuario y cultivo para disparar alertas.';
COMMENT ON TABLE configuracion_control IS 'Tiempo maximo de riego y confianza minima de inferencia ML por cultivo.';


-- =========================================================
-- 12. MODELOS ML Y PREDICCIONES
-- =========================================================
CREATE TABLE modelos_ml (
    id                  SERIAL PRIMARY KEY,
    id_planta           INT          REFERENCES plantas(id) ON DELETE SET NULL,
    nombre_modelo       VARCHAR(100) NOT NULL,
    algoritmo           VARCHAR(50)  NOT NULL,
    descripcion         TEXT,
    ruta_archivo        VARCHAR(255),
    ruta                VARCHAR(255),
    precision_modelo    NUMERIC(5,2),
    precision_score     NUMERIC(5,4),
    recall_score        NUMERIC(5,4),
    f1_score            NUMERIC(5,4),
    version             VARCHAR(20)  DEFAULT '1.0.0',
    es_default          BOOLEAN      DEFAULT FALSE,
    estado              VARCHAR(20)  DEFAULT 'activo',
    creado_por          INT          REFERENCES usuarios(id),
    fecha_registro      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    fecha_entrenamiento TIMESTAMP
);

-- Un modelo activo por usuario (el agricultor elige)
CREATE TABLE cultivo_modelo (
    id               SERIAL PRIMARY KEY,
    id_usuario       INT       NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    id_cultivo       INT       REFERENCES cultivos(id) ON DELETE CASCADE,
    id_modelo        INT       NOT NULL REFERENCES modelos_ml(id),
    activo           BOOLEAN   DEFAULT TRUE,
    fecha_asignacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(id_usuario, id_cultivo)
);

-- Trazabilidad de cambios de modelo
CREATE TABLE historial_modelos (
    id          SERIAL PRIMARY KEY,
    id_usuario  INT       REFERENCES usuarios(id),
    id_modelo   INT       REFERENCES modelos_ml(id),
    accion      VARCHAR(50),   -- 'activado','desactivado','reentrenado'
    descripcion TEXT,
    fecha       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Predicciones con JSONB para variables de entrada flexibles
CREATE TABLE predicciones_ml (
    id               BIGSERIAL     PRIMARY KEY,
    id_usuario       INT           NOT NULL REFERENCES usuarios(id),
    id_modelo        INT           NOT NULL REFERENCES modelos_ml(id),
    id_cultivo       INT           REFERENCES cultivos(id),
    variables_entrada JSONB        NOT NULL,   -- {humedad_suelo, temp_suelo, temp_amb, hum_amb}
    recomendacion    VARCHAR(50),              -- 'regar', 'no_regar'
    probabilidad     NUMERIC(5,2),
    accion_ejecutada BOOLEAN,
    fuente_accion    VARCHAR(30),              -- 'automatico', 'manual_override'
    fecha            TIMESTAMP     DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_predicciones_usuario ON predicciones_ml(id_usuario);
CREATE INDEX idx_predicciones_modelo  ON predicciones_ml(id_modelo);
CREATE INDEX idx_predicciones_fecha   ON predicciones_ml(fecha DESC);

COMMENT ON TABLE modelos_ml       IS 'Modelos de ML disponibles con sus metricas de evaluacion.';
COMMENT ON TABLE cultivo_modelo   IS 'Modelo activo elegido por cada agricultor para cada uno de sus cultivos.';
COMMENT ON TABLE historial_modelos IS 'Trazabilidad de cambios de modelo por usuario.';
COMMENT ON TABLE predicciones_ml  IS 'Inferencias de riego con variables de entrada en JSONB.';


-- =========================================================
-- 13. RIEGO Y PROGRAMACION
-- =========================================================
CREATE TABLE riego (
    id                   BIGSERIAL    PRIMARY KEY,
    id_asignacion        INT          NOT NULL REFERENCES asignaciones_iot(id) ON DELETE CASCADE,
    id_usuario           INT          REFERENCES usuarios(id),
    id_modelo            INT          REFERENCES modelos_ml(id),
    id_prediccion        BIGINT       REFERENCES predicciones_ml(id),
    tipo_riego           VARCHAR(20)  NOT NULL,  -- 'automatico_ml','programado','manual'
    duracion_segundos    INT,
    segundos_acumulados  INT          DEFAULT 0,
    cantidad_agua_litros NUMERIC(10,2),
    motivo_cierre        VARCHAR(50),  -- 'tiempo_max','sensor_ok','manual','nivel_bajo'
    estado               BOOLEAN      DEFAULT FALSE,
    fecha_inicio         TIMESTAMP,
    fecha_fin            TIMESTAMP,
    fecha                TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_riego_asignacion ON riego(id_asignacion);
CREATE INDEX idx_riego_usuario    ON riego(id_usuario);
CREATE INDEX idx_riego_fecha      ON riego(fecha DESC);

CREATE TABLE ejecuciones_riego (
    metodo_medicion VARCHAR(20),
    id                   SERIAL       PRIMARY KEY,
    id_riego             BIGINT       NOT NULL REFERENCES riego(id) ON DELETE CASCADE,
    fecha_inicio         TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_fin            TIMESTAMP,
    distancia_inicial_cm NUMERIC(6,2),
    distancia_final_cm   NUMERIC(6,2),
    duracion_segundos    INT          DEFAULT 0,
    cantidad_agua_litros NUMERIC(10,2) DEFAULT 0.0,
    motivo_cierre        VARCHAR(50)
);

CREATE INDEX idx_ejecuciones_riego_riego ON ejecuciones_riego(id_riego);
CREATE INDEX idx_ejecuciones_riego_fecha ON ejecuciones_riego(fecha_inicio DESC);

COMMENT ON TABLE riego             IS 'Historial completo de sesiones de riego con trazabilidad al modelo ML.';
COMMENT ON TABLE ejecuciones_riego   IS 'Historial individual de arranques/paradas de bomba durante una sesion de riego.';


-- =========================================================
-- 14. REPORTE DE CONSUMO DE AGUA
-- Metrica clave: reduccion del 20-40% de consumo
-- =========================================================
CREATE TABLE reporte_consumo_agua (
    id                       SERIAL PRIMARY KEY,
    id_usuario               INT          NOT NULL REFERENCES usuarios(id),
    id_cultivo               INT          REFERENCES cultivos(id),
    periodo_inicio           DATE         NOT NULL,
    periodo_fin              DATE         NOT NULL,
    consumo_total_litros     NUMERIC(12,3),
    consumo_manual_litros    NUMERIC(12,3),   -- referencia para comparacion
    reduccion_porcentaje     NUMERIC(5,2),    -- % reduccion vs riego manual
    riegos_automaticos       INT,
    riegos_manuales          INT,
    riegos_programados       INT,
    duracion_total_segundos  INT,
    generado_en              TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_reporte_usuario ON reporte_consumo_agua(id_usuario);
CREATE INDEX idx_reporte_periodo ON reporte_consumo_agua(periodo_inicio, periodo_fin);

COMMENT ON TABLE reporte_consumo_agua IS 'Metricas de ahorro hidrico: consumo total, comparativa con riego manual y porcentaje de reduccion (objetivo: 20-40%).';


-- =========================================================
-- 15. FEEDBACK DE AGRICULTORES
-- Encuestas configurables por administradores
-- =========================================================
CREATE TABLE feedback_agricultores (
    id           SERIAL PRIMARY KEY,
    id_usuario   INT         NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    id_cultivo   INT         REFERENCES cultivos(id) ON DELETE SET NULL,
    modulo       VARCHAR(50) NOT NULL,
    tipo         VARCHAR(30) NOT NULL,
    calificacion INT         NOT NULL CHECK (calificacion BETWEEN 1 AND 5),
    mensaje      TEXT        NOT NULL,
    estado       VARCHAR(20) NOT NULL DEFAULT 'nuevo',
    fecha        TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE feedback_preguntas (
    id              SERIAL PRIMARY KEY,
    pregunta        TEXT      NOT NULL,
    tipo            VARCHAR(20) NOT NULL DEFAULT 'rating',
    obligatoria     BOOLEAN   NOT NULL DEFAULT TRUE,
    opciones        JSON,
    descripcion     TEXT,
    orden           INT       NOT NULL DEFAULT 0,
    activo          BOOLEAN   NOT NULL DEFAULT TRUE,
    fecha_registro  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_en  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE feedback_respuestas (
    id              SERIAL PRIMARY KEY,
    id_feedback     INT       NOT NULL REFERENCES feedback_agricultores(id) ON DELETE CASCADE,
    id_pregunta     INT       NOT NULL REFERENCES feedback_preguntas(id) ON DELETE RESTRICT,
    calificacion    INT       CHECK (calificacion IS NULL OR (calificacion BETWEEN 1 AND 5)),
    respuesta_texto TEXT,
    fecha           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_feedback_respuesta_pregunta UNIQUE (id_feedback, id_pregunta)
);

CREATE INDEX idx_feedback_agricultores_usuario ON feedback_agricultores(id_usuario);
CREATE INDEX idx_feedback_agricultores_cultivo ON feedback_agricultores(id_cultivo);
CREATE INDEX idx_feedback_respuestas_feedback  ON feedback_respuestas(id_feedback);
CREATE INDEX idx_feedback_respuestas_pregunta  ON feedback_respuestas(id_pregunta);

COMMENT ON TABLE feedback_agricultores IS 'Envios de feedback realizados por agricultores sobre el sistema.';
COMMENT ON TABLE feedback_preguntas IS 'Preguntas configurables por administradores para la encuesta de feedback.';
COMMENT ON TABLE feedback_respuestas IS 'Calificaciones por pregunta dentro de cada envio de feedback.';


-- =========================================================
-- 16. ALERTAS Y NOTIFICACIONES
-- id_usuario directo para evitar JOINs innecesarios
-- =========================================================
CREATE TABLE tipos_alerta (
    id          SERIAL PRIMARY KEY,
    codigo      VARCHAR(50)  NOT NULL UNIQUE,
    nombre      VARCHAR(100) NOT NULL,
    descripcion TEXT,
    severidad   VARCHAR(20)  NOT NULL,  -- 'info','advertencia','critica','emergencia'
    activo      BOOLEAN      DEFAULT TRUE
);

CREATE TABLE alertas (
    id              BIGSERIAL    PRIMARY KEY,
    id_usuario      INT          NOT NULL REFERENCES usuarios(id),  -- directo, sin JOIN
    id_asignacion   INT          REFERENCES asignaciones_iot(id) ON DELETE CASCADE,
    id_tipo_alerta  INT          NOT NULL REFERENCES tipos_alerta(id),
    id_tipo_metrica INT          REFERENCES tipos_metrica(id),
    mensaje         TEXT         NOT NULL,
    prioridad       VARCHAR(20),
    valor_detectado NUMERIC(10,2),
    umbral          NUMERIC(10,2),
    estado          VARCHAR(20)  DEFAULT 'pendiente',  -- 'pendiente','resuelta','ignorada'
    resuelta_por    INT          REFERENCES usuarios(id),
    resuelta_en     TIMESTAMP,
    comentario      TEXT,
    fecha           TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    ultima_notificacion_en TIMESTAMP,
    proxima_notificacion_en TIMESTAMP,
    cantidad_notificaciones INT NOT NULL DEFAULT 0,
    ultimo_valor_detectado NUMERIC(10,2)
);

CREATE INDEX idx_alertas_usuario      ON alertas(id_usuario);
CREATE INDEX idx_alertas_asignacion   ON alertas(id_asignacion);
CREATE INDEX idx_alertas_tipo         ON alertas(id_tipo_alerta);
CREATE INDEX idx_alertas_estado       ON alertas(estado);
CREATE INDEX idx_alertas_fecha        ON alertas(fecha DESC);
CREATE UNIQUE INDEX uq_alerta_condicion_activa
    ON alertas (id_usuario, id_asignacion, id_tipo_metrica, id_tipo_alerta)
    WHERE estado IN ('pendiente', 'activa');

CREATE TABLE configuracion_notificaciones (
    id              SERIAL PRIMARY KEY,
    id_usuario      INT     NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    id_tipo_alerta  INT     NOT NULL REFERENCES tipos_alerta(id),
    activo          BOOLEAN DEFAULT TRUE,
    canal_email     BOOLEAN DEFAULT TRUE,
    canal_dashboard BOOLEAN DEFAULT TRUE,
    recordatorio_minutos INT,
    UNIQUE(id_usuario, id_tipo_alerta)
);

CREATE TABLE notificaciones (
    id         BIGSERIAL   PRIMARY KEY,
    id_alerta  BIGINT      NOT NULL REFERENCES alertas(id),
    id_usuario INT         NOT NULL REFERENCES usuarios(id),
    canal      VARCHAR(20) NOT NULL,  -- 'email', 'dashboard'
    asunto     VARCHAR(200),
    mensaje    TEXT,
    enviado    BOOLEAN     DEFAULT FALSE,
    enviado_en TIMESTAMP,
    error      TEXT,
    tipo_evento VARCHAR(20) NOT NULL DEFAULT 'activacion',
    intento INT NOT NULL DEFAULT 1,
    intentado_en TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_notificaciones_alerta  ON notificaciones(id_alerta);
CREATE INDEX idx_notificaciones_usuario ON notificaciones(id_usuario);
CREATE INDEX idx_notificaciones_enviado ON notificaciones(enviado);

COMMENT ON TABLE tipos_alerta                IS 'Codigos de eventos de advertencia y critico del sistema.';
COMMENT ON TABLE alertas                     IS 'Historial de alarmas con id_usuario directo para notificacion inmediata.';
COMMENT ON TABLE configuracion_notificaciones IS 'Canales de alerta activos por usuario y tipo.';
COMMENT ON TABLE notificaciones              IS 'Envios de avisos por correo o dashboard con registro de errores.';


-- =========================================================
-- 17. AUDITORIA Y LOGS
-- =========================================================
CREATE TABLE logs_sistema (
    id          BIGSERIAL    PRIMARY KEY,
    id_usuario  INT          REFERENCES usuarios(id),
    accion      VARCHAR(100) NOT NULL,
    modulo      VARCHAR(50),
    descripcion TEXT,
    ip_acceso   INET,
    fecha       TIMESTAMP    DEFAULT (now() AT TIME ZONE 'utc')
);

CREATE INDEX idx_logs_usuario ON logs_sistema(id_usuario);
CREATE INDEX idx_logs_fecha   ON logs_sistema(fecha DESC);

COMMENT ON TABLE logs_sistema IS 'Auditoria completa de acciones por usuario, modulo e IP.';

-- =========================================================
-- MEJORAS POSTERIORES: ALMACENES & STOCK (AÑADIDO V4.0)
-- =========================================================
CREATE TABLE almacenes (
    id             SERIAL PRIMARY KEY,
    nombre         VARCHAR(100) NOT NULL UNIQUE,
    id_distrito    INT          REFERENCES distritos(id) ON DELETE SET NULL,
    direccion      TEXT,
    fecha_registro TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE dispositivos ADD COLUMN id_almacen INT REFERENCES almacenes(id) ON DELETE SET NULL;
ALTER TABLE dispositivos ADD COLUMN en_almacen BOOLEAN DEFAULT TRUE;
ALTER TABLE componentes ADD COLUMN id_almacen INT REFERENCES almacenes(id) ON DELETE SET NULL;
ALTER TABLE componentes ADD COLUMN en_almacen BOOLEAN DEFAULT TRUE;

-- =========================================================
-- 18. VERSIONES E INSTALACIONES DE FIRMWARE
-- =========================================================
CREATE TABLE versiones_firmware (
    id               SERIAL PRIMARY KEY,
    version          VARCHAR(30)  NOT NULL,
    chip             VARCHAR(30)  NOT NULL,
    tipo_dispositivo VARCHAR(30)  NOT NULL,
    descripcion      TEXT,
    manifiesto       JSONB        NOT NULL,
    directorio       VARCHAR(255) NOT NULL,
    ubicacion_archivo VARCHAR(500),
    publicado        BOOLEAN      NOT NULL DEFAULT TRUE,
    descontinuado    BOOLEAN      NOT NULL DEFAULT FALSE,
    creado_por       INT          NOT NULL REFERENCES usuarios(id),
    fecha_registro   TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_descontinuado TIMESTAMP,
    CONSTRAINT uq_firmware_release UNIQUE (version, chip, tipo_dispositivo)
);

CREATE TABLE instalaciones_firmware (
    id               SERIAL PRIMARY KEY,
    id_firmware      INT         NOT NULL REFERENCES versiones_firmware(id),
    id_dispositivo   INT         NOT NULL REFERENCES dispositivos(id),
    id_administrador INT         NOT NULL REFERENCES usuarios(id),
    chip_detectado   VARCHAR(50),
    mac_detectada    VARCHAR(100),
    estado           VARCHAR(30) NOT NULL DEFAULT 'iniciada',
    progreso         INT         NOT NULL DEFAULT 0 CHECK (progreso BETWEEN 0 AND 100),
    mensaje          TEXT,
    fecha_inicio     TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_fin        TIMESTAMP
);

CREATE INDEX idx_instalaciones_firmware_dispositivo ON instalaciones_firmware(id_dispositivo);
CREATE INDEX idx_instalaciones_firmware_fecha ON instalaciones_firmware(fecha_inicio DESC);

COMMENT ON TABLE versiones_firmware IS 'Catalogo de versiones y manifiestos binarios aprobados para ESP32.';
COMMENT ON TABLE instalaciones_firmware IS 'Auditoria de instalaciones de firmware realizadas por administradores.';

COMMENT ON TABLE almacenes IS 'Ubicaciones físicas de almacén donde se guarda el stock de hardware.';
