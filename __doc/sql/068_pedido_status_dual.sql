-- Pedido: status do comprador (canal/cliente final) + status do vendedor (operação drop)

ALTER TABLE tbl_pedido DROP CONSTRAINT IF EXISTS tbl_pedido_status_check;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'tbl_pedido' AND column_name = 'status'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'tbl_pedido' AND column_name = 'status_vendedor'
    ) THEN
        ALTER TABLE tbl_pedido RENAME COLUMN status TO status_vendedor;
    END IF;
END $$;

ALTER TABLE tbl_pedido
    ADD COLUMN IF NOT EXISTS status_comprador VARCHAR(30) NOT NULL DEFAULT 'pendente';

ALTER TABLE tbl_pedido DROP CONSTRAINT IF EXISTS tbl_pedido_status_comprador_check;
ALTER TABLE tbl_pedido ADD CONSTRAINT tbl_pedido_status_comprador_check
    CHECK (status_comprador IN ('pendente', 'pago', 'cancelado'));

ALTER TABLE tbl_pedido DROP CONSTRAINT IF EXISTS tbl_pedido_status_vendedor_check;
ALTER TABLE tbl_pedido ADD CONSTRAINT tbl_pedido_status_vendedor_check
    CHECK (status_vendedor IN (
        'rascunho', 'importado', 'aguardando_pagamento', 'pago',
        'em_expedicao', 'entregue', 'cancelado'
    ));

-- Pedidos Bling: comprador já pagou no canal; vendedor ainda prepara/paga fornecedor
UPDATE tbl_pedido
SET status_comprador = 'pago',
    status_vendedor = 'importado'
WHERE origem = 'bling'
  AND status_vendedor = 'pago'
  AND (status_comprador IS NULL OR status_comprador = 'pendente');

DROP INDEX IF EXISTS ix_pedido_fornecedor_status;
CREATE INDEX IF NOT EXISTS ix_pedido_fornecedor_status_vendedor
    ON tbl_pedido(id_tenant_fornecedor, status_vendedor);

DROP INDEX IF EXISTS ix_pedido_vendedor_status;
CREATE INDEX IF NOT EXISTS ix_pedido_vendedor_status_vendedor
    ON tbl_pedido(id_tenant_vendedor, status_vendedor);

CREATE INDEX IF NOT EXISTS ix_pedido_vendedor_status_comprador
    ON tbl_pedido(id_tenant_vendedor, status_comprador);

COMMENT ON COLUMN tbl_pedido.status_comprador IS
    'Pagamento/situação do cliente final no canal de venda (Bling, loja, etc.).';
COMMENT ON COLUMN tbl_pedido.status_vendedor IS
    'Fluxo operacional do vendedor no DropNexo (pagar fornecedor, frete, expedição).';
