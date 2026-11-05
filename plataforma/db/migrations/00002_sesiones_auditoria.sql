-- Etapa 1: sesiones HTTP y auditoría.

-- +goose Up

-- Sesiones de la API. Solo se guarda el SHA-256 del token: con una copia de la base
-- no se pueden usar las cookies. Vencen a las 12 h o tras 2 h sin uso (lo controla la API).
CREATE TABLE sesiones (
  token_hash  bytea PRIMARY KEY,
  usuario_id  uuid NOT NULL REFERENCES usuarios (id) ON DELETE CASCADE,
  creada_en   timestamptz NOT NULL DEFAULT now(),
  vence_en    timestamptz NOT NULL,
  ultimo_uso  timestamptz NOT NULL DEFAULT now(),
  ip          text,
  user_agent  text
);
CREATE INDEX sesiones_usuario_idx ON sesiones (usuario_id);

-- Auditoría de solo agregado: la aplicación puede insertar pero no leer, cambiar ni borrar.
CREATE TABLE auditoria (
  id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  creado_en         timestamptz NOT NULL DEFAULT now(),
  administracion_id uuid REFERENCES administraciones (id) ON DELETE SET NULL,
  usuario_id        uuid REFERENCES usuarios (id) ON DELETE SET NULL,
  accion            text NOT NULL,
  detalle           jsonb NOT NULL DEFAULT '{}',
  ip                text
);
CREATE INDEX auditoria_administracion_idx ON auditoria (administracion_id, creado_en);
CREATE INDEX auditoria_usuario_idx ON auditoria (usuario_id, creado_en);

GRANT SELECT, INSERT, UPDATE, DELETE ON sesiones TO consorcios_app;
GRANT INSERT ON auditoria TO consorcios_app;

-- +goose Down
DROP TABLE auditoria;
DROP TABLE sesiones;
