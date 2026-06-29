-- DropNexo — Bling: company_id, sync estoque bidirecional, anti-eco, fila webhook

ALTER TABLE tbl_integracao_bling
    ADD COLUMN IF NOT EXISTS bling_company_id VARCHAR(64);

CREATE INDEX IF NOT EXISTS ix_integracao_bling_company
    ON tbl_integracao_bling (bling_company_id)
    WHERE bling_company_id IS NOT NULL AND status = 'conectado';

ALTER TABLE tbl_integracao_bling_config
    ADD COLUMN IF NOT EXISTS ultima_sync_estoque_recebido TIMESTAMPTZ;

ALTER TABLE tbl_integracao_bling_config
    ADD COLUMN IF NOT EXISTS ultima_sync_estoque_enviado TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS tbl_integracao_bling_eco_estoque (
    id SERIAL PRIMARY KEY,
    id_tenant INTEGER NOT NULL REFERENCES tbl_tenant(id) ON DELETE CASCADE,
    id_bling_produto VARCHAR(64) NOT NULL,
    id_bling_deposito VARCHAR(64) NOT NULL,
    quantidade_esperada INTEGER,
    origem VARCHAR(30) NOT NULL,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expira_em TIMESTAMPTZ NOT NULL,
    consumido_em TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_bling_eco_estoque_lookup
    ON tbl_integracao_bling_eco_estoque (
        id_tenant, id_bling_produto, id_bling_deposito, expira_em
    )
    WHERE consumido_em IS NULL;

CREATE TABLE IF NOT EXISTS tbl_integracao_bling_webhook_fila (
    id SERIAL PRIMARY KEY,
    id_tenant INTEGER REFERENCES tbl_tenant(id) ON DELETE CASCADE,
    company_id VARCHAR(64),
    recurso VARCHAR(30),
    acao VARCHAR(20),
    payload JSONB NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pendente'
        CHECK (status IN ('pendente', 'processando', 'ok', 'ignorado', 'erro')),
    erro TEXT,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processado_em TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_bling_webhook_fila_pendente
    ON tbl_integracao_bling_webhook_fila (status, criado_em)
    WHERE status = 'pendente';
