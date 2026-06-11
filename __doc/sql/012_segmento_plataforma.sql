-- DropNexo — Segmentos oficiais da plataforma (dev) + fornecedor escolhe os que atende

ALTER TABLE tbl_segmento ADD COLUMN IF NOT EXISTS slug VARCHAR(64);

ALTER TABLE tbl_segmento ALTER COLUMN id_tenant DROP NOT NULL;

ALTER TABLE tbl_segmento DROP CONSTRAINT IF EXISTS tbl_segmento_id_tenant_nome_key;

UPDATE tbl_categoria SET id_segmento = NULL
WHERE id_segmento IN (SELECT id FROM tbl_segmento WHERE id_tenant IS NOT NULL);

DELETE FROM tbl_segmento WHERE id_tenant IS NOT NULL;

UPDATE tbl_segmento SET id_tenant = NULL WHERE id_tenant IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_segmento_slug ON tbl_segmento(slug) WHERE slug IS NOT NULL AND slug <> '';

CREATE UNIQUE INDEX IF NOT EXISTS uq_segmento_nome_plataforma ON tbl_segmento(LOWER(nome)) WHERE id_tenant IS NULL;

CREATE TABLE IF NOT EXISTS tbl_fornecedor_segmento (
    id_tenant INTEGER NOT NULL REFERENCES tbl_tenant(id) ON DELETE CASCADE,
    id_segmento INTEGER NOT NULL REFERENCES tbl_segmento(id) ON DELETE CASCADE,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id_tenant, id_segmento)
);

CREATE INDEX IF NOT EXISTS ix_fornecedor_segmento_seg ON tbl_fornecedor_segmento(id_segmento);

-- Seed segmentos oficiais (idempotente por slug)
INSERT INTO tbl_segmento (id_tenant, nome, slug, descricao, ordem, ativo)
SELECT NULL, v.nome, v.slug, v.descr, v.ord, TRUE
FROM (VALUES
    ('Moda e vestuário', 'moda-vestuario', 'Roupas, moda íntima e acessórios de vestuário', 10),
    ('Calçados', 'calcados', 'Calçados em geral', 20),
    ('Joias e acessórios', 'joias-acessorios', 'Joias, bijuterias e acessórios pessoais', 30),
    ('Eletrônicos', 'eletronicos', 'Eletrônicos e tecnologia', 40),
    ('Casa e decoração', 'casa-decoracao', 'Casa, móveis e decoração', 50),
    ('Beleza e perfumaria', 'beleza-perfumaria', 'Cosméticos, perfumaria e cuidados pessoais', 60),
    ('Esporte e lazer', 'esporte-lazer', 'Artigos esportivos e lazer', 70),
    ('Infantil', 'infantil', 'Produtos infantis', 80),
    ('Pet', 'pet', 'Produtos para animais', 90),
    ('Papelaria e escritório', 'papelaria-escritorio', 'Papelaria e material de escritório', 100),
    ('Automotivo', 'automotivo', 'Peças e acessórios automotivos', 110),
    ('Saúde e bem-estar', 'saude-bem-estar', 'Saúde, suplementos (verificar regulamentação)', 120)
) AS v(nome, slug, descr, ord)
WHERE NOT EXISTS (SELECT 1 FROM tbl_segmento s WHERE s.slug = v.slug);
