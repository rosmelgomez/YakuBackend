ALTER TABLE feedback_preguntas ADD COLUMN IF NOT EXISTS tipo VARCHAR(20) DEFAULT 'rating';
ALTER TABLE feedback_preguntas ADD COLUMN IF NOT EXISTS obligatoria BOOLEAN DEFAULT TRUE;
ALTER TABLE feedback_preguntas ADD COLUMN IF NOT EXISTS opciones JSON;

ALTER TABLE feedback_respuestas ADD COLUMN IF NOT EXISTS respuesta_texto TEXT;

ALTER TABLE feedback_respuestas ALTER COLUMN calificacion DROP NOT NULL;
