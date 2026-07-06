-- Integração Mercado Pago (fornecedor recebe pagamentos de pedidos)

CREATE TABLE IF NOT EXISTS tbl_integracao_mercadopago (
    id_tenant INTEGER PRIMARY KEY REFERENCES tbl_tenant(id) ON DELETE CASCADE,
    status VARCHAR(20) NOT NULL DEFAULT 'desconectado'
        CHECK (status IN ('desconectado', 'conectado', 'erro')),
    access_token_enc TEXT,
    refresh_token_enc TEXT,
    token_expires_em TIMESTAMPTZ,
    mp_user_id BIGINT,
    mp_conta_info JSONB NOT NULL DEFAULT '{}',
    aceita_pix BOOLEAN NOT NULL DEFAULT TRUE,
    aceita_cartao BOOLEAN NOT NULL DEFAULT TRUE,
    conectado_em TIMESTAMPTZ,
    ultimo_erro TEXT,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE tbl_integracao_mercadopago IS
    'OAuth Mercado Pago por fornecedor — recebimento de pedidos B2B (PIX e cartão).';
COMMENT ON COLUMN tbl_integracao_mercadopago.aceita_pix IS
    'Vendedor pode escolher PIX no checkout do pedido.';
COMMENT ON COLUMN tbl_integracao_mercadopago.aceita_cartao IS
    'Vendedor pode escolher cartão no checkout do pedido.';
