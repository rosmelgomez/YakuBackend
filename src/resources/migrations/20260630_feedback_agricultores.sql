CREATE TABLE IF NOT EXISTS feedback_agricultores (
    id SERIAL PRIMARY KEY,
    id_usuario INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    id_cultivo INTEGER REFERENCES cultivos(id) ON DELETE SET NULL,
    modulo VARCHAR(50) NOT NULL,
    tipo VARCHAR(30) NOT NULL,
    calificacion INTEGER NOT NULL,
    mensaje TEXT NOT NULL,
    estado VARCHAR(20) NOT NULL DEFAULT 'nuevo',
    fecha TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_feedback_calificacion CHECK (calificacion BETWEEN 1 AND 5)
);

CREATE INDEX IF NOT EXISTS ix_feedback_agricultores_id_usuario
    ON feedback_agricultores(id_usuario);

CREATE INDEX IF NOT EXISTS ix_feedback_agricultores_id_cultivo
    ON feedback_agricultores(id_cultivo);

CREATE TABLE IF NOT EXISTS feedback_preguntas (
    id SERIAL PRIMARY KEY,
    pregunta TEXT NOT NULL,
    tipo VARCHAR(20) NOT NULL DEFAULT 'rating',
    obligatoria BOOLEAN NOT NULL DEFAULT TRUE,
    opciones JSON,
    descripcion TEXT,
    orden INTEGER NOT NULL DEFAULT 0,
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    fecha_registro TIMESTAMP NOT NULL DEFAULT NOW(),
    actualizado_en TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS feedback_respuestas (
    id SERIAL PRIMARY KEY,
    id_feedback INTEGER NOT NULL REFERENCES feedback_agricultores(id) ON DELETE CASCADE,
    id_pregunta INTEGER NOT NULL REFERENCES feedback_preguntas(id) ON DELETE RESTRICT,
    calificacion INTEGER,
    respuesta_texto TEXT,
    fecha TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_feedback_respuesta_calificacion CHECK (calificacion IS NULL OR (calificacion BETWEEN 1 AND 5)),
    CONSTRAINT uq_feedback_respuesta_pregunta UNIQUE (id_feedback, id_pregunta)
);

CREATE INDEX IF NOT EXISTS ix_feedback_respuestas_id_feedback
    ON feedback_respuestas(id_feedback);

CREATE INDEX IF NOT EXISTS ix_feedback_respuestas_id_pregunta
    ON feedback_respuestas(id_pregunta);

INSERT INTO feedback_preguntas (pregunta, tipo, obligatoria, opciones, orden, activo)
SELECT pregunta, tipo, obligatoria, opciones::json, orden, activo
FROM (
    VALUES
        ('¿Con qué frecuencia utilizas la plataforma Yaku?', 'select', TRUE, '["Varias veces al día", "Una vez al día", "Varios días a la semana", "Una vez a la semana", "Menos de una vez a la semana"]', 1, TRUE),
        ('¿Cómo valorarías la utilidad del sistema de alertas?', 'rating', TRUE, NULL, 2, TRUE),
        ('¿Las recomendaciones de riego se han ajustado a las necesidades reales de tu cultivo?', 'rating', TRUE, NULL, 3, TRUE),
        ('¿Qué aspecto mejorarías de la plataforma?', 'text', FALSE, NULL, 4, TRUE),
        ('¿Recomendarías Yaku a otros agricultores?', 'rating', TRUE, NULL, 5, TRUE),
        ('¿Qué funcionalidad usas con más frecuencia?', 'select', FALSE, '["Control de riego", "Sensores", "Alertas", "Modelos IA"]', 6, FALSE)
) AS defaults(pregunta, tipo, obligatoria, opciones, orden, activo)
WHERE NOT EXISTS (SELECT 1 FROM feedback_preguntas);
