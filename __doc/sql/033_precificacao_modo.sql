-- Modo de precificação do fornecedor: global (todos) ou por categoria (mutuamente exclusivo na UI)
ALTER TABLE tbl_tenant ADD COLUMN IF NOT EXISTS precificacao_modo VARCHAR(20) NOT NULL DEFAULT 'global';

UPDATE tbl_tenant SET precificacao_modo = 'global' WHERE precificacao_modo IS NULL OR precificacao_modo = '';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ck_tenant_precificacao_modo'
    ) THEN
        ALTER TABLE tbl_tenant
            ADD CONSTRAINT ck_tenant_precificacao_modo
            CHECK (precificacao_modo IN ('global', 'categoria'));
    END IF;
END $$;
