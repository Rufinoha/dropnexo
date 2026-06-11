-- DropNexo — favoritos do vendedor (produtos da rede)

CREATE TABLE IF NOT EXISTS tbl_produto_favorito (
    id SERIAL PRIMARY KEY,
    id_tenant INTEGER NOT NULL REFERENCES tbl_tenant(id) ON DELETE CASCADE,
    id_produto INTEGER NOT NULL REFERENCES tbl_produto(id) ON DELETE CASCADE,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (id_tenant, id_produto)
);

CREATE INDEX IF NOT EXISTS ix_produto_favorito_tenant ON tbl_produto_favorito(id_tenant);
