-- DropNexo — Parâmetros fornecedor, valor_drop, campos completos produto, menus

-- ---------------------------------------------------------------------------
-- Preço Drop (oferta ao vendedor)
-- ---------------------------------------------------------------------------
ALTER TABLE tbl_produto ADD COLUMN IF NOT EXISTS valor_drop NUMERIC(12, 2);

UPDATE tbl_produto
SET valor_drop = COALESCE(valor_drop, valor_dropshipping, preco)
WHERE valor_drop IS NULL;

ALTER TABLE tbl_produto_variante ADD COLUMN IF NOT EXISTS valor_drop NUMERIC(12, 2);

UPDATE tbl_produto_variante v
SET valor_drop = COALESCE(v.valor_drop, v.preco)
FROM tbl_produto p
WHERE p.id = v.id_produto AND v.valor_drop IS NULL;

-- Campos Bling / cadastro completo
ALTER TABLE tbl_produto ADD COLUMN IF NOT EXISTS condicao VARCHAR(32);
ALTER TABLE tbl_produto ADD COLUMN IF NOT EXISTS origem_fiscal VARCHAR(4);
ALTER TABLE tbl_produto ADD COLUMN IF NOT EXISTS cest VARCHAR(10);
ALTER TABLE tbl_produto ADD COLUMN IF NOT EXISTS frete_gratis BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE tbl_produto ADD COLUMN IF NOT EXISTS volumes INTEGER;
ALTER TABLE tbl_produto ADD COLUMN IF NOT EXISTS producao VARCHAR(20);
ALTER TABLE tbl_produto ADD COLUMN IF NOT EXISTS preco_custo_origem NUMERIC(12, 2);

-- ---------------------------------------------------------------------------
-- Precificação do fornecedor (preço → valor_drop)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tbl_fornecedor_precificacao (
    id SERIAL PRIMARY KEY,
    id_tenant INTEGER NOT NULL REFERENCES tbl_tenant(id) ON DELETE CASCADE,
    escopo VARCHAR(20) NOT NULL DEFAULT 'global'
        CHECK (escopo IN ('global', 'categoria')),
    id_categoria INTEGER REFERENCES tbl_categoria(id) ON DELETE CASCADE,
    pct_ajuste NUMERIC(8, 4) NOT NULL DEFAULT 0,
    pct_taxas NUMERIC(8, 4) NOT NULL DEFAULT 0,
    pct_comissao NUMERIC(8, 4) NOT NULL DEFAULT 0,
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_fn_prec_escopo CHECK (
        (escopo = 'global' AND id_categoria IS NULL)
        OR (escopo = 'categoria' AND id_categoria IS NOT NULL)
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_fn_prec_global
    ON tbl_fornecedor_precificacao(id_tenant)
    WHERE escopo = 'global' AND ativo = TRUE;

CREATE UNIQUE INDEX IF NOT EXISTS uq_fn_prec_categoria
    ON tbl_fornecedor_precificacao(id_tenant, id_categoria)
    WHERE escopo = 'categoria' AND ativo = TRUE;

CREATE INDEX IF NOT EXISTS ix_fn_prec_tenant ON tbl_fornecedor_precificacao(id_tenant);

-- ---------------------------------------------------------------------------
-- Menu Parâmetros (fornecedor)
-- ---------------------------------------------------------------------------
INSERT INTO tbl_menu (
    nome_menu, descricao, data_page, icone, tipo_abrir, ordem, parent_id, pai, status, obs,
    id_modulo, nav_codigo, contexto_modulo
)
SELECT
    'Parâmetros', 'Regras comerciais e precificação', '/fornecedor/parametros',
    'settings', 'Mesma Janela', 65, NULL, TRUE, TRUE, NULL,
    (SELECT id FROM tbl_menu_modulo WHERE modulo = 'Operacional' LIMIT 1),
    'fn_parametros', 'fornecedor'
WHERE NOT EXISTS (SELECT 1 FROM tbl_menu WHERE nav_codigo = 'fn_parametros');

INSERT INTO tbl_permissao (codigo, modulo, descricao)
SELECT v.codigo, v.modulo, v.descricao
FROM (VALUES
    ('fn_parametros.ver', 'fn_parametros', 'Ver parâmetros do fornecedor'),
    ('fn_parametros.editar', 'fn_parametros', 'Editar parâmetros do fornecedor')
) AS v(codigo, modulo, descricao)
WHERE NOT EXISTS (SELECT 1 FROM tbl_permissao p WHERE p.codigo = v.codigo);

INSERT INTO tbl_perfil_permissao (id_perfil, id_permissao)
SELECT p.id, m.id
FROM tbl_perfil p
CROSS JOIN tbl_permissao m
WHERE p.codigo IN ('dono', 'admin')
  AND m.codigo IN ('fn_parametros.ver', 'fn_parametros.editar')
  AND NOT EXISTS (
      SELECT 1 FROM tbl_perfil_permissao pp
      WHERE pp.id_perfil = p.id AND pp.id_permissao = m.id
  );

INSERT INTO tbl_perfil_menu (id_perfil, id_menu, exibir)
SELECT p.id, m.id, TRUE
FROM tbl_perfil p
CROSS JOIN tbl_menu m
WHERE p.codigo IN ('dono', 'admin')
  AND m.nav_codigo = 'fn_parametros'
  AND NOT EXISTS (
      SELECT 1 FROM tbl_perfil_menu pm
      WHERE pm.id_perfil = p.id AND pm.id_menu = m.id
  );

-- Reordenar menus fornecedor
UPDATE tbl_menu SET nome_menu = 'Catálogo', ordem = 10
WHERE nav_codigo = 'catalogos' AND contexto_modulo = 'fornecedor';

UPDATE tbl_menu SET ordem = 20 WHERE nav_codigo = 'fn_vendedores';
UPDATE tbl_menu SET ordem = 30 WHERE nav_codigo = 'fn_categorias';
UPDATE tbl_menu SET ordem = 40 WHERE nav_codigo = 'fn_variacoes';
UPDATE tbl_menu SET ordem = 50 WHERE nav_codigo = 'fn_depositos';
UPDATE tbl_menu SET ordem = 60 WHERE nav_codigo = 'fn_usuarios';
UPDATE tbl_menu SET ordem = 65 WHERE nav_codigo = 'fn_parametros';
UPDATE tbl_menu SET ordem = 70 WHERE nav_codigo = 'fn_integracoes';
