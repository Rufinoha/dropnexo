-- 064_fornecedor_fase_contato.sql
-- Espelho de sql/23_fornecedor_fase_contato.sql (série __doc/sql).

ALTER TABLE tbl_tenant
  ADD COLUMN IF NOT EXISTS fornecedor_fase TEXT,
  ADD COLUMN IF NOT EXISTS fornecedor_fase_em TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS fornecedor_triagem JSONB;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'chk_tenant_fornecedor_fase'
  ) THEN
    ALTER TABLE tbl_tenant
      ADD CONSTRAINT chk_tenant_fornecedor_fase
      CHECK (
        fornecedor_fase IS NULL
        OR fornecedor_fase IN (
          'cadastrado',
          'boas_vindas',
          'cadastrando',
          'lembrete',
          'ativo',
          'eh_vendedor',
          'sem_resposta',
          'desistiu'
        )
      );
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS tbl_fornecedor_contato (
  id            BIGSERIAL PRIMARY KEY,
  id_tenant     INTEGER NOT NULL REFERENCES tbl_tenant(id) ON DELETE CASCADE,
  criado_em     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  canal         TEXT NOT NULL,
  direcao       TEXT NOT NULL,
  resumo        TEXT NOT NULL,
  fase_apos     TEXT NULL,
  autor         TEXT NOT NULL DEFAULT '',
  CONSTRAINT chk_fornecedor_contato_canal
    CHECK (canal IN ('whatsapp', 'email', 'telefone', 'outro')),
  CONSTRAINT chk_fornecedor_contato_direcao
    CHECK (direcao IN ('enviado', 'recebido')),
  CONSTRAINT chk_fornecedor_contato_resumo
    CHECK (char_length(resumo) <= 500),
  CONSTRAINT chk_fornecedor_contato_fase_apos
    CHECK (
      fase_apos IS NULL
      OR fase_apos IN (
        'cadastrado',
        'boas_vindas',
        'cadastrando',
        'lembrete',
        'ativo',
        'eh_vendedor',
        'sem_resposta',
        'desistiu'
      )
    )
);

CREATE INDEX IF NOT EXISTS idx_fornecedor_contato_tenant_em
  ON tbl_fornecedor_contato (id_tenant, criado_em DESC);

COMMENT ON COLUMN tbl_tenant.fornecedor_fase IS
  'Fase de acompanhamento do fornecedor (cadastro → ativo / desistiu etc.).';
COMMENT ON COLUMN tbl_tenant.fornecedor_fase_em IS
  'Quando a fase atual foi definida.';
COMMENT ON COLUMN tbl_tenant.fornecedor_triagem IS
  'Respostas da triagem pré-cadastro de fornecedor (JSONB).';
COMMENT ON TABLE tbl_fornecedor_contato IS
  'Histórico curto de contatos com o fornecedor (prova de acompanhamento).';
