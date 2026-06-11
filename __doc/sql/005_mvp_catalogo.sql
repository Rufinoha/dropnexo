-- DropNexo — MVP catálogo (categorias, produtos, estoque por tenant)

CREATE TABLE IF NOT EXISTS tbl_categoria (
    id SERIAL PRIMARY KEY,
    id_tenant INTEGER NOT NULL REFERENCES tbl_tenant(id) ON DELETE CASCADE,
    nome VARCHAR(120) NOT NULL,
    descricao TEXT,
    ordem INTEGER NOT NULL DEFAULT 0,
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (id_tenant, nome)
);

CREATE INDEX IF NOT EXISTS ix_categoria_tenant ON tbl_categoria(id_tenant);

CREATE TABLE IF NOT EXISTS tbl_produto (
    id SERIAL PRIMARY KEY,
    id_tenant INTEGER NOT NULL REFERENCES tbl_tenant(id) ON DELETE CASCADE,
    id_categoria INTEGER REFERENCES tbl_categoria(id) ON DELETE SET NULL,
    sku VARCHAR(64),
    nome VARCHAR(255) NOT NULL,
    descricao TEXT,
    preco NUMERIC(12, 2) NOT NULL DEFAULT 0,
    preco_promocional NUMERIC(12, 2),
    unidade VARCHAR(20) NOT NULL DEFAULT 'UN',
    imagem_url TEXT,
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    publicado BOOLEAN NOT NULL DEFAULT FALSE,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_produto_tenant_sku
    ON tbl_produto(id_tenant, sku) WHERE sku IS NOT NULL AND sku <> '';

CREATE INDEX IF NOT EXISTS ix_produto_tenant ON tbl_produto(id_tenant);
CREATE INDEX IF NOT EXISTS ix_produto_publicado ON tbl_produto(id_tenant, publicado) WHERE publicado = TRUE;

CREATE TABLE IF NOT EXISTS tbl_produto_estoque (
    id_produto INTEGER PRIMARY KEY REFERENCES tbl_produto(id) ON DELETE CASCADE,
    quantidade INTEGER NOT NULL DEFAULT 0 CHECK (quantidade >= 0),
    reservado INTEGER NOT NULL DEFAULT 0 CHECK (reservado >= 0),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Categorias padrão para tenants existentes (idempotente)
INSERT INTO tbl_categoria (id_tenant, nome, ordem)
SELECT t.id, c.nome, c.ord
FROM tbl_tenant t
CROSS JOIN (VALUES ('Geral', 10), ('Destaques', 20)) AS c(nome, ord)
WHERE NOT EXISTS (
    SELECT 1 FROM tbl_categoria cat WHERE cat.id_tenant = t.id AND cat.nome = c.nome
);
