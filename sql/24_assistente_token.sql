-- 24_assistente_token.sql
-- Token e auditoria da API do Assistente (dn_assist_…).

CREATE TABLE IF NOT EXISTS tbl_assistente_token (
  id              SERIAL PRIMARY KEY,
  token_hash      TEXT NOT NULL UNIQUE,
  token_hint      TEXT NOT NULL,
  nome            TEXT NOT NULL DEFAULT 'Assistente',
  ativo           BOOLEAN NOT NULL DEFAULT TRUE,
  criado_em       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  criado_por      INTEGER NULL,
  revogado_em     TIMESTAMPTZ NULL,
  revogado_por    INTEGER NULL
);

CREATE TABLE IF NOT EXISTS tbl_assistente_auditoria (
  id              BIGSERIAL PRIMARY KEY,
  criado_em       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  rota            TEXT NOT NULL,
  metodo          TEXT NOT NULL DEFAULT 'GET',
  ip              TEXT NULL,
  token_hint      TEXT NULL,
  http_status     INTEGER NULL,
  id_tenant_alvo  INTEGER NULL
);

CREATE INDEX IF NOT EXISTS idx_assistente_auditoria_em
  ON tbl_assistente_auditoria (criado_em DESC);

CREATE INDEX IF NOT EXISTS idx_assistente_token_ativo
  ON tbl_assistente_token (ativo)
  WHERE ativo = TRUE;

COMMENT ON TABLE tbl_assistente_token IS
  'Tokens dn_assist_… (só hash). Gerados por DEV/H74 na manutenção.';
COMMENT ON TABLE tbl_assistente_auditoria IS
  'Auditoria de chamadas da API /api/v1/assistente/*.';
