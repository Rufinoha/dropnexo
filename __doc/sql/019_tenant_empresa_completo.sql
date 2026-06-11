-- DropNexo — campos completos de empresa (aba Minha empresa) + inscrições ST

ALTER TABLE tbl_tenant ADD COLUMN IF NOT EXISTS ie_isento BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE tbl_tenant ADD COLUMN IF NOT EXISTS atividade_principal VARCHAR(120);
ALTER TABLE tbl_tenant ADD COLUMN IF NOT EXISTS codigo_regime_tributario VARCHAR(40);
ALTER TABLE tbl_tenant ADD COLUMN IF NOT EXISTS tamanho_empresa VARCHAR(40);
ALTER TABLE tbl_tenant ADD COLUMN IF NOT EXISTS segmento_comercio BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE tbl_tenant ADD COLUMN IF NOT EXISTS segmento_ecommerce BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE tbl_tenant ADD COLUMN IF NOT EXISTS segmento_industria BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE tbl_tenant ADD COLUMN IF NOT EXISTS segmento_servicos BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE tbl_tenant ADD COLUMN IF NOT EXISTS faturamento_ultimo_ano VARCHAR(40);
ALTER TABLE tbl_tenant ADD COLUMN IF NOT EXISTS quantidade_funcionarios VARCHAR(40);
ALTER TABLE tbl_tenant ADD COLUMN IF NOT EXISTS pessoas_contato VARCHAR(255);
ALTER TABLE tbl_tenant ADD COLUMN IF NOT EXISTS celular_comercial VARCHAR(20);
ALTER TABLE tbl_tenant ADD COLUMN IF NOT EXISTS site VARCHAR(255);
ALTER TABLE tbl_tenant ADD COLUMN IF NOT EXISTS logo_caminho TEXT;

CREATE TABLE IF NOT EXISTS tbl_tenant_inscricao_st (
    id SERIAL PRIMARY KEY,
    id_tenant INTEGER NOT NULL REFERENCES tbl_tenant(id) ON DELETE CASCADE,
    uf CHAR(2) NOT NULL,
    inscricao_estadual VARCHAR(20) NOT NULL,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_tenant_inscricao_st_tenant ON tbl_tenant_inscricao_st(id_tenant);

CREATE TABLE IF NOT EXISTS tbl_cancelamento_conta (
    id SERIAL PRIMARY KEY,
    id_tenant INTEGER NOT NULL REFERENCES tbl_tenant(id) ON DELETE CASCADE,
    id_usuario INTEGER NOT NULL REFERENCES tbl_usuario(id) ON DELETE CASCADE,
    etapa SMALLINT NOT NULL DEFAULT 1,
    motivo TEXT,
    solicitado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    concluido_em TIMESTAMPTZ,
    UNIQUE (id_tenant)
);
