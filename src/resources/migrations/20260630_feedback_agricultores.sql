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
    calificacion INTEGER NOT NULL,
    fecha TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_feedback_respuesta_calificacion CHECK (calificacion BETWEEN 1 AND 5),
    CONSTRAINT uq_feedback_respuesta_pregunta UNIQUE (id_feedback, id_pregunta)
);

CREATE INDEX IF NOT EXISTS ix_feedback_respuestas_id_feedback
    ON feedback_respuestas(id_feedback);

CREATE INDEX IF NOT EXISTS ix_feedback_respuestas_id_pregunta
    ON feedback_respuestas(id_pregunta);

INSERT INTO feedback_preguntas (pregunta, orden, activo)
SELECT pregunta, orden, TRUE
FROM (
    VALUES
        ('Te parecio facil usar y entender el sistema Yaku?', 1),
        ('Fueron claras las recomendaciones y alertas del sistema?', 2),
        ('Consideras utiles o adecuadas las recomendaciones de riego?', 3),
        ('La interaccion con el sistema se realizo sin dificultades?', 4),
        ('Estas satisfecho con la experiencia general del sistema?', 5)
) AS defaults(pregunta, orden)
WHERE NOT EXISTS (SELECT 1 FROM feedback_preguntas);
