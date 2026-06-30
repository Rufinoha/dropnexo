-- Progresso da sync inicial de estoque (sobrevive a múltiplos workers Gunicorn)
CREATE TABLE IF NOT EXISTS tbl_integracao_bling_sync_job (
    job_id UUID PRIMARY KEY,
    id_tenant INTEGER NOT NULL REFERENCES tbl_tenant(id) ON DELETE CASCADE,
    id_bling_deposito VARCHAR(64),
    status VARCHAR(20) NOT NULL DEFAULT 'processando'
        CHECK (status IN ('processando', 'concluido', 'erro')),
    total INTEGER NOT NULL DEFAULT 0,
    processados INTEGER NOT NULL DEFAULT 0,
    sincronizados INTEGER NOT NULL DEFAULT 0,
    falhas INTEGER NOT NULL DEFAULT 0,
    mensagem TEXT,
    resumo TEXT,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_bling_sync_job_tenant
    ON tbl_integracao_bling_sync_job(id_tenant, criado_em DESC);
