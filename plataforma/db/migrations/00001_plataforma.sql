-- Etapa 1: plataforma multi-tenant (usuarios, administraciones, membresías) y
-- la primera tabla de tenant (consorcios) con Row-Level Security.
--
-- Roles (los crea deploy/initdb/01-roles.sh):
--   consorcios_owner  dueño del esquema; corre las migraciones.
--   consorcios_app    usa la API y el worker; sin BYPASSRLS ni propiedad de tablas.

-- +goose Up

-- Contexto del tenant: lo fija database.EnTenant con set_config(..., true).
CREATE FUNCTION app_administracion_id() RETURNS uuid
LANGUAGE sql STABLE AS $$
  SELECT nullif(current_setting('app.administracion_id', true), '')::uuid
$$;

-- ── Plataforma (sin RLS: se consultan antes de elegir administración) ────────

CREATE TABLE usuarios (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email         text NOT NULL,
  nombre        text NOT NULL,
  password_hash text,                 -- Argon2id; null si entra solo con proveedor externo
  activo        boolean NOT NULL DEFAULT true,
  creado_en     timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX usuarios_email_uk ON usuarios (lower(email));

CREATE TABLE administraciones (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  nombre     text NOT NULL,
  cuit       text,
  activa     boolean NOT NULL DEFAULT true,
  creado_en  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE membresias (
  usuario_id        uuid NOT NULL REFERENCES usuarios (id),
  administracion_id uuid NOT NULL REFERENCES administraciones (id),
  rol               text NOT NULL CHECK (rol IN ('admin', 'operador', 'consulta')),
  creado_en         timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (usuario_id, administracion_id)
);

-- ── Tenant (con RLS) ──────────────────────────────────────────────────────────

CREATE TABLE consorcios (
  id                uuid NOT NULL DEFAULT gen_random_uuid(),
  administracion_id uuid NOT NULL REFERENCES administraciones (id),
  nombre            text NOT NULL,
  direccion         text,
  cuit              text,
  creado_en         timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (id),
  -- Destino de las FK compuestas (administracion_id, consorcio_id) de las tablas hijas:
  -- impide colgar una unidad de un consorcio de otra administración.
  UNIQUE (administracion_id, id)
);

ALTER TABLE consorcios ENABLE ROW LEVEL SECURITY;
ALTER TABLE consorcios FORCE ROW LEVEL SECURITY;
CREATE POLICY consorcios_tenant ON consorcios
  USING (administracion_id = app_administracion_id())
  WITH CHECK (administracion_id = app_administracion_id());

-- ── Permisos del rol de la aplicación ────────────────────────────────────────

GRANT USAGE ON SCHEMA public TO consorcios_app;
GRANT SELECT, INSERT, UPDATE ON usuarios, administraciones, membresias TO consorcios_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON consorcios TO consorcios_app;
GRANT EXECUTE ON FUNCTION app_administracion_id() TO consorcios_app;

-- +goose Down
DROP TABLE consorcios;
DROP TABLE membresias;
DROP TABLE administraciones;
DROP TABLE usuarios;
DROP FUNCTION app_administracion_id();
