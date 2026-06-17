-- DropNexo — PRODUÇÃO: alinhar schema para importação Bling (027 → 037)
-- Seguro para rodar mais de uma vez (IF NOT EXISTS / ON CONFLICT DO NOTHING).
--
-- No psql:
--   \i '/caminho/para/DROPNEXO/__doc/sql/039_producao_importacao_bling.sql'
--
-- Ou:
--   psql -U postgres -d bd_dropnexo -f __doc/sql/039_producao_importacao_bling.sql

BEGIN;

-- ===========================================================================
-- 027 — motor de importação (lotes, erros, rastreio em produtos)
-- ===========================================================================
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

ALTER TABLE tbl_produto ADD COLUMN IF NOT EXISTS origem VARCHAR(20) NOT NULL DEFAULT 'manual';
ALTER TABLE tbl_produto DROP CONSTRAINT IF EXISTS tbl_produto_origem_check;
ALTER TABLE tbl_produto ADD CONSTRAINT tbl_produto_origem_check
    CHECK (origem IN ('manual', 'arquivo', 'integracao', 'editado'));

ALTER TABLE tbl_produto ADD COLUMN IF NOT EXISTS id_importacao_lote INTEGER
    REFERENCES tbl_importacao_lote(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_produto_importacao_lote
    ON tbl_produto(id_importacao_lote) WHERE id_importacao_lote IS NOT NULL;

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
WHERE p.codigo IN ('dono', 'admin', 'operacional')
  AND m.codigo IN ('fn_importacao.ver', 'fn_importacao.editar')
ON CONFLICT DO NOTHING;

INSERT INTO tbl_perfil_menu (id_perfil, id_menu, exibir)
SELECT p.id, m.id, TRUE
FROM tbl_perfil p
CROSS JOIN tbl_menu m
WHERE p.codigo IN ('dono', 'admin', 'operacional')
  AND m.nav_codigo = 'fn_importacao'
ON CONFLICT DO NOTHING;

-- ===========================================================================
-- 028 — menu importação oculto (abre via modal no catálogo)
-- ===========================================================================
UPDATE tbl_menu SET status = FALSE, obs = 'Abrir via Catalogos > Importar (modal)'
WHERE nav_codigo = 'fn_importacao';

-- ===========================================================================
-- 029 — opções Bling (estoque, polling)
-- ===========================================================================
ALTER TABLE tbl_integracao_bling_config
    ADD COLUMN IF NOT EXISTS opcoes JSONB NOT NULL DEFAULT '{}';

-- ===========================================================================
-- 030 — campos produto / valor_drop (usados na importação Bling)
-- ===========================================================================
ALTER TABLE tbl_produto ADD COLUMN IF NOT EXISTS valor_drop NUMERIC(12, 2);
ALTER TABLE tbl_produto ADD COLUMN IF NOT EXISTS condicao VARCHAR(32);
ALTER TABLE tbl_produto ADD COLUMN IF NOT EXISTS origem_fiscal VARCHAR(4);
ALTER TABLE tbl_produto ADD COLUMN IF NOT EXISTS cest VARCHAR(10);
ALTER TABLE tbl_produto ADD COLUMN IF NOT EXISTS frete_gratis BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE tbl_produto ADD COLUMN IF NOT EXISTS volumes INTEGER;
ALTER TABLE tbl_produto ADD COLUMN IF NOT EXISTS producao VARCHAR(20);
ALTER TABLE tbl_produto ADD COLUMN IF NOT EXISTS preco_custo_origem NUMERIC(12, 2);

UPDATE tbl_produto
SET valor_drop = COALESCE(valor_drop, valor_dropshipping, preco)
WHERE valor_drop IS NULL;

ALTER TABLE tbl_produto_variante ADD COLUMN IF NOT EXISTS valor_drop NUMERIC(12, 2);

UPDATE tbl_produto_variante v
SET valor_drop = COALESCE(v.valor_drop, v.preco)
FROM tbl_produto p
WHERE p.id = v.id_produto AND v.valor_drop IS NULL;

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

-- ===========================================================================
-- 031 — estoque por depósito (sync Bling)
-- ===========================================================================
CREATE TABLE IF NOT EXISTS tbl_produto_estoque_deposito (
    id SERIAL PRIMARY KEY,
    id_variante INTEGER NOT NULL REFERENCES tbl_produto_variante(id) ON DELETE CASCADE,
    id_deposito INTEGER NOT NULL REFERENCES tbl_deposito_expedicao(id) ON DELETE CASCADE,
    quantidade INTEGER NOT NULL DEFAULT 0 CHECK (quantidade >= 0),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (id_variante, id_deposito)
);

CREATE INDEX IF NOT EXISTS ix_ped_variante ON tbl_produto_estoque_deposito(id_variante);
CREATE INDEX IF NOT EXISTS ix_ped_deposito ON tbl_produto_estoque_deposito(id_deposito);

INSERT INTO tbl_produto_estoque_deposito (id_variante, id_deposito, quantidade, atualizado_em)
SELECT v.id, d.id, COALESCE(e.quantidade, 0), COALESCE(e.atualizado_em, NOW())
FROM tbl_produto_variante v
JOIN tbl_produto p ON p.id = v.id_produto
JOIN tbl_deposito_expedicao d ON d.id_tenant = p.id_tenant AND d.ativo = TRUE
LEFT JOIN tbl_produto_variante_estoque e ON e.id_variante = v.id
WHERE d.principal = TRUE
  AND NOT EXISTS (
      SELECT 1 FROM tbl_produto_estoque_deposito x
      WHERE x.id_variante = v.id AND x.id_deposito = d.id
  );

INSERT INTO tbl_produto_estoque_deposito (id_variante, id_deposito, quantidade, atualizado_em)
SELECT v.id, d.id, COALESCE(e.quantidade, 0), COALESCE(e.atualizado_em, NOW())
FROM tbl_produto_variante v
JOIN tbl_produto p ON p.id = v.id_produto
JOIN LATERAL (
    SELECT id FROM tbl_deposito_expedicao
    WHERE id_tenant = p.id_tenant AND ativo = TRUE
    ORDER BY principal DESC, id
    LIMIT 1
) d ON TRUE
LEFT JOIN tbl_produto_variante_estoque e ON e.id_variante = v.id
WHERE NOT EXISTS (SELECT 1 FROM tbl_produto_estoque_deposito x WHERE x.id_variante = v.id);

-- ===========================================================================
-- 032 / 033 — precificação
-- ===========================================================================
ALTER TABLE tbl_produto ADD COLUMN IF NOT EXISTS valor_drop_manual BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE tbl_tenant ADD COLUMN IF NOT EXISTS precificacao_modo VARCHAR(20) NOT NULL DEFAULT 'global';

UPDATE tbl_tenant SET precificacao_modo = 'global'
WHERE precificacao_modo IS NULL OR precificacao_modo = '';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ck_tenant_precificacao_modo'
    ) THEN
        ALTER TABLE tbl_tenant
            ADD CONSTRAINT ck_tenant_precificacao_modo
            CHECK (precificacao_modo IN ('global', 'categoria'));
    END IF;
