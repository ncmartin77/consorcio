-- Consultas del tenant (dentro de database.EnTenant; RLS filtra por administración).

-- name: ObtenerConsorcio :one
SELECT id, administracion_id, nombre, direccion, cuit, creado_en
  FROM consorcios WHERE id = $1;

-- name: ListarUnidades :many
SELECT *
  FROM unidades
 WHERE consorcio_id = $1
 ORDER BY length(codigo), codigo;

-- name: ObtenerUnidad :one
SELECT *
  FROM unidades WHERE id = $1;

-- name: CrearUnidad :one
INSERT INTO unidades (administracion_id, consorcio_id, codigo, descripcion, piso, tipo)
VALUES (app_administracion_id(), $1, $2, $3, $4, $5)
RETURNING *;

-- name: ActualizarUnidad :one
UPDATE unidades SET
  codigo      = coalesce(sqlc.narg(codigo), codigo),
  descripcion = coalesce(sqlc.narg(descripcion), descripcion),
  piso        = coalesce(sqlc.narg(piso), piso),
  tipo        = coalesce(sqlc.narg(tipo), tipo),
  activa      = coalesce(sqlc.narg(activa), activa)
 WHERE id = sqlc.arg(id)
RETURNING *;
