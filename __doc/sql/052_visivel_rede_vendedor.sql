-- Visibilidade do fornecedor na rede de vendedores (switch em Parâmetros)

ALTER TABLE tbl_fornecedor_requisitos_vendedor
    ADD COLUMN IF NOT EXISTS visivel_rede_vendedor BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN tbl_fornecedor_requisitos_vendedor.visivel_rede_vendedor IS
    'Quando TRUE, o fornecedor pode aparecer na rede de vendedores (se tiver produto ativo).';
