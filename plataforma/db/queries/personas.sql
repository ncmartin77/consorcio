-- name: BuscarPersonas :many
SELECT id, nombre, documento, email, telefono, notas, creado_en
  FROM personas
 WHERE sqlc.narg(texto)::text IS NULL
    OR lower(nombre) LIKE '%' || lower(sqlc.narg(texto)::text) || '%'
    OR documento = sqlc.narg(texto)::text
    OR lower(email) = lower(sqlc.narg(texto)::text)
 ORDER BY lower(nombre)
 LIMIT 200;

-- name: ObtenerPersona :one
SELECT *
  FROM personas WHERE id = $1;

-- name: CrearPersona :one
INSERT INTO personas (administracion_id, nombre, documento, email, telefono, notas)
VALUES (app_administracion_id(), $1, $2, $3, $4, $5)
RETURNING *;

-- name: ActualizarPersona :one
UPDATE personas SET
  nombre    = coalesce(sqlc.narg(nombre), nombre),
  documento = coalesce(sqlc.narg(documento), documento),
  email     = coalesce(sqlc.narg(email), email),
  telefono  = coalesce(sqlc.narg(telefono), telefono),
  notas     = coalesce(sqlc.narg(notas), notas)
 WHERE id = sqlc.arg(id)
RETURNING *;

-- name: VinculosDeUnidad :many
-- Con fecha: los vigentes ese día. Sin fecha: toda la historia.
SELECT v.id, v.unidad_id, v.persona_id, p.nombre AS persona_nombre, v.tipo_vinculo,
       v.porcentaje_titularidad, v.recibe_liquidacion, v.desde, v.hasta
  FROM unidad_personas v
  JOIN personas p ON p.id = v.persona_id
 WHERE v.unidad_id = sqlc.arg(unidad_id)
   AND (sqlc.narg(fecha)::date IS NULL
        OR (v.desde <= sqlc.narg(fecha)::date AND (v.hasta IS NULL OR v.hasta > sqlc.narg(fecha)::date)))
 ORDER BY v.tipo_vinculo, v.desde, p.nombre;

-- name: VinculosDePersona :many
SELECT v.id, v.unidad_id, u.codigo AS unidad_codigo, u.consorcio_id, v.tipo_vinculo,
       v.porcentaje_titularidad, v.recibe_liquidacion, v.desde, v.hasta
  FROM unidad_personas v
  JOIN unidades u ON u.id = v.unidad_id
 WHERE v.persona_id = $1
 ORDER BY v.desde DESC;

-- name: CrearVinculo :one
INSERT INTO unidad_personas (administracion_id, unidad_id, persona_id, tipo_vinculo,
                             porcentaje_titularidad, recibe_liquidacion, desde)
VALUES (app_administracion_id(), $1, $2, $3, $4, $5, $6)
RETURNING *;

-- name: FinalizarVinculo :one
UPDATE unidad_personas SET hasta = sqlc.arg(hasta)
 WHERE id = sqlc.arg(id) AND hasta IS NULL
RETURNING *;
