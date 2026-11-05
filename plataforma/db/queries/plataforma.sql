-- name: AdministracionesDeUsuario :many
SELECT a.id, a.nombre, m.rol
  FROM membresias m
  JOIN administraciones a ON a.id = m.administracion_id
 WHERE m.usuario_id = $1 AND a.activa
 ORDER BY a.nombre;

-- name: RolEnAdministracion :one
SELECT m.rol
  FROM membresias m
  JOIN administraciones a ON a.id = m.administracion_id
 WHERE m.usuario_id = $1 AND m.administracion_id = $2 AND a.activa;
