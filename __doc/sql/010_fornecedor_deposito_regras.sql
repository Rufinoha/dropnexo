-- DropNexo — Fornecedor PJ, depósitos de expedição, regras comerciais, produto × depósito

-- Dados cadastrais PJ (endereço fiscal opcional; expedição nos depósitos)
ALTER TABLE tbl_tenant ADD COLUMN IF NOT EXISTS razao_social VARCHAR(255);
ALTER TABLE tbl_tenant ADD COLUMN IF NOT EXISTS nome_fantasia VARCHAR(255);
ALTER TABLE tbl_tenant ADD COLUMN IF NOT EXISTS inscricao_estadual VARCHAR(20);
ALTER TABLE tbl_tenant ADD COLUMN IF NOT EXISTS inscricao_municipal VARCHAR(20);
ALTER TABLE tbl_tenant ADD COLUMN IF NOT EXISTS situacao_cadastral VARCHAR(40);
ALTER TABLE tbl_tenant ADD COLUMN IF NOT EXISTS cnae_principal VARCHAR(20);
ALTER TABLE tbl_tenant ADD COLUMN IF NOT EXISTS telefone_comercial VARCHAR(20);
ALTER TABLE tbl_tenant ADD COLUMN IF NOT EXISTS email_comercial VARCHAR(255);

ALTER TABLE tbl_tenant ALTER COLUMN cep DROP NOT NULL;
ALTER TABLE tbl_tenant ALTER COLUMN logradouro DROP NOT NULL;
ALTER TABLE tbl_tenant ALTER COLUMN numero DROP NOT NULL;
ALTER TABLE tbl_tenant ALTER COLUMN bairro DROP NOT NULL;
ALTER TABLE tbl_tenant ALTER COLUMN cidade DROP NOT NULL;
ALTER TABLE tbl_tenant ALTER COLUMN uf DROP NOT NULL;

-- Depósitos de expedição (remetente / origem do frete)
CREATE TABLE IF NOT EXISTS tbl_deposito_expedicao (
    id SERIAL PRIMARY KEY,
    id_tenant INTEGER NOT NULL REFERENCES tbl_tenant(id) ON DELETE CASCADE,
    nome VARCHAR(120) NOT NULL DEFAULT 'Depósito',
    cep VARCHAR(8) NOT NULL,
    logradouro VARCHAR(255) NOT NULL,
    numero VARCHAR(20) NOT NULL DEFAULT 'S/N',
    complemento VARCHAR(120),
    bairro VARCHAR(120) NOT NULL,
    cidade VARCHAR(120) NOT NULL,
    uf CHAR(2) NOT NULL,
    remetente_nome VARCHAR(255),
    remetente_documento VARCHAR(14),
    principal BOOLEAN NOT NULL DEFAULT FALSE,
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (id_tenant, cep)
);

CREATE INDEX IF NOT EXISTS ix_deposito_tenant ON tbl_deposito_expedicao(id_tenant);

-- Regras comerciais do fornecedor (dropshipping / marketplace)
CREATE TABLE IF NOT EXISTS tbl_fornecedor_regra (
    id SERIAL PRIMARY KEY,
    id_tenant INTEGER NOT NULL REFERENCES tbl_tenant(id) ON DELETE CASCADE,
    codigo VARCHAR(40) NOT NULL,
    titulo VARCHAR(120) NOT NULL,
    descricao TEXT,
    valor_inteiro INTEGER,
    valor_booleano BOOLEAN,
    valor_texto TEXT,
    ordem INTEGER NOT NULL DEFAULT 0,
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (id_tenant, codigo)
);

-- Produto: depósito de expedição + campos alinhados ao XML Drop
ALTER TABLE tbl_produto ADD COLUMN IF NOT EXISTS id_deposito_expedicao INTEGER
    REFERENCES tbl_deposito_expedicao(id) ON DELETE SET NULL;
ALTER TABLE tbl_produto ADD COLUMN IF NOT EXISTS marca VARCHAR(120);
ALTER TABLE tbl_produto ADD COLUMN IF NOT EXISTS grupo VARCHAR(64);
ALTER TABLE tbl_produto ADD COLUMN IF NOT EXISTS valor_atacado NUMERIC(12, 2);
ALTER TABLE tbl_produto ADD COLUMN IF NOT EXISTS valor_dropshipping NUMERIC(12, 2);
ALTER TABLE tbl_produto ADD COLUMN IF NOT EXISTS reposicao_estoque BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE tbl_produto ADD COLUMN IF NOT EXISTS dimensao_caixa_cm VARCHAR(40);
ALTER TABLE tbl_produto ADD COLUMN IF NOT EXISTS peso_gramas INTEGER;

CREATE INDEX IF NOT EXISTS ix_produto_deposito ON tbl_produto(id_deposito_expedicao);
