-- Tipo de aviso para el administrador: un agricultor se registro y queda pendiente
-- de aprobacion. El clic en la notificacion lleva a /dashboard/administrador/usuarios.
INSERT INTO tipos_alerta (id, codigo, nombre, descripcion, severidad, activo)
SELECT (SELECT COALESCE(MAX(id), 0) + 1 FROM tipos_alerta), 'USUARIO_REGISTRADO', 'Nuevo usuario registrado', 'Aviso al administrador cuando un agricultor se registra y queda pendiente de aprobación.', 'info', TRUE
WHERE NOT EXISTS (SELECT 1 FROM tipos_alerta WHERE codigo = 'USUARIO_REGISTRADO');