END $$;

-- ===========================================================================
-- 034 — galeria / imagens (importação Bling)
-- ===========================================================================
ALTER TABLE tbl_produto
    ADD COLUMN IF NOT EXISTS imagem_modo VARCHAR(10);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'tbl_produto_imagem_modo_check'
    ) THEN
        ALTER TABLE tbl_produto
            ADD CONSTRAINT tbl_produto_imagem_modo_check
            CHECK (imagem_modo IS NULL OR imagem_modo IN ('link', 'upload'));
    END IF;
END $$;

ALTER TABLE tbl_produto_imagem
    ADD COLUMN IF NOT EXISTS origem VARCHAR(20) NOT NULL DEFAULT 'manual_upload';

ALTER TABLE tbl_produto_variante
    ADD COLUMN IF NOT EXISTS id_imagem_principal INTEGER
        REFERENCES tbl_produto_imagem(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_variante_imagem_principal
    ON tbl_produto_variante(id_imagem_principal)
    WHERE id_imagem_principal IS NOT NULL;

CREATE TABLE IF NOT EXISTS tbl_produto_atributo_imagem (
    id SERIAL PRIMARY KEY,
    id_produto INTEGER NOT NULL REFERENCES tbl_produto(id) ON DELETE CASCADE,
    nome_atributo VARCHAR(60) NOT NULL,
    valor VARCHAR(120) NOT NULL,
    id_imagem INTEGER NOT NULL REFERENCES tbl_produto_imagem(id) ON DELETE CASCADE,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (id_produto, nome_atributo, valor)
);

CREATE INDEX IF NOT EXISTS ix_produto_atributo_imagem_produto
    ON tbl_produto_atributo_imagem(id_produto);

-- ===========================================================================
-- 035 — imagens por variante
-- ===========================================================================
CREATE TABLE IF NOT EXISTS tbl_produto_variante_imagem (
    id_variante INTEGER NOT NULL REFERENCES tbl_produto_variante(id) ON DELETE CASCADE,
    id_imagem INTEGER NOT NULL REFERENCES tbl_produto_imagem(id) ON DELETE CASCADE,
    ordem INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (id_variante, id_imagem)
);

CREATE INDEX IF NOT EXISTS ix_variante_imagem_variante
    ON tbl_produto_variante_imagem(id_variante);

CREATE INDEX IF NOT EXISTS ix_variante_imagem_imagem
    ON tbl_produto_variante_imagem(id_imagem);

INSERT INTO tbl_produto_variante_imagem (id_variante, id_imagem, ordem)
SELECT v.id, v.id_imagem_principal, 0
FROM tbl_produto_variante v
WHERE v.id_imagem_principal IS NOT NULL
  AND COALESCE(v.herda_pai, TRUE) = FALSE
ON CONFLICT (id_variante, id_imagem) DO NOTHING;

-- ===========================================================================
-- 036 — descrição por variante
-- ===========================================================================
ALTER TABLE tbl_produto_variante
    ADD COLUMN IF NOT EXISTS descricao TEXT;

-- ===========================================================================
-- 037 — preços promoção variante
-- ===========================================================================
ALTER TABLE tbl_produto_variante
    ADD COLUMN IF NOT EXISTS valor_drop_manual BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE tbl_produto_variante
    ADD COLUMN IF NOT EXISTS promocao_validade DATE;

ALTER TABLE tbl_produto_variante
    ADD COLUMN IF NOT EXISTS promocao_ate_zerar_estoque BOOLEAN NOT NULL DEFAULT FALSE;

COMMIT;

-- Verificação rápida (deve listar todas as tabelas/colunas críticas)
SELECT 'tbl_importacao_lote' AS item, to_regclass('public.tbl_importacao_lote')::text AS ok
UNION ALL SELECT 'tbl_importacao_erro', to_regclass('public.tbl_importacao_erro')::text
UNION ALL SELECT 'tbl_produto.id_importacao_lote', (
    SELECT CASE WHEN EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'tbl_produto' AND column_name = 'id_importacao_lote'
    ) THEN 'ok' ELSE 'FALTA' END
)
UNION ALL SELECT 'tbl_produto_estoque_deposito', to_regclass('public.tbl_produto_estoque_deposito')::text
UNION ALL SELECT 'tbl_produto_variante.descricao', (
    SELECT CASE WHEN EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'tbl_produto_variante' AND column_name = 'descricao'
    ) THEN 'ok' ELSE 'FALTA' END
)
UNION ALL SELECT 'tbl_integracao_bling_config.opcoes', (
    SELECT CASE WHEN EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'tbl_integracao_bling_config' AND column_name = 'opcoes'
    ) THEN 'ok' ELSE 'FALTA' END
);
