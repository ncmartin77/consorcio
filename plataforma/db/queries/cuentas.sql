-- Etapa 3: cuenta corriente de las unidades (partidas, pagos y aplicaciones).
-- Pendiente de una partida = importe − lo aplicado (sin contar lo anulado).
-- Saldo a favor de un pago = importe − lo aplicado.

-- name: CrearPartida :one
INSERT INTO partidas (administracion_id, consorcio_id, unidad_id, liquidacion_id, periodo, tipo,
                      concepto, detalle, importe, vencimiento, deuda_inicial)
VALUES (app_administracion_id(), $1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
RETURNING *;

-- name: PartidasConPendiente :many
-- Partidas vigentes de una unidad con lo que falta pagar (solo las que deben algo).
SELECT p.id, p.periodo, p.tipo, p.concepto, p.vencimiento, p.deuda_inicial,
       (p.importe - coalesce(sum(a.importe), 0))::numeric(14,2) AS pendiente
  FROM partidas p
  LEFT JOIN aplicaciones a ON a.partida_id = p.id AND a.anulado_en IS NULL
 WHERE p.unidad_id = $1 AND p.anulado_en IS NULL
 GROUP BY p.id
HAVING p.importe - coalesce(sum(a.importe), 0) > 0
 ORDER BY p.periodo, p.creado_en;

-- name: PendientesConsorcio :many
-- Lo mismo para todas las unidades de un consorcio (para calcular una liquidación).
SELECT p.unidad_id, p.tipo, p.vencimiento, p.deuda_inicial,
       (p.importe - coalesce(sum(a.importe), 0))::numeric(14,2) AS pendiente
  FROM partidas p
  LEFT JOIN aplicaciones a ON a.partida_id = p.id AND a.anulado_en IS NULL
 WHERE p.consorcio_id = $1 AND p.anulado_en IS NULL
 GROUP BY p.id
HAVING p.importe - coalesce(sum(a.importe), 0) > 0;

-- name: CreditosConsorcio :many
-- Saldo a favor de cada unidad: lo que sus pagos vigentes no aplicaron.
SELECT p.unidad_id, sum(p.importe - coalesce(ap.aplicado, 0))::numeric(14,2) AS credito
  FROM pagos p
  LEFT JOIN (SELECT pago_id, sum(importe) AS aplicado FROM aplicaciones
              WHERE anulado_en IS NULL GROUP BY pago_id) ap ON ap.pago_id = p.id
 WHERE p.consorcio_id = $1 AND p.anulado_en IS NULL
 GROUP BY p.unidad_id
HAVING sum(p.importe - coalesce(ap.aplicado, 0)) > 0;

-- name: PagosConCredito :many
-- Pagos de la unidad que tienen saldo sin aplicar, del más viejo al más nuevo.
SELECT p.id, (p.importe - coalesce(sum(a.importe), 0))::numeric(14,2) AS disponible
  FROM pagos p
  LEFT JOIN aplicaciones a ON a.pago_id = p.id AND a.anulado_en IS NULL
 WHERE p.unidad_id = $1 AND p.anulado_en IS NULL
 GROUP BY p.id
HAVING p.importe - coalesce(sum(a.importe), 0) > 0
 ORDER BY p.fecha, p.creado_en;

-- name: CrearAplicacion :exec
INSERT INTO aplicaciones (administracion_id, unidad_id, pago_id, partida_id, importe, origen)
VALUES (app_administracion_id(), $1, $2, $3, $4, $5);

-- name: UnidadesConPartidasDeLiquidacion :many
SELECT DISTINCT unidad_id FROM partidas WHERE liquidacion_id = $1;

-- name: AplicacionesDePagosEnLiquidacion :one
-- Pagos (no saldo a favor) aplicados a partidas de la liquidación: si hay, no se reabre.
SELECT count(*) AS cantidad
  FROM aplicaciones a JOIN partidas p ON p.id = a.partida_id
 WHERE p.liquidacion_id = $1 AND p.anulado_en IS NULL
   AND a.anulado_en IS NULL AND a.origen = 'pago';

-- name: AnularAplicacionesDeLiquidacion :execrows
UPDATE aplicaciones SET anulado_en = now(), anulado_motivo = sqlc.arg(motivo)
 WHERE anulado_en IS NULL
   AND partida_id IN (SELECT id FROM partidas WHERE liquidacion_id = sqlc.arg(liquidacion_id));

-- name: AnularPartidasDeLiquidacion :execrows
UPDATE partidas SET anulado_en = now(), anulado_motivo = sqlc.arg(motivo)
 WHERE liquidacion_id = sqlc.arg(liquidacion_id) AND anulado_en IS NULL;

-- name: AnularAplicacionesDePago :execrows
UPDATE aplicaciones SET anulado_en = now(), anulado_motivo = sqlc.arg(motivo)
 WHERE pago_id = sqlc.arg(pago_id) AND anulado_en IS NULL;

-- name: CrearPago :one
INSERT INTO pagos (administracion_id, consorcio_id, unidad_id, fecha, importe, medio, referencia, creado_por)
VALUES (app_administracion_id(), $1, $2, $3, $4, $5, $6, $7)
RETURNING *;

-- name: ObtenerPago :one
SELECT * FROM pagos WHERE id = $1;

-- name: AnularPago :one
UPDATE pagos SET anulado_en = now(), anulado_motivo = sqlc.arg(motivo)
 WHERE id = sqlc.arg(id) AND anulado_en IS NULL
RETURNING *;

-- name: PartidasDeUnidad :many
-- Cuenta corriente completa de la unidad (incluye lo anulado, marcado).
SELECT p.*, (p.importe - coalesce(sum(a.importe) FILTER (WHERE a.anulado_en IS NULL), 0))::numeric(14,2) AS pendiente
  FROM partidas p
  LEFT JOIN aplicaciones a ON a.partida_id = p.id
 WHERE p.unidad_id = $1
 GROUP BY p.id
 ORDER BY p.periodo, p.tipo, p.creado_en;

-- name: PagosDeUnidad :many
SELECT p.*, coalesce(sum(a.importe) FILTER (WHERE a.anulado_en IS NULL), 0)::numeric(14,2) AS aplicado
  FROM pagos p
  LEFT JOIN aplicaciones a ON a.pago_id = p.id
 WHERE p.unidad_id = $1
 GROUP BY p.id
 ORDER BY p.fecha, p.creado_en;

-- name: AplicacionesDeUnidad :many
SELECT * FROM aplicaciones WHERE unidad_id = $1 ORDER BY creado_en;

-- name: HayPartidasConsorcio :one
SELECT EXISTS (SELECT 1 FROM partidas WHERE consorcio_id = $1 AND anulado_en IS NULL) AS hay;

-- name: PagosDeAjusteDeLiquidacion :many
-- Ajustes a favor (líneas negativas) que generó la emisión de una liquidación.
SELECT * FROM pagos
 WHERE consorcio_id = sqlc.arg(consorcio_id) AND medio = 'bonificacion'
   AND referencia LIKE sqlc.arg(prefijo)::text || '%' AND anulado_en IS NULL;
