-- Etapa 3: liquidaciones y cuenta corriente.
-- Reglas en docs/decisiones-liquidaciones.md (alineadas con la v10.1 del sistema actual).
--
-- Períodos: siempre el primer día del mes. La liquidación del período P reparte los
-- gastos del período P−1 (mes vencido) y los cargos particulares de P.
--
-- Nada se borra: los gastos, cargos, pagos, partidas y aplicaciones se ANULAN con fecha,
-- usuario y motivo. Las consultas ignoran lo anulado. La auditoría guarda quién hizo qué.

-- +goose Up

-- ── Parámetros de liquidación con vigencia ────────────────────────────────────
-- Vencimiento y fondo de reserva de un consorcio desde una fecha. Para liquidar P se usa
-- el último registro con vigente_desde <= P (día 1 del mes de la liquidación).
CREATE TABLE parametros_consorcio (
  id                uuid NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  administracion_id uuid NOT NULL,
  consorcio_id      uuid NOT NULL,
  vigente_desde     date NOT NULL CHECK (extract(day FROM vigente_desde) = 1),
  dia_vencimiento   smallint NOT NULL CHECK (dia_vencimiento BETWEEN 0 AND 28), -- 0 = último día del mes
  fondo_reserva_mensual numeric(14,2) NOT NULL DEFAULT 0 CHECK (fondo_reserva_mensual >= 0),
  grupo_fondo_id    uuid,                     -- grupo con el que se reparte el fondo
  creado_en         timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (administracion_id, consorcio_id) REFERENCES consorcios (administracion_id, id),
  FOREIGN KEY (administracion_id, consorcio_id, grupo_fondo_id)
    REFERENCES grupos_prorrateo (administracion_id, consorcio_id, id),
  CHECK (fondo_reserva_mensual = 0 OR grupo_fondo_id IS NOT NULL),
  UNIQUE (consorcio_id, vigente_desde)
);

-- ── Tasas de mora con vigencia y fundamento (v10.1: tabla tasas_mora) ──────────
CREATE TABLE tasas_mora (
  id                uuid NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  administracion_id uuid NOT NULL,
  consorcio_id      uuid NOT NULL,
  vigente_desde     date NOT NULL CHECK (extract(day FROM vigente_desde) = 1),
  tasa_mensual      numeric(7,6) NOT NULL CHECK (tasa_mensual >= 0 AND tasa_mensual < 1), -- 0.05 = 5 %
  fundamento        text NOT NULL CHECK (btrim(fundamento) <> ''),  -- reglamento, acta de asamblea...
  creado_en         timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (administracion_id, consorcio_id) REFERENCES consorcios (administracion_id, id),
  UNIQUE (consorcio_id, vigente_desde)
);

-- ── Gastos del período (con la clasificación de la v10.1, CCyC 2048) ─────────
CREATE TABLE gastos (
  id                uuid NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  administracion_id uuid NOT NULL,
  consorcio_id      uuid NOT NULL,
  periodo           date NOT NULL CHECK (extract(day FROM periodo) = 1), -- mes del gasto
  grupo_id          uuid NOT NULL,
  concepto          text NOT NULL CHECK (btrim(concepto) <> ''),
  proveedor         text,
  importe           numeric(14,2) NOT NULL CHECK (importe <> 0),
  naturaleza        text NOT NULL DEFAULT 'ordinaria'  CHECK (naturaleza IN ('ordinaria', 'extraordinaria')),
  habitualidad      text NOT NULL DEFAULT 'recurrente' CHECK (habitualidad IN ('recurrente', 'no_recurrente')),
  financiacion      text NOT NULL DEFAULT 'expensas'   CHECK (financiacion IN ('expensas', 'fondo_reserva')),
  respaldo          text,                     -- acta o autorización (obligatorio para extraordinarios)
  creado_en         timestamptz NOT NULL DEFAULT now(),
  anulado_en        timestamptz,
  anulado_motivo    text,
  CHECK (naturaleza = 'ordinaria' OR btrim(coalesce(respaldo, '')) <> ''),
  CHECK ((anulado_en IS NULL) = (anulado_motivo IS NULL)),
  FOREIGN KEY (administracion_id, consorcio_id, grupo_id)
    REFERENCES grupos_prorrateo (administracion_id, consorcio_id, id)
);
CREATE INDEX gastos_periodo_idx ON gastos (consorcio_id, periodo);

-- ── Cargos particulares: a una sola unidad en un período (hoy gastos_extra) ─────
CREATE TABLE cargos_particulares (
  id                uuid NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  administracion_id uuid NOT NULL,
  consorcio_id      uuid NOT NULL,
  unidad_id         uuid NOT NULL,
  periodo           date NOT NULL CHECK (extract(day FROM periodo) = 1), -- período de la liquidación
  concepto          text NOT NULL CHECK (btrim(concepto) <> ''),
  importe           numeric(14,2) NOT NULL CHECK (importe <> 0),
  creado_en         timestamptz NOT NULL DEFAULT now(),
  anulado_en        timestamptz,
  anulado_motivo    text,
  CHECK ((anulado_en IS NULL) = (anulado_motivo IS NULL)),
  FOREIGN KEY (administracion_id, consorcio_id, unidad_id)
    REFERENCES unidades (administracion_id, consorcio_id, id)
);
CREATE INDEX cargos_particulares_periodo_idx ON cargos_particulares (consorcio_id, periodo);

