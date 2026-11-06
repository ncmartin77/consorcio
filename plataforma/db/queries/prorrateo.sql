-- name: ListarGrupos :many
SELECT *
  FROM grupos_prorrateo WHERE consorcio_id = $1 ORDER BY nombre;

-- name: ObtenerGrupo :one
SELECT *
  FROM grupos_prorrateo WHERE id = $1;

-- name: CrearGrupo :one
INSERT INTO grupos_prorrateo (administracion_id, consorcio_id, nombre, descripcion)
VALUES (app_administracion_id(), $1, $2, $3)
RETURNING *;

-- name: CoeficientesVigentes :many
SELECT c.unidad_id, u.codigo AS unidad_codigo, c.porcentaje, c.vigente_desde, c.vigente_hasta
  FROM unidad_coeficientes c
  JOIN unidades u ON u.id = c.unidad_id
 WHERE c.grupo_id = sqlc.arg(grupo_id)
   AND c.vigente_desde <= sqlc.arg(fecha)
   AND (c.vigente_hasta IS NULL OR c.vigente_hasta > sqlc.arg(fecha))
 ORDER BY length(u.codigo), u.codigo;

-- name: UltimaVigenciaGrupo :one
-- Fecha de la tabla de coeficientes más nueva del grupo (null si no hay ninguna).
SELECT max(vigente_desde)::date AS ultima FROM unidad_coeficientes WHERE grupo_id = $1;

-- name: CerrarCoeficientes :execrows
UPDATE unidad_coeficientes SET vigente_hasta = sqlc.arg(desde)
 WHERE grupo_id = sqlc.arg(grupo_id) AND vigente_hasta IS NULL;

-- name: InsertarCoeficiente :exec
INSERT INTO unidad_coeficientes (administracion_id, consorcio_id, grupo_id, unidad_id, porcentaje, vigente_desde)
VALUES (app_administracion_id(), $1, $2, $3, $4, $5);
