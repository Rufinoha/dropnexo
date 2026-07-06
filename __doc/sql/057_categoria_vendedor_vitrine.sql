-- Categoria do vendedor na vitrine (produtos integrados da rede)

ALTER TABLE tbl_produto_vendedor
    ADD COLUMN IF NOT EXISTS id_categoria_vendedor INTEGER
        REFERENCES tbl_categoria(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_produto_vendedor_cat_vend
    ON tbl_produto_vendedor(id_tenant_vendedor, id_categoria_vendedor)
    WHERE id_categoria_vendedor IS NOT NULL;

COMMENT ON COLUMN tbl_produto_vendedor.id_categoria_vendedor IS
    'Categoria na árvore do vendedor (organização da vitrine). Independente da categoria do fornecedor.';