-- ── Liquidaciones ─────────────────────────────────────────────────────────────
-- borrador → calculada → aprobada → emitida. Calcular se puede repetir hasta aprobar.
-- Emitida pasa los cargos a la cuenta corriente. Reabrir (solo admin, sin pagos y con la
-- siguiente sin emitir) la devuelve a calculada y anula sus partidas.
CREATE TABLE liquidaciones (
  id                uuid NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  administracion_id uuid NOT NULL,
  consorcio_id      uuid NOT NULL,
  periodo           date NOT NULL CHECK (extract(day FROM periodo) = 1),
  estado            text NOT NULL DEFAULT 'borrador'
                    CHECK (estado IN ('borrador', 'calculada', 'aprobada', 'emitida')),
  calculo_id        uuid,                     -- cálculo vigente (el último)
  vencimiento       date,                     -- se fija al emitir
  emitida_en        timestamptz,
  creado_en         timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (administracion_id, consorcio_id) REFERENCES consorcios (administracion_id, id),
  UNIQUE (consorcio_id, periodo),
  UNIQUE (administracion_id, consorcio_id, id),
  CHECK (estado = 'borrador' OR calculo_id IS NOT NULL),
  CHECK ((estado = 'emitida') = (emitida_en IS NOT NULL AND vencimiento IS NOT NULL))
);

-- Cada cálculo queda guardado (entrada y resultado): nunca se pisa, así una reapertura
-- conserva lo que se había emitido.
CREATE TABLE liquidacion_calculos (
  id                uuid NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  administracion_id uuid NOT NULL,
  consorcio_id      uuid NOT NULL,
  liquidacion_id    uuid NOT NULL,
  fecha_calculo     date NOT NULL,            -- fecha de cierre: base del interés
  tasa_mensual      numeric(7,6) NOT NULL,
  tasa_id           uuid,
  entrada           jsonb NOT NULL,
  resultado         jsonb NOT NULL,
  total_cargos      numeric(14,2) NOT NULL,
  calculado_por     uuid,
  creado_en         timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (administracion_id, consorcio_id, liquidacion_id)
    REFERENCES liquidaciones (administracion_id, consorcio_id, id),
  UNIQUE (administracion_id, id)
);
ALTER TABLE liquidaciones
  ADD FOREIGN KEY (administracion_id, calculo_id) REFERENCES liquidacion_calculos (administracion_id, id);

-- Condonación de interés por unidad en una liquidación (el switch "sin interés" de la v10).
CREATE TABLE liquidacion_condonaciones (
  administracion_id uuid NOT NULL,
  consorcio_id      uuid NOT NULL,
  liquidacion_id    uuid NOT NULL,
  unidad_id         uuid NOT NULL,
  motivo            text NOT NULL CHECK (btrim(motivo) <> ''),
  creado_por        uuid,
  creado_en         timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (liquidacion_id, unidad_id),
  FOREIGN KEY (administracion_id, consorcio_id, liquidacion_id)
    REFERENCES liquidaciones (administracion_id, consorcio_id, id),
  FOREIGN KEY (administracion_id, consorcio_id, unidad_id)
    REFERENCES unidades (administracion_id, consorcio_id, id)
);

-- ── Cuenta corriente ──────────────────────────────────────────────────────────
-- Partida: algo que una unidad debe (capital o interés). La crean la emisión de una
-- liquidación (una por línea) o la carga de la deuda inicial al migrar.
CREATE TABLE partidas (
  id                uuid NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  administracion_id uuid NOT NULL,
  consorcio_id      uuid NOT NULL,
  unidad_id         uuid NOT NULL,
  liquidacion_id    uuid,                     -- null: deuda inicial
  periodo           date NOT NULL CHECK (extract(day FROM periodo) = 1),
  tipo              text NOT NULL CHECK (tipo IN ('capital', 'interes')),
  concepto          text NOT NULL,            -- expensas, fondo_reserva, interes_deuda, deuda_inicial...
  detalle           text NOT NULL,
  importe           numeric(14,2) NOT NULL CHECK (importe > 0),
  vencimiento       date NOT NULL,
  deuda_inicial     boolean NOT NULL DEFAULT false,
  creado_en         timestamptz NOT NULL DEFAULT now(),
  anulado_en        timestamptz,
  anulado_motivo    text,
  CHECK ((anulado_en IS NULL) = (anulado_motivo IS NULL)),
  CHECK (deuda_inicial = (liquidacion_id IS NULL)),
  FOREIGN KEY (administracion_id, consorcio_id, unidad_id)
    REFERENCES unidades (administracion_id, consorcio_id, id),
  FOREIGN KEY (administracion_id, consorcio_id, liquidacion_id)
    REFERENCES liquidaciones (administracion_id, consorcio_id, id),
  UNIQUE (administracion_id, unidad_id, id)
);
CREATE INDEX partidas_unidad_idx ON partidas (unidad_id, periodo);
CREATE INDEX partidas_liquidacion_idx ON partidas (liquidacion_id);

