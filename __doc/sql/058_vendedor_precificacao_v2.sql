-- Precificação vendedor V1: modo sugestão fornecedor vs margem sobre valor Drop
ALTER TABLE tbl_vendedor_precificacao
    ADD COLUMN IF NOT EXISTS modo VARCHAR(30) NOT NULL DEFAULT 'sugestao_fornecedor',
    ADD COLUMN IF NOT EXISTS arredondamento_centavos SMALLINT NULL,
    ADD COLUMN IF NOT EXISTS margem_minima_alerta NUMERIC(8, 4) NOT NULL DEFAULT 30;

UPDATE tbl_vendedor_precificacao
SET modo = 'sugestao_fornecedor'
WHERE modo IS NULL OR modo = '';

UPDATE tbl_vendedor_precificacao
SET margem_minima_alerta = 30
WHERE margem_minima_alerta IS NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ck_vendedor_precificacao_modo'
    ) THEN
        ALTER TABLE tbl_vendedor_precificacao
            ADD CONSTRAINT ck_vendedor_precificacao_modo
            CHECK (modo IN ('sugestao_fornecedor', 'margem_drop'));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ck_vendedor_precificacao_arredondamento'
    ) THEN
        ALTER TABLE tbl_vendedor_precificacao
            ADD CONSTRAINT ck_vendedor_precificacao_arredondamento
            CHECK (arredondamento_centavos IS NULL OR arredondamento_centavos IN (0, 90, 99));
    END IF;
END $$;

COMMENT ON COLUMN tbl_vendedor_precificacao.modo IS
    'sugestao_fornecedor = preço sugerido do fornecedor; margem_drop = % lucro sobre valor Drop';
COMMENT ON COLUMN tbl_vendedor_precificacao.arredondamento_centavos IS
    'Centavos finais do preço (ex.: 90 → ,90). NULL = sem arredondamento especial.';
COMMENT ON COLUMN tbl_vendedor_precificacao.margem_minima_alerta IS
    'Margem mínima (%) para alertas quando modo = sugestao_fornecedor.';
