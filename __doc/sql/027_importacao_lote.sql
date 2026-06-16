-- DropNexo — motor de importação (lote, erros, layouts) + rastreio em produtos

-- ---------------------------------------------------------------------------
-- Layouts (Fase 1: estrutura + layout padrão CSV catálogo)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tbl_importacao_layout (
    id SERIAL PRIMARY KEY,
    id_tenant INTEGER NOT NULL REFERENCES tbl_tenant(id) ON DELETE CASCADE,
    modulo VARCHAR(40) NOT NULL DEFAULT 'catalogo_produto',
    nome VARCHAR(120) NOT NULL,
    descricao TEXT,
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    padrao BOOLEAN NOT NULL DEFAULT FALSE,
    tipo_arquivo VARCHAR(10) NOT NULL DEFAULT 'csv' CHECK (tipo_arquivo IN ('csv', 'xlsx')),
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (id_tenant, modulo, nome)
);

CREATE INDEX IF NOT EXISTS ix_import_layout_tenant_modulo
    ON tbl_importacao_layout(id_tenant, modulo) WHERE ativo = TRUE;

CREATE TABLE IF NOT EXISTS tbl_importacao_layout_campo (
    id SERIAL PRIMARY KEY,
    id_layout INTEGER NOT NULL REFERENCES tbl_importacao_layout(id) ON DELETE CASCADE,
    campo_interno VARCHAR(64) NOT NULL,
    coluna_arquivo VARCHAR(120) NOT NULL,
    obrigatorio BOOLEAN NOT NULL DEFAULT FALSE,
    ordem INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS ix_import_layout_campo_layout
    ON tbl_importacao_layout_campo(id_layout, ordem);

-- ---------------------------------------------------------------------------
-- Lotes de importação
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tbl_importacao_lote (
    id SERIAL PRIMARY KEY,
    id_tenant INTEGER NOT NULL REFERENCES tbl_tenant(id) ON DELETE CASCADE,
    numero VARCHAR(32) NOT NULL,
    modulo VARCHAR(40) NOT NULL DEFAULT 'catalogo_produto',
    origem VARCHAR(20) NOT NULL CHECK (origem IN ('manual', 'arquivo', 'integracao')),
    provedor VARCHAR(30),
    id_layout INTEGER REFERENCES tbl_importacao_layout(id) ON DELETE SET NULL,
    nome_lote VARCHAR(120),
    nome_arquivo VARCHAR(255),
    status VARCHAR(20) NOT NULL DEFAULT 'processando'
        CHECK (status IN ('processando', 'concluido', 'erro', 'cancelado')),
    total_linhas INTEGER NOT NULL DEFAULT 0,
    total_importadas INTEGER NOT NULL DEFAULT 0,
    total_atualizadas INTEGER NOT NULL DEFAULT 0,
    total_rejeitadas INTEGER NOT NULL DEFAULT 0,
    meta JSONB,
    importado_por INTEGER REFERENCES tbl_usuario(id) ON DELETE SET NULL,
    importado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finalizado_em TIMESTAMPTZ,
    UNIQUE (id_tenant, numero)
);

CREATE INDEX IF NOT EXISTS ix_import_lote_tenant_data
    ON tbl_importacao_lote(id_tenant, importado_em DESC);

CREATE INDEX IF NOT EXISTS ix_import_lote_tenant_modulo
    ON tbl_importacao_lote(id_tenant, modulo, importado_em DESC);

-- ---------------------------------------------------------------------------
-- Erros por lote
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tbl_importacao_erro (
    id SERIAL PRIMARY KEY,
    id_tenant INTEGER NOT NULL REFERENCES tbl_tenant(id) ON DELETE CASCADE,
    id_importacao_lote INTEGER NOT NULL REFERENCES tbl_importacao_lote(id) ON DELETE CASCADE,
    modulo VARCHAR(40) NOT NULL DEFAULT 'catalogo_produto',
    linha_arquivo INTEGER,
    ref_externa VARCHAR(64),
    nome_registro VARCHAR(255),
    sku_registro VARCHAR(64),
    campo VARCHAR(64),
    mensagem TEXT NOT NULL,
    payload JSONB,
    corrigido BOOLEAN NOT NULL DEFAULT FALSE,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_import_erro_lote
    ON tbl_importacao_erro(id_importacao_lote, criado_em);

-- ---------------------------------------------------------------------------
-- Rastreio nos produtos
-- ---------------------------------------------------------------------------
ALTER TABLE tbl_produto ADD COLUMN IF NOT EXISTS origem VARCHAR(20) NOT NULL DEFAULT 'manual';
ALTER TABLE tbl_produto DROP CONSTRAINT IF EXISTS tbl_produto_origem_check;
ALTER TABLE tbl_produto ADD CONSTRAINT tbl_produto_origem_check
    CHECK (origem IN ('manual', 'arquivo', 'integracao', 'editado'));

ALTER TABLE tbl_produto ADD COLUMN IF NOT EXISTS id_importacao_lote INTEGER
    REFERENCES tbl_importacao_lote(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_produto_importacao_lote
    ON tbl_produto(id_importacao_lote) WHERE id_importacao_lote IS NOT NULL;

-- ---------------------------------------------------------------------------
-- Menu Importação (fornecedor)
-- ---------------------------------------------------------------------------
INSERT INTO tbl_menu (
    nome_menu, descricao, data_page, icone, tipo_abrir, ordem, parent_id, pai, status, obs,
    id_modulo, nav_codigo, contexto_modulo
)
SELECT
    'Importacao', 'Importar catalogo por arquivo ou integracao', '/fornecedor/importacao',
    'upload', 'Mesma Janela', 31, NULL, TRUE, TRUE, NULL,
    (SELECT id FROM tbl_menu_modulo WHERE modulo = 'Operacional' LIMIT 1),
    'fn_importacao', 'fornecedor'
WHERE NOT EXISTS (SELECT 1 FROM tbl_menu WHERE nav_codigo = 'fn_importacao');

UPDATE tbl_menu SET
    nome_menu = 'Importacao',
    descricao = 'Importar catalogo por arquivo ou integracao',
    data_page = '/fornecedor/importacao',
    icone = 'upload',
    tipo_abrir = 'Mesma Janela',
    ordem = 31,
    status = FALSE,
    obs = 'Abrir via Catalogos > Importar (modal)',
    id_modulo = (SELECT id FROM tbl_menu_modulo WHERE modulo = 'Operacional' LIMIT 1),
    contexto_modulo = 'fornecedor'
WHERE nav_codigo = 'fn_importacao';

INSERT INTO tbl_permissao (codigo, modulo, descricao) VALUES
    ('fn_importacao.ver', 'fn_importacao', 'Ver painel de importacao'),
    ('fn_importacao.editar', 'fn_importacao', 'Executar e excluir importacoes')
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO tbl_perfil_permissao (id_perfil, id_permissao)
SELECT p.id, m.id
FROM tbl_perfil p
CROSS JOIN tbl_permissao m
WHERE p.codigo IN ('dono', 'admin')
  AND m.codigo IN ('fn_importacao.ver', 'fn_importacao.editar')
ON CONFLICT DO NOTHING;

INSERT INTO tbl_perfil_permissao (id_perfil, id_permissao)
SELECT p.id, m.id
FROM tbl_perfil p
CROSS JOIN tbl_permissao m
WHERE p.codigo = 'operacional'
  AND m.codigo IN ('fn_importacao.ver', 'fn_importacao.editar')
ON CONFLICT DO NOTHING;

INSERT INTO tbl_perfil_menu (id_perfil, id_menu, exibir)
SELECT p.id, m.id, TRUE
FROM tbl_perfil p
CROSS JOIN tbl_menu m
WHERE p.codigo IN ('dono', 'admin', 'operacional')
  AND m.nav_codigo = 'fn_importacao'
ON CONFLICT DO NOTHING;
