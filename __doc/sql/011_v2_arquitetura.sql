-- DropNexo V2 — segmentos, vínculo vendedor×fornecedor, produto vendedor, precificação, menus por módulo

-- Segmento (nicho) do fornecedor
CREATE TABLE IF NOT EXISTS tbl_segmento (
    id SERIAL PRIMARY KEY,
    id_tenant INTEGER NOT NULL REFERENCES tbl_tenant(id) ON DELETE CASCADE,
    nome VARCHAR(120) NOT NULL,
    descricao TEXT,
    ordem INTEGER NOT NULL DEFAULT 0,
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (id_tenant, nome)
);

CREATE INDEX IF NOT EXISTS ix_segmento_tenant ON tbl_segmento(id_tenant);

ALTER TABLE tbl_categoria ADD COLUMN IF NOT EXISTS id_segmento INTEGER
    REFERENCES tbl_segmento(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_categoria_segmento ON tbl_categoria(id_segmento);

-- Vínculo vendedor ↔ fornecedor (aprovação)
CREATE TABLE IF NOT EXISTS tbl_vinculo_vendedor_fornecedor (
    id SERIAL PRIMARY KEY,
    id_tenant_vendedor INTEGER NOT NULL REFERENCES tbl_tenant(id) ON DELETE CASCADE,
    id_tenant_fornecedor INTEGER NOT NULL REFERENCES tbl_tenant(id) ON DELETE CASCADE,
    status VARCHAR(24) NOT NULL DEFAULT 'aguardando'
        CHECK (status IN ('aguardando', 'ativo', 'recusado', 'inativo')),
    snapshot_vendedor JSONB,
    mensagem_solicitacao TEXT,
    mensagem_resposta TEXT,
    solicitado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    respondido_em TIMESTAMPTZ,
    inativado_em TIMESTAMPTZ,
    UNIQUE (id_tenant_vendedor, id_tenant_fornecedor)
);

CREATE INDEX IF NOT EXISTS ix_vinculo_fornecedor ON tbl_vinculo_vendedor_fornecedor(id_tenant_fornecedor, status);
CREATE INDEX IF NOT EXISTS ix_vinculo_vendedor ON tbl_vinculo_vendedor_fornecedor(id_tenant_vendedor, status);

-- Produto ativado pelo vendedor (vitrine — não altera mestre do fornecedor)
CREATE TABLE IF NOT EXISTS tbl_produto_vendedor (
    id SERIAL PRIMARY KEY,
    id_tenant_vendedor INTEGER NOT NULL REFERENCES tbl_tenant(id) ON DELETE CASCADE,
    id_tenant_fornecedor INTEGER NOT NULL REFERENCES tbl_tenant(id) ON DELETE CASCADE,
    id_variante INTEGER NOT NULL REFERENCES tbl_produto_variante(id) ON DELETE CASCADE,
    id_produto INTEGER NOT NULL REFERENCES tbl_produto(id) ON DELETE CASCADE,
    nome_vitrine VARCHAR(255),
    descricao_vitrine TEXT,
    imagem_url_vitrine TEXT,
    preco_fornecedor NUMERIC(12, 2) NOT NULL DEFAULT 0,
    preco_venda NUMERIC(12, 2) NOT NULL DEFAULT 0,
    preco_manual BOOLEAN NOT NULL DEFAULT FALSE,
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    estoque_vitrine INTEGER NOT NULL DEFAULT 0 CHECK (estoque_vitrine >= 0),
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (id_tenant_vendedor, id_variante)
);

CREATE INDEX IF NOT EXISTS ix_produto_vendedor_tenant ON tbl_produto_vendedor(id_tenant_vendedor, ativo);
CREATE INDEX IF NOT EXISTS ix_produto_vendedor_forn ON tbl_produto_vendedor(id_tenant_fornecedor);

-- Regras de precificação do vendedor (global, segmento ou categoria)
CREATE TABLE IF NOT EXISTS tbl_vendedor_precificacao (
    id SERIAL PRIMARY KEY,
    id_tenant_vendedor INTEGER NOT NULL REFERENCES tbl_tenant(id) ON DELETE CASCADE,
    escopo VARCHAR(20) NOT NULL DEFAULT 'global'
        CHECK (escopo IN ('global', 'segmento', 'categoria')),
    id_segmento INTEGER REFERENCES tbl_segmento(id) ON DELETE CASCADE,
    id_categoria INTEGER REFERENCES tbl_categoria(id) ON DELETE CASCADE,
    pct_marketplace NUMERIC(8, 4) NOT NULL DEFAULT 0,
    pct_impostos NUMERIC(8, 4) NOT NULL DEFAULT 0,
    pct_taxas NUMERIC(8, 4) NOT NULL DEFAULT 0,
    pct_margem_lucro NUMERIC(8, 4) NOT NULL DEFAULT 0,
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_precificacao_escopo CHECK (
        (escopo = 'global' AND id_segmento IS NULL AND id_categoria IS NULL)
        OR (escopo = 'segmento' AND id_segmento IS NOT NULL AND id_categoria IS NULL)
        OR (escopo = 'categoria' AND id_categoria IS NOT NULL)
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_precificacao_global
    ON tbl_vendedor_precificacao(id_tenant_vendedor)
    WHERE escopo = 'global' AND ativo = TRUE;

-- Menu: contexto do módulo (fornecedor | vendedor | comum)
ALTER TABLE tbl_menu ADD COLUMN IF NOT EXISTS contexto_modulo VARCHAR(20) NOT NULL DEFAULT 'comum';

UPDATE tbl_menu SET contexto_modulo = 'vendedor'
WHERE nav_codigo IN ('fornecedores', 'produtos', 'integracoes')
  AND nome_menu IN ('Fornecedores', 'Meus produtos', 'Integrações');

UPDATE tbl_menu SET contexto_modulo = 'fornecedor'
WHERE nav_codigo = 'catalogos';

-- Módulos de navegação (seletor sidebar)
INSERT INTO tbl_menu_modulo (modulo, icone, ordem, ativo) VALUES
    ('Fornecedor', 'truck', 5, TRUE),
    ('Vendedor', 'shopping-cart', 6, TRUE)
ON CONFLICT (modulo) DO NOTHING;

-- Novos itens de menu V2
INSERT INTO tbl_menu (nome_menu, descricao, data_page, icone, ordem, pai, status, nav_codigo, contexto_modulo)
SELECT v.nome, v.descricao, v.page, v.ico, v.ord, TRUE, TRUE, v.nav, v.ctx
FROM (VALUES
    ('Depósitos', 'Filiais de expedição', '/fornecedor/depositos', 'map-pin', 15, 'fn_depositos', 'fornecedor'),
    ('Segmentos', 'Nichos e categorias', '/fornecedor/segmentos', 'layers', 20, 'fn_segmentos', 'fornecedor'),
    ('Vendedores', 'Parceiros e aprovações', '/fornecedor/vendedores', 'users', 55, 'fn_vendedores', 'fornecedor'),
    ('Catálogo', 'Produtos dos fornecedores aprovados', '/vendedor/catalogo', 'package', 35, 'vd_catalogo', 'vendedor'),
    ('Precificação', 'Margens e preços de venda', '/vendedor/precificacao', 'percent', 45, 'vd_precificacao', 'vendedor'),
    ('Pedidos', 'Pedidos (em breve)', '/vendedor/pedidos', 'clipboard-list', 50, 'vd_pedidos', 'vendedor'),
    ('Expedição', 'Entrega ao cliente final', '/vendedor/expedicao', 'truck', 60, 'vd_expedicao', 'vendedor')
) AS v(nome, descricao, page, ico, ord, nav, ctx)
WHERE NOT EXISTS (SELECT 1 FROM tbl_menu m WHERE m.nav_codigo = v.nav);

UPDATE tbl_menu SET contexto_modulo = 'fornecedor', ordem = 30
WHERE nav_codigo = 'catalogos';

UPDATE tbl_menu SET contexto_modulo = 'vendedor', ordem = 25, nome_menu = 'Fornecedores'
WHERE nav_codigo = 'fornecedores';

UPDATE tbl_menu SET contexto_modulo = 'vendedor', ordem = 40
WHERE nav_codigo = 'produtos';

UPDATE tbl_menu SET contexto_modulo = 'comum', ordem = 5
WHERE nav_codigo = 'inicio';

-- Permissões V2
INSERT INTO tbl_permissao (codigo, modulo, descricao) VALUES
    ('precificacao.ver', 'precificacao', 'Ver precificação'),
    ('precificacao.editar', 'precificacao', 'Editar regras de precificação'),
    ('fn_vendedores.ver', 'fn_vendedores', 'Ver vendedores parceiros'),
    ('fn_vendedores.editar', 'fn_vendedores', 'Aprovar ou recusar vendedores'),
    ('fn_segmentos.ver', 'fn_segmentos', 'Ver segmentos'),
    ('fn_segmentos.editar', 'fn_segmentos', 'Editar segmentos'),
    ('vd_catalogo.ver', 'vd_catalogo', 'Ver catálogo agregado'),
    ('vd_catalogo.editar', 'vd_catalogo', 'Ativar produtos do catálogo'),
    ('plataforma.fornecedores', 'plataforma', 'Cadastrar fornecedores na plataforma (dev)')
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO tbl_perfil_permissao (id_perfil, id_permissao)
SELECT p.id, m.id
FROM tbl_perfil p
CROSS JOIN tbl_permissao m
WHERE p.codigo IN ('dono', 'admin')
  AND m.codigo IN (
    'precificacao.ver', 'precificacao.editar',
    'fn_vendedores.ver', 'fn_vendedores.editar',
    'fn_segmentos.ver', 'fn_segmentos.editar',
    'vd_catalogo.ver', 'vd_catalogo.editar'
  )
ON CONFLICT DO NOTHING;

INSERT INTO tbl_perfil_permissao (id_perfil, id_permissao)
SELECT p.id, m.id FROM tbl_perfil p
JOIN tbl_permissao m ON m.codigo IN (
    'dashboard.ver', 'fornecedores.ver', 'vd_catalogo.ver', 'vd_catalogo.editar',
    'produtos.ver', 'produtos.editar', 'precificacao.ver', 'precificacao.editar'
) WHERE p.codigo = 'vendedor'
ON CONFLICT DO NOTHING;

-- Perfil × menu novos itens
INSERT INTO tbl_perfil_menu (id_perfil, id_menu, exibir)
SELECT p.id, m.id, TRUE
FROM tbl_perfil p
CROSS JOIN tbl_menu m
WHERE m.status = TRUE
  AND p.codigo IN ('dono', 'admin')
  AND m.nav_codigo IN (
    'fn_depositos', 'fn_segmentos', 'fn_vendedores',
    'vd_catalogo', 'vd_precificacao', 'vd_pedidos', 'vd_expedicao'
  )
ON CONFLICT DO NOTHING;
