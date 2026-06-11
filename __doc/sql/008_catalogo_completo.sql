-- DropNexo — Catálogo 1.5: categorias em árvore, produto pai, variantes, imagens, campos ERP

-- Categorias hierárquicas
ALTER TABLE tbl_categoria ADD COLUMN IF NOT EXISTS parent_id INTEGER REFERENCES tbl_categoria(id) ON DELETE SET NULL;
ALTER TABLE tbl_categoria ADD COLUMN IF NOT EXISTS slug VARCHAR(80);

CREATE INDEX IF NOT EXISTS ix_categoria_parent ON tbl_categoria(parent_id);

-- Produto pai (catálogo fornecedor)
ALTER TABLE tbl_produto ADD COLUMN IF NOT EXISTS formato VARCHAR(2) NOT NULL DEFAULT 'S'
    CHECK (formato IN ('S', 'E'));
ALTER TABLE tbl_produto ADD COLUMN IF NOT EXISTS tipo VARCHAR(2) NOT NULL DEFAULT 'P'
    CHECK (tipo IN ('P', 'S'));
ALTER TABLE tbl_produto ADD COLUMN IF NOT EXISTS preco_custo NUMERIC(12, 2);
ALTER TABLE tbl_produto ADD COLUMN IF NOT EXISTS gtin VARCHAR(20);
ALTER TABLE tbl_produto ADD COLUMN IF NOT EXISTS ncm VARCHAR(10);
ALTER TABLE tbl_produto ADD COLUMN IF NOT EXISTS referencia VARCHAR(64);
ALTER TABLE tbl_produto ADD COLUMN IF NOT EXISTS peso_liquido_kg NUMERIC(10, 3);
ALTER TABLE tbl_produto ADD COLUMN IF NOT EXISTS peso_bruto_kg NUMERIC(10, 3);
ALTER TABLE tbl_produto ADD COLUMN IF NOT EXISTS altura_cm NUMERIC(10, 2);
ALTER TABLE tbl_produto ADD COLUMN IF NOT EXISTS largura_cm NUMERIC(10, 2);
ALTER TABLE tbl_produto ADD COLUMN IF NOT EXISTS profundidade_cm NUMERIC(10, 2);
ALTER TABLE tbl_produto ADD COLUMN IF NOT EXISTS prazo_envio_dias INTEGER;
ALTER TABLE tbl_produto ADD COLUMN IF NOT EXISTS moq INTEGER NOT NULL DEFAULT 1;
ALTER TABLE tbl_produto ADD COLUMN IF NOT EXISTS id_variante_padrao INTEGER;

-- Variantes (SKU vendável — simples ou filho de produto com variações)
CREATE TABLE IF NOT EXISTS tbl_produto_variante (
    id SERIAL PRIMARY KEY,
    id_produto INTEGER NOT NULL REFERENCES tbl_produto(id) ON DELETE CASCADE,
    sku VARCHAR(64),
    nome_exibicao VARCHAR(255) NOT NULL DEFAULT 'Padrão',
    preco NUMERIC(12, 2) NOT NULL DEFAULT 0,
    preco_promocional NUMERIC(12, 2),
    preco_custo NUMERIC(12, 2),
    atributos JSONB NOT NULL DEFAULT '{}',
    imagem_url TEXT,
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    ordem INTEGER NOT NULL DEFAULT 0,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_variante_produto_sku
    ON tbl_produto_variante(id_produto, sku) WHERE sku IS NOT NULL AND sku <> '';

CREATE INDEX IF NOT EXISTS ix_variante_produto ON tbl_produto_variante(id_produto);

CREATE TABLE IF NOT EXISTS tbl_produto_variante_estoque (
    id_variante INTEGER PRIMARY KEY REFERENCES tbl_produto_variante(id) ON DELETE CASCADE,
    quantidade INTEGER NOT NULL DEFAULT 0 CHECK (quantidade >= 0),
    reservado INTEGER NOT NULL DEFAULT 0 CHECK (reservado >= 0),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Definição de atributos no produto pai (Cor, Tamanho…)
CREATE TABLE IF NOT EXISTS tbl_produto_atributo (
    id SERIAL PRIMARY KEY,
    id_produto INTEGER NOT NULL REFERENCES tbl_produto(id) ON DELETE CASCADE,
    nome VARCHAR(60) NOT NULL,
    valores JSONB NOT NULL DEFAULT '[]',
    ordem INTEGER NOT NULL DEFAULT 0,
    UNIQUE (id_produto, nome)
);

-- Galeria de imagens
CREATE TABLE IF NOT EXISTS tbl_produto_imagem (
    id SERIAL PRIMARY KEY,
    id_produto INTEGER NOT NULL REFERENCES tbl_produto(id) ON DELETE CASCADE,
    id_variante INTEGER REFERENCES tbl_produto_variante(id) ON DELETE CASCADE,
    caminho TEXT NOT NULL,
    ordem INTEGER NOT NULL DEFAULT 0,
    principal BOOLEAN NOT NULL DEFAULT FALSE,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_produto_imagem_produto ON tbl_produto_imagem(id_produto);

-- Favoritos passam a referenciar variante (SKU da rede)
ALTER TABLE tbl_produto_favorito ADD COLUMN IF NOT EXISTS id_variante INTEGER
    REFERENCES tbl_produto_variante(id) ON DELETE CASCADE;

-- Migração: uma variante padrão por produto existente
INSERT INTO tbl_produto_variante (
    id_produto, sku, nome_exibicao, preco, preco_promocional, imagem_url, ativo, ordem, atualizado_em
)
SELECT p.id, p.sku, COALESCE(NULLIF(TRIM(p.nome), ''), 'Padrão'), p.preco, p.preco_promocional,
       p.imagem_url, p.ativo, 0, p.atualizado_em
FROM tbl_produto p
WHERE NOT EXISTS (SELECT 1 FROM tbl_produto_variante v WHERE v.id_produto = p.id);

INSERT INTO tbl_produto_variante_estoque (id_variante, quantidade, reservado, atualizado_em)
SELECT v.id, COALESCE(e.quantidade, 0), COALESCE(e.reservado, 0), COALESCE(e.atualizado_em, NOW())
FROM tbl_produto_variante v
JOIN tbl_produto p ON p.id = v.id_produto
LEFT JOIN tbl_produto_estoque e ON e.id_produto = p.id
WHERE NOT EXISTS (SELECT 1 FROM tbl_produto_variante_estoque ve WHERE ve.id_variante = v.id);

UPDATE tbl_produto p
SET id_variante_padrao = v.id, formato = COALESCE(NULLIF(p.formato, ''), 'S')
FROM tbl_produto_variante v
WHERE v.id_produto = p.id
  AND p.id_variante_padrao IS NULL
  AND v.id = (
      SELECT v2.id FROM tbl_produto_variante v2
      WHERE v2.id_produto = p.id ORDER BY v2.ordem, v2.id LIMIT 1
  );

UPDATE tbl_produto_favorito f
SET id_variante = p.id_variante_padrao
FROM tbl_produto p
WHERE f.id_variante IS NULL
  AND p.id = f.id_produto
  AND p.id_variante_padrao IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_favorito_tenant_variante
    ON tbl_produto_favorito(id_tenant, id_variante) WHERE id_variante IS NOT NULL;
