-- Consultas del tenant: se ejecutan dentro de database.EnTenant; RLS filtra por administración.

-- name: ListarConsorcios :many
SELECT id, administracion_id, nombre, direccion, cuit, creado_en
  FROM consorcios
 ORDER BY nombre;

-- name: CrearConsorcio :one
INSERT INTO consorcios (administracion_id, nombre, direccion, cuit)
VALUES (app_administracion_id(), $1, $2, $3)
RETURNING id, administracion_id, nombre, direccion, cuit, creado_en;
