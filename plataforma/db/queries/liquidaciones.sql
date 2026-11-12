-- Etapa 3: parámetros, tasas, gastos, cargos y liquidaciones (dentro de EnTenant: RLS).

-- name: BloquearConsorcio :one
-- Serializa las escrituras que tocan la cuenta corriente o el estado de las liquidaciones
-- de un consorcio (cálculo, emisión, pagos).
SELECT id FROM consorcios WHERE id = $1 FOR UPDATE;

-- ── Parámetros ───────────────────────────────────────────────────────────────

-- name: CrearParametros :one
INSERT INTO parametros_consorcio (administracion_id, consorcio_id, vigente_desde, dia_vencimiento,
                                  fondo_reserva_mensual, grupo_fondo_id)
VALUES (app_administracion_id(), $1, $2, $3, $4, $5)
RETURNING *;

-- name: ListarParametros :many
SELECT * FROM parametros_consorcio WHERE consorcio_id = $1 ORDER BY vigente_desde;

-- name: ParametrosVigentes :one
SELECT * FROM parametros_consorcio
 WHERE consorcio_id = sqlc.arg(consorcio_id) AND vigente_desde <= sqlc.arg(fecha)
 ORDER BY vigente_desde DESC LIMIT 1;

-- ── Tasas de mora ────────────────────────────────────────────────────────────

-- name: CrearTasa :one
INSERT INTO tasas_mora (administracion_id, consorcio_id, vigente_desde, tasa_mensual, fundamento)
VALUES (app_administracion_id(), $1, $2, $3, $4)
RETURNING *;

-- name: ListarTasas :many
SELECT * FROM tasas_mora WHERE consorcio_id = $1 ORDER BY vigente_desde;

-- name: TasaVigente :one
SELECT * FROM tasas_mora
 WHERE consorcio_id = sqlc.arg(consorcio_id) AND vigente_desde <= sqlc.arg(fecha)
 ORDER BY vigente_desde DESC LIMIT 1;

-- name: UltimoPeriodoCerrado :one
-- Último período aprobado o emitido (null si no hay): las tasas y parámetros nuevos tienen
-- que regir después, para no cambiar una liquidación cerrada.
SELECT max(periodo)::date AS periodo FROM liquidaciones
 WHERE consorcio_id = $1 AND estado IN ('aprobada', 'emitida');

-- ── Gastos ───────────────────────────────────────────────────────────────────

-- name: CrearGasto :one
INSERT INTO gastos (administracion_id, consorcio_id, periodo, grupo_id, concepto, proveedor, importe,
                    naturaleza, habitualidad, financiacion, respaldo)
