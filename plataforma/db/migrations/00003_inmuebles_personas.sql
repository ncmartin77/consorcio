-- Etapa 2: unidades, personas con vínculos históricos, grupos de prorrateo y
-- coeficientes con vigencia. Todas son tablas de tenant: administracion_id + RLS, y
-- claves foráneas compuestas para que nada se cuelgue de otra administración.

-- +goose Up

-- Para las restricciones de "no superposición" de fechas (EXCLUDE con uuid y rangos).
CREATE EXTENSION IF NOT EXISTS btree_gist;

-- ── Unidades funcionales ──────────────────────────────────────────────────────
CREATE TABLE unidades (
  id                uuid NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  administracion_id uuid NOT NULL,
  consorcio_id      uuid NOT NULL,
  codigo            text NOT NULL,            -- como figura en la liquidación: "1", "2B", "Cochera 3"
  descripcion       text,
  piso              text,
  tipo              text NOT NULL DEFAULT 'departamento'
                    CHECK (tipo IN ('departamento', 'cochera', 'local', 'baulera', 'otro')),
  activa            boolean NOT NULL DEFAULT true,
  creado_en         timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (administracion_id, consorcio_id) REFERENCES consorcios (administracion_id, id),
  UNIQUE (consorcio_id, codigo),
  UNIQUE (administracion_id, consorcio_id, id)
);

-- ── Personas (propietarios, inquilinos, contactos) ────────────────────────────
-- Separadas de los usuarios: un propietario no necesita iniciar sesión.
-- Son de la administración: una persona puede tener unidades en varios consorcios.
CREATE TABLE personas (
  id                uuid NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  administracion_id uuid NOT NULL REFERENCES administraciones (id),
  nombre            text NOT NULL,
  documento         text,                     -- DNI/CUIT, sin formato fijo por ahora
  email             text,
  telefono          text,
  notas             text,
  creado_en         timestamptz NOT NULL DEFAULT now(),
  UNIQUE (administracion_id, id)
);
CREATE INDEX personas_nombre_idx ON personas (administracion_id, lower(nombre));

-- Vínculos persona ↔ unidad con historia: nunca se borran, se cierran con "hasta".
-- Rango [desde, hasta): "hasta" es el primer día en que ya no rige.
CREATE TABLE unidad_personas (
  id                uuid NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  administracion_id uuid NOT NULL,
  unidad_id         uuid NOT NULL,
  persona_id        uuid NOT NULL,
  tipo_vinculo      text NOT NULL CHECK (tipo_vinculo IN ('propietario', 'inquilino', 'contacto')),
  porcentaje_titularidad numeric(7,4) CHECK (porcentaje_titularidad > 0 AND porcentaje_titularidad <= 100),
  recibe_liquidacion boolean NOT NULL DEFAULT false,
  desde             date NOT NULL,
  hasta             date,
  creado_en         timestamptz NOT NULL DEFAULT now(),
  CHECK (hasta IS NULL OR hasta > desde),
  CHECK (porcentaje_titularidad IS NULL OR tipo_vinculo = 'propietario'),
  FOREIGN KEY (administracion_id, persona_id) REFERENCES personas (administracion_id, id),
  -- La misma persona no puede tener dos vínculos del mismo tipo superpuestos en la unidad.
  EXCLUDE USING gist (unidad_id WITH =, persona_id WITH =, tipo_vinculo WITH =,
                      daterange(desde, hasta, '[)') WITH &&)
);
-- FK compuesta a unidades sin consorcio_id: se valida con un índice único extra.
CREATE UNIQUE INDEX unidades_adm_id_uk ON unidades (administracion_id, id);
ALTER TABLE unidad_personas
  ADD FOREIGN KEY (administracion_id, unidad_id) REFERENCES unidades (administracion_id, id);
CREATE INDEX unidad_personas_unidad_idx ON unidad_personas (unidad_id, desde);
CREATE INDEX unidad_personas_persona_idx ON unidad_personas (persona_id);

