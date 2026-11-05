-- Usuarios, sesiones y auditoría (tablas de plataforma, sin RLS).

-- name: UsuarioPorEmail :one
SELECT id, email, nombre, password_hash, activo
  FROM usuarios
 WHERE lower(email) = lower(sqlc.arg(email));

-- name: CrearUsuario :one
INSERT INTO usuarios (email, nombre, password_hash)
VALUES (lower(sqlc.arg(email)), sqlc.arg(nombre), sqlc.arg(password_hash))
RETURNING id;

-- name: CrearAdministracion :one
INSERT INTO administraciones (nombre, cuit) VALUES ($1, $2) RETURNING id;

-- name: CrearMembresia :exec
INSERT INTO membresias (usuario_id, administracion_id, rol) VALUES ($1, $2, $3);

-- name: CrearSesion :exec
INSERT INTO sesiones (token_hash, usuario_id, vence_en, ip, user_agent)
VALUES ($1, $2, $3, $4, $5);

-- name: SesionVigente :one
-- Vigente: no venció, se usó después de sqlc.arg(usada_desde) y el usuario sigue activo.
SELECT s.usuario_id, s.ultimo_uso, u.email, u.nombre
  FROM sesiones s
  JOIN usuarios u ON u.id = s.usuario_id
 WHERE s.token_hash = sqlc.arg(token_hash)
   AND s.vence_en > now()
   AND s.ultimo_uso > sqlc.arg(usada_desde)
   AND u.activo;

-- name: TocarSesion :exec
UPDATE sesiones SET ultimo_uso = now() WHERE token_hash = $1;

-- name: BorrarSesion :exec
DELETE FROM sesiones WHERE token_hash = $1;

-- name: BorrarSesionesVencidas :execrows
DELETE FROM sesiones WHERE vence_en <= now() OR ultimo_uso <= sqlc.arg(usada_desde);

-- name: RegistrarAuditoria :exec
INSERT INTO auditoria (administracion_id, usuario_id, accion, detalle, ip)
VALUES ($1, $2, $3, $4, $5);
