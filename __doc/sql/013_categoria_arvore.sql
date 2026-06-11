-- DropNexo — Categorias em árvore (até 3 níveis) por segmento do fornecedor

ALTER TABLE tbl_categoria ADD COLUMN IF NOT EXISTS nivel SMALLINT NOT NULL DEFAULT 1;

ALTER TABLE tbl_categoria DROP CONSTRAINT IF EXISTS tbl_categoria_id_tenant_nome_key;

DROP INDEX IF EXISTS uq_categoria_nome_pai;

CREATE UNIQUE INDEX IF NOT EXISTS uq_categoria_seg_pai_nome
    ON tbl_categoria (
        id_tenant,
        COALESCE(id_segmento, 0),
        COALESCE(parent_id, 0),
        LOWER(nome)
    );

-- Recalcula nível (migração de categorias planas existentes)
UPDATE tbl_categoria SET nivel = 1, parent_id = NULL WHERE parent_id IS NULL AND nivel IS NULL;

UPDATE tbl_categoria c SET nivel = 1
WHERE c.parent_id IS NULL AND (c.nivel IS NULL OR c.nivel < 1);

UPDATE tbl_categoria filho SET nivel = 2
FROM tbl_categoria pai
WHERE filho.parent_id = pai.id AND pai.nivel = 1 AND filho.nivel < 2;

UPDATE tbl_categoria filho SET nivel = 3
FROM tbl_categoria pai
WHERE filho.parent_id = pai.id AND pai.nivel = 2 AND filho.nivel < 3;

-- Menu Categorias (fornecedor)
INSERT INTO tbl_menu (nome_menu, descricao, data_page, icone, ordem, pai, status, nav_codigo, contexto_modulo)
SELECT v.nome, v.descricao, v.page, v.ico, v.ord, TRUE, TRUE, v.nav, v.ctx
FROM (VALUES
    ('Categorias', 'Árvore de categorias por segmento', '/fornecedor/categorias', 'folder', 22, 'fn_categorias', 'fornecedor')
) AS v(nome, descricao, page, ico, ord, nav, ctx)
WHERE NOT EXISTS (SELECT 1 FROM tbl_menu m WHERE m.nav_codigo = v.nav);

INSERT INTO tbl_permissao (codigo, modulo, descricao) VALUES
    ('fn_categorias.ver', 'fn_categorias', 'Ver árvore de categorias'),
    ('fn_categorias.editar', 'fn_categorias', 'Editar árvore de categorias')
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO tbl_perfil_permissao (id_perfil, id_permissao)
SELECT p.id, m.id
FROM tbl_perfil p
CROSS JOIN tbl_permissao m
WHERE p.codigo IN ('dono', 'admin')
  AND m.codigo IN ('fn_categorias.ver', 'fn_categorias.editar')
ON CONFLICT DO NOTHING;

INSERT INTO tbl_perfil_menu (id_perfil, id_menu, exibir)
SELECT p.id, m.id, TRUE
FROM tbl_perfil p
CROSS JOIN tbl_menu m
WHERE m.status = TRUE
  AND p.codigo IN ('dono', 'admin')
  AND m.nav_codigo = 'fn_categorias'
ON CONFLICT DO NOTHING;
