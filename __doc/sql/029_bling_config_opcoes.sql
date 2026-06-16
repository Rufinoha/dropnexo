-- Opções extras da integração Bling (estoque automático, polling, etc.)
ALTER TABLE tbl_integracao_bling_config
    ADD COLUMN IF NOT EXISTS opcoes JSONB NOT NULL DEFAULT '{}';
