-- Resultado JSON de jobs longos (ex.: painel de categorias Bling)
ALTER TABLE tbl_integracao_bling_sync_job
    ADD COLUMN IF NOT EXISTS payload JSONB;
