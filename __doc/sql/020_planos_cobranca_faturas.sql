-- DropNexo — planos, cobrança tenant e faturas (Efi)

CREATE TABLE IF NOT EXISTS tbl_plano (
    id SERIAL PRIMARY KEY,
    slug VARCHAR(32) NOT NULL UNIQUE,
    nome VARCHAR(80) NOT NULL,
    valor_centavos INTEGER NOT NULL DEFAULT 0,
    periodicidade VARCHAR(20) NOT NULL DEFAULT 'mensal'
        CHECK (periodicidade IN ('mensal', 'anual')),
    efi_plano_id VARCHAR(64),
    descricao TEXT,
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    ordem INTEGER NOT NULL DEFAULT 0
);

INSERT INTO tbl_plano (slug, nome, valor_centavos, periodicidade, descricao, ordem, ativo)
VALUES
    ('starter', 'Starter', 0, 'mensal', 'Comece grátis', 10, TRUE),
    ('professional', 'Profissional', 14900, 'mensal', 'Operação em escala', 20, TRUE),
    ('enterprise', 'Enterprise', 49900, 'mensal', 'Recursos avançados', 30, TRUE)
ON CONFLICT (slug) DO UPDATE SET
    nome = EXCLUDED.nome,
    valor_centavos = EXCLUDED.valor_centavos,
    descricao = EXCLUDED.descricao;

CREATE TABLE IF NOT EXISTS tbl_tenant_cobranca (
    id SERIAL PRIMARY KEY,
    id_tenant INTEGER NOT NULL UNIQUE REFERENCES tbl_tenant(id) ON DELETE CASCADE,
    plano_slug VARCHAR(32) NOT NULL DEFAULT 'starter' REFERENCES tbl_plano(slug),
    forma_pagamento VARCHAR(20) NOT NULL DEFAULT 'boleto'
        CHECK (forma_pagamento IN ('boleto', 'pix', 'cartao')),
    dia_vencimento SMALLINT NOT NULL DEFAULT 15
        CHECK (dia_vencimento BETWEEN 1 AND 28),
    email_cobranca VARCHAR(255),
    efi_customer_id VARCHAR(64),
    inicio_cobranca DATE,
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS tbl_fatura (
    id SERIAL PRIMARY KEY,
    id_tenant INTEGER NOT NULL REFERENCES tbl_tenant(id) ON DELETE CASCADE,
    referencia VARCHAR(7) NOT NULL,
    valor_centavos INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pendente'
        CHECK (status IN ('pendente', 'pago', 'vencido', 'cancelado')),
    efi_charge_id VARCHAR(64),
    link_boleto TEXT,
    codigo_barras TEXT,
    vencimento_em DATE,
    pago_em TIMESTAMPTZ,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (id_tenant, referencia)
);

CREATE INDEX IF NOT EXISTS ix_fatura_tenant ON tbl_fatura(id_tenant);
CREATE INDEX IF NOT EXISTS ix_fatura_status ON tbl_fatura(status);
