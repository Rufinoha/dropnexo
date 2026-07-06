-- Expedição + referência Bling nos pedidos (Fase 4 + Fase 3)

ALTER TABLE tbl_pedido ADD COLUMN IF NOT EXISTS id_bling_pedido VARCHAR(64);
ALTER TABLE tbl_pedido ADD COLUMN IF NOT EXISTS codigo_rastreio VARCHAR(80);
ALTER TABLE tbl_pedido ADD COLUMN IF NOT EXISTS transportadora VARCHAR(120);
ALTER TABLE tbl_pedido ADD COLUMN IF NOT EXISTS expedido_em TIMESTAMPTZ;
ALTER TABLE tbl_pedido ADD COLUMN IF NOT EXISTS entregue_em TIMESTAMPTZ;

CREATE UNIQUE INDEX IF NOT EXISTS uq_pedido_bling_fornecedor
    ON tbl_pedido(id_tenant_vendedor, id_bling_pedido, id_tenant_fornecedor)
    WHERE id_bling_pedido IS NOT NULL AND id_bling_pedido <> '';

COMMENT ON COLUMN tbl_pedido.id_bling_pedido IS 'ID do pedido de venda no Bling (importação vendedor).';
COMMENT ON COLUMN tbl_pedido.codigo_rastreio IS 'Código de rastreio informado na expedição.';