VALUES (app_administracion_id(), $1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
RETURNING *;

-- name: ListarGastos :many
SELECT * FROM gastos WHERE consorcio_id = $1 AND periodo = $2 ORDER BY creado_en;

-- name: ObtenerGasto :one
SELECT * FROM gastos WHERE id = $1;

-- name: AnularGasto :one
UPDATE gastos SET anulado_en = now(), anulado_motivo = sqlc.arg(motivo)
 WHERE id = sqlc.arg(id) AND anulado_en IS NULL
RETURNING *;

-- name: GastosParaLiquidar :many
-- Los gastos pagados con el fondo de reserva no se cobran a las unidades.
SELECT * FROM gastos
 WHERE consorcio_id = $1 AND periodo = $2 AND anulado_en IS NULL AND financiacion = 'expensas'
 ORDER BY creado_en;

-- ── Cargos particulares ──────────────────────────────────────────────────────

-- name: CrearCargo :one
INSERT INTO cargos_particulares (administracion_id, consorcio_id, unidad_id, periodo, concepto, importe)
VALUES (app_administracion_id(), $1, $2, $3, $4, $5)
RETURNING *;

-- name: ListarCargos :many
SELECT * FROM cargos_particulares WHERE consorcio_id = $1 AND periodo = $2 ORDER BY creado_en;

-- name: ObtenerCargo :one
SELECT * FROM cargos_particulares WHERE id = $1;

-- name: AnularCargo :one
UPDATE cargos_particulares SET anulado_en = now(), anulado_motivo = sqlc.arg(motivo)
 WHERE id = sqlc.arg(id) AND anulado_en IS NULL
RETURNING *;

-- name: CargosParaLiquidar :many
SELECT * FROM cargos_particulares
 WHERE consorcio_id = $1 AND periodo = $2 AND anulado_en IS NULL
 ORDER BY creado_en;

-- ── Liquidaciones ────────────────────────────────────────────────────────────

-- name: CrearLiquidacion :one
INSERT INTO liquidaciones (administracion_id, consorcio_id, periodo)
VALUES (app_administracion_id(), $1, $2)
RETURNING *;

-- name: ListarLiquidaciones :many
SELECT * FROM liquidaciones WHERE consorcio_id = $1 ORDER BY periodo DESC;

-- name: ObtenerLiquidacion :one
SELECT * FROM liquidaciones WHERE id = $1;

-- name: LiquidacionPorPeriodo :one
SELECT * FROM liquidaciones WHERE consorcio_id = $1 AND periodo = $2;

-- name: EstadoLiquidacionPeriodo :one
-- Estado de la liquidación de un período ('' si no existe).
SELECT coalesce((SELECT estado FROM liquidaciones l WHERE l.consorcio_id = $1 AND l.periodo = $2), '')::text AS estado;

-- name: HayPosteriorCerrada :one
SELECT EXISTS (SELECT 1 FROM liquidaciones
                WHERE consorcio_id = $1 AND periodo > $2 AND estado IN ('aprobada', 'emitida')) AS hay;

-- name: HayAnteriorAbierta :one
-- Hay una liquidación anterior todavía sin emitir (no se puede aprobar ni emitir salteando).
SELECT EXISTS (SELECT 1 FROM liquidaciones
                WHERE consorcio_id = $1 AND periodo < $2 AND estado <> 'emitida') AS hay;

-- name: HayEmitidas :one
SELECT EXISTS (SELECT 1 FROM liquidaciones WHERE consorcio_id = $1 AND estado = 'emitida') AS hay;

-- name: GuardarCalculo :one
INSERT INTO liquidacion_calculos (administracion_id, consorcio_id, liquidacion_id, fecha_calculo,
                                  tasa_mensual, tasa_id, entrada, resultado, total_cargos, calculado_por)
VALUES (app_administracion_id(), $1, $2, $3, $4, $5, $6, $7, $8, $9)
RETURNING *;

-- name: ObtenerCalculo :one
SELECT * FROM liquidacion_calculos WHERE id = $1;

-- name: ListarCalculos :many
SELECT id, fecha_calculo, tasa_mensual, total_cargos, calculado_por, creado_en
  FROM liquidacion_calculos WHERE liquidacion_id = $1 ORDER BY creado_en;

-- name: MarcarCalculada :one
UPDATE liquidaciones SET estado = 'calculada', calculo_id = sqlc.arg(calculo_id)
 WHERE id = sqlc.arg(id)
RETURNING *;

-- name: MarcarAprobada :one
UPDATE liquidaciones SET estado = 'aprobada' WHERE id = $1 RETURNING *;

-- name: MarcarEmitida :one
UPDATE liquidaciones SET estado = 'emitida', vencimiento = sqlc.arg(vencimiento), emitida_en = now()
 WHERE id = sqlc.arg(id)
RETURNING *;

-- name: MarcarReabierta :one
UPDATE liquidaciones SET estado = 'calculada', vencimiento = NULL, emitida_en = NULL
 WHERE id = $1
RETURNING *;

-- ── Condonaciones ────────────────────────────────────────────────────────────

-- name: Condonar :exec
INSERT INTO liquidacion_condonaciones (administracion_id, consorcio_id, liquidacion_id, unidad_id, motivo, creado_por)
VALUES (app_administracion_id(), $1, $2, $3, $4, $5)
ON CONFLICT (liquidacion_id, unidad_id) DO NOTHING;

-- name: QuitarCondonacion :execrows
DELETE FROM liquidacion_condonaciones WHERE liquidacion_id = $1 AND unidad_id = $2;

-- name: ListarCondonaciones :many
SELECT * FROM liquidacion_condonaciones WHERE liquidacion_id = $1;

-- name: MarcarDesactualizada :execrows
-- Cambió algo de lo que usa el cálculo (gastos, cargos, condonaciones): hay que recalcular.
UPDATE liquidaciones SET estado = 'borrador'
 WHERE consorcio_id = $1 AND periodo = $2 AND estado = 'calculada';
