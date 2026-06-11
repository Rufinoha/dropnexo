-- DropNexo — Kits montados pelo vendedor (combina produtos/variantes da rede)

CREATE TABLE IF NOT EXISTS tbl_kit_vendedor (
    id SERIAL PRIMARY KEY,
    id_tenant INTEGER NOT NULL REFERENCES tbl_tenant(id) ON DELETE CASCADE,
    nome VARCHAR(255) NOT NULL,
    descricao TEXT,
    preco_venda NUMERIC(12, 2) NOT NULL DEFAULT 0,
    usar_preco_sugerido BOOLEAN NOT NULL DEFAULT TRUE,
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_kit_vendedor_tenant ON tbl_kit_vendedor(id_tenant);

CREATE TABLE IF NOT EXISTS tbl_kit_vendedor_item (
    id SERIAL PRIMARY KEY,
    id_kit INTEGER NOT NULL REFERENCES tbl_kit_vendedor(id) ON DELETE CASCADE,
    id_variante INTEGER NOT NULL REFERENCES tbl_produto_variante(id) ON DELETE RESTRICT,
    quantidade INTEGER NOT NULL DEFAULT 1 CHECK (quantidade > 0),
    ordem INTEGER NOT NULL DEFAULT 0,
    UNIQUE (id_kit, id_variante)
);

CREATE INDEX IF NOT EXISTS ix_kit_vendedor_item_kit ON tbl_kit_vendedor_item(id_kit);
