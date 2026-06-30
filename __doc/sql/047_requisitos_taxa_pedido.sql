-- Taxa por pedido nos requisitos do vendedor

ALTER TABLE tbl_fornecedor_requisitos_vendedor
    ADD COLUMN IF NOT EXISTS cobra_taxa_pedido BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE tbl_fornecedor_requisitos_vendedor
    ADD COLUMN IF NOT EXISTS valor_taxa_pedido NUMERIC(12, 2) NOT NULL DEFAULT 0;