-- Pago de una unidad. La referencia es única en el consorcio para no cargarlo dos veces.
CREATE TABLE pagos (
  id                uuid NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  administracion_id uuid NOT NULL,
  consorcio_id      uuid NOT NULL,
  unidad_id         uuid NOT NULL,
  fecha             date NOT NULL,
  importe           numeric(14,2) NOT NULL CHECK (importe > 0),
  medio             text NOT NULL DEFAULT 'transferencia'
                    CHECK (medio IN ('efectivo', 'transferencia', 'cheque', 'deposito', 'bonificacion', 'otro')),
  referencia        text NOT NULL CHECK (btrim(referencia) <> ''),
  creado_por        uuid,
  creado_en         timestamptz NOT NULL DEFAULT now(),
  anulado_en        timestamptz,
  anulado_motivo    text,
  CHECK ((anulado_en IS NULL) = (anulado_motivo IS NULL)),
  FOREIGN KEY (administracion_id, consorcio_id, unidad_id)
    REFERENCES unidades (administracion_id, consorcio_id, id),
  UNIQUE (consorcio_id, referencia),
  UNIQUE (administracion_id, unidad_id, id)
);
CREATE INDEX pagos_unidad_idx ON pagos (unidad_id, fecha);

-- Cuánto de cada pago se aplicó a cada partida (art. 903 CCyC: intereses primero, después
-- lo más viejo). origen 'pago': al registrar el pago; 'credito': el saldo a favor de pagos
-- anteriores aplicado a partidas nuevas (al emitir o al anular otro pago).
-- Lo que un pago no aplicó es saldo a favor de la unidad.
CREATE TABLE aplicaciones (
  id                uuid NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  administracion_id uuid NOT NULL,
  unidad_id         uuid NOT NULL,
  pago_id           uuid NOT NULL,
  partida_id        uuid NOT NULL,
  importe           numeric(14,2) NOT NULL CHECK (importe > 0),
  origen            text NOT NULL CHECK (origen IN ('pago', 'credito')),
  creado_en         timestamptz NOT NULL DEFAULT now(),
  anulado_en        timestamptz,
  anulado_motivo    text,
  CHECK ((anulado_en IS NULL) = (anulado_motivo IS NULL)),
  -- El pago y la partida tienen que ser de la misma unidad.
  FOREIGN KEY (administracion_id, unidad_id, pago_id)    REFERENCES pagos (administracion_id, unidad_id, id),
  FOREIGN KEY (administracion_id, unidad_id, partida_id) REFERENCES partidas (administracion_id, unidad_id, id)
);
CREATE INDEX aplicaciones_partida_idx ON aplicaciones (partida_id) WHERE anulado_en IS NULL;
CREATE INDEX aplicaciones_pago_idx ON aplicaciones (pago_id) WHERE anulado_en IS NULL;

-- ── RLS ───────────────────────────────────────────────────────────────────────
-- +goose StatementBegin
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['parametros_consorcio', 'tasas_mora', 'gastos', 'cargos_particulares',
                           'liquidaciones', 'liquidacion_calculos', 'liquidacion_condonaciones',
                           'partidas', 'pagos', 'aplicaciones'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format('CREATE POLICY %I ON %I USING (administracion_id = app_administracion_id()) '
                   'WITH CHECK (administracion_id = app_administracion_id())', t || '_tenant', t);
  END LOOP;
END $$;
-- +goose StatementEnd

-- Sin DELETE: todo se anula. Los cálculos guardados no se modifican.
GRANT SELECT, INSERT, UPDATE ON parametros_consorcio, tasas_mora, gastos, cargos_particulares,
                                liquidaciones, partidas, pagos, aplicaciones TO consorcios_app;
GRANT SELECT, INSERT          ON liquidacion_calculos TO consorcios_app;
-- Las condonaciones se pueden quitar mientras la liquidación no se aprobó (queda en la auditoría).
GRANT SELECT, INSERT, DELETE  ON liquidacion_condonaciones TO consorcios_app;

-- +goose Down
DROP TABLE aplicaciones;
DROP TABLE pagos;
DROP TABLE partidas;
DROP TABLE liquidacion_condonaciones;
ALTER TABLE liquidaciones DROP COLUMN calculo_id;
DROP TABLE liquidacion_calculos;
DROP TABLE liquidaciones;
DROP TABLE cargos_particulares;
DROP TABLE gastos;
DROP TABLE tasas_mora;
DROP TABLE parametros_consorcio;