-- ── Prorrateo ────────────────────────────────────────────────────────────────
-- Un consorcio tiene uno o más grupos (GENERAL, Ascensor, Cocheras...). Cada gasto
-- se reparte según los coeficientes vigentes de su grupo.
CREATE TABLE grupos_prorrateo (
  id                uuid NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  administracion_id uuid NOT NULL,
  consorcio_id      uuid NOT NULL,
  nombre            text NOT NULL,
  descripcion       text,
  creado_en         timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (administracion_id, consorcio_id) REFERENCES consorcios (administracion_id, id),
  UNIQUE (consorcio_id, nombre),
  UNIQUE (administracion_id, consorcio_id, id)
);

-- Coeficiente (porcentaje) de cada unidad en un grupo, con vigencia [vigente_desde, vigente_hasta).
-- El grupo y la unidad tienen que ser del mismo consorcio (FKs compuestas).
CREATE TABLE unidad_coeficientes (
  id                uuid NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  administracion_id uuid NOT NULL,
  consorcio_id      uuid NOT NULL,
  grupo_id          uuid NOT NULL,
  unidad_id         uuid NOT NULL,
  porcentaje        numeric(9,6) NOT NULL CHECK (porcentaje >= 0 AND porcentaje <= 100),
  vigente_desde     date NOT NULL,
  vigente_hasta     date,
  creado_en         timestamptz NOT NULL DEFAULT now(),
  CHECK (vigente_hasta IS NULL OR vigente_hasta > vigente_desde),
  FOREIGN KEY (administracion_id, consorcio_id, grupo_id)  REFERENCES grupos_prorrateo (administracion_id, consorcio_id, id),
  FOREIGN KEY (administracion_id, consorcio_id, unidad_id) REFERENCES unidades (administracion_id, consorcio_id, id),
  EXCLUDE USING gist (grupo_id WITH =, unidad_id WITH =,
                      daterange(vigente_desde, vigente_hasta, '[)') WITH &&)
);
CREATE INDEX unidad_coeficientes_grupo_idx ON unidad_coeficientes (grupo_id, vigente_desde);

-- ── RLS: cada tabla solo muestra y acepta filas de la administración del contexto ──
ALTER TABLE unidades            ENABLE ROW LEVEL SECURITY;
ALTER TABLE unidades            FORCE  ROW LEVEL SECURITY;
ALTER TABLE personas            ENABLE ROW LEVEL SECURITY;
ALTER TABLE personas            FORCE  ROW LEVEL SECURITY;
ALTER TABLE unidad_personas     ENABLE ROW LEVEL SECURITY;
ALTER TABLE unidad_personas     FORCE  ROW LEVEL SECURITY;
ALTER TABLE grupos_prorrateo    ENABLE ROW LEVEL SECURITY;
ALTER TABLE grupos_prorrateo    FORCE  ROW LEVEL SECURITY;
ALTER TABLE unidad_coeficientes ENABLE ROW LEVEL SECURITY;
ALTER TABLE unidad_coeficientes FORCE  ROW LEVEL SECURITY;

CREATE POLICY unidades_tenant ON unidades
  USING (administracion_id = app_administracion_id()) WITH CHECK (administracion_id = app_administracion_id());
CREATE POLICY personas_tenant ON personas
  USING (administracion_id = app_administracion_id()) WITH CHECK (administracion_id = app_administracion_id());
CREATE POLICY unidad_personas_tenant ON unidad_personas
  USING (administracion_id = app_administracion_id()) WITH CHECK (administracion_id = app_administracion_id());
CREATE POLICY grupos_prorrateo_tenant ON grupos_prorrateo
  USING (administracion_id = app_administracion_id()) WITH CHECK (administracion_id = app_administracion_id());
CREATE POLICY unidad_coeficientes_tenant ON unidad_coeficientes
  USING (administracion_id = app_administracion_id()) WITH CHECK (administracion_id = app_administracion_id());

-- Sin DELETE en vínculos ni coeficientes: la historia se cierra con fechas, no se borra.
GRANT SELECT, INSERT, UPDATE         ON unidades, personas, grupos_prorrateo TO consorcios_app;
GRANT SELECT, INSERT, UPDATE         ON unidad_personas, unidad_coeficientes TO consorcios_app;

-- +goose Down
DROP TABLE unidad_coeficientes;
DROP TABLE grupos_prorrateo;
DROP TABLE unidad_personas;
DROP TABLE personas;
DROP TABLE unidades;
