-- Integração Melhor Envio (fornecedor — cotação, etiquetas e rastreio)

CREATE TABLE IF NOT EXISTS tbl_integracao_melhor_envio (
    id_tenant INTEGER PRIMARY KEY REFERENCES tbl_tenant(id) ON DELETE CASCADE,
    status VARCHAR(20) NOT NULL DEFAULT 'desconectado'
        CHECK (status IN ('desconectado', 'conectado', 'erro')),
    access_token_enc TEXT,
    refresh_token_enc TEXT,
    token_expires_em TIMESTAMPTZ,
    me_user_id BIGINT,
    me_conta_info JSONB NOT NULL DEFAULT '{}',
    conectado_em TIMESTAMPTZ,
    ultimo_erro TEXT,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE tbl_integracao_melhor_envio IS
    'OAuth Melhor Envio por fornecedor — frete B2B (cotação, etiqueta, rastreio).';

ALTER TABLE tbl_pedido ADD COLUMN IF NOT EXISTS me_order_id VARCHAR(64);
ALTER TABLE tbl_pedido ADD COLUMN IF NOT EXISTS me_protocol VARCHAR(80);

COMMENT ON COLUMN tbl_pedido.me_order_id IS 'ID da etiqueta/pedido no Melhor Envio (webhook).';
COMMENT ON COLUMN tbl_pedido.me_protocol IS 'Protocolo ORD-... do Melhor Envio.';

CREATE INDEX IF NOT EXISTS idx_pedido_me_order_id
    ON tbl_pedido(me_order_id)
    WHERE me_order_id IS NOT NULL AND me_order_id <> '';
