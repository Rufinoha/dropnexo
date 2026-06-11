-- DropNexo — modelos de variação pré-cadastrados (fornecedor)

CREATE TABLE IF NOT EXISTS tbl_variacao_preset (
    id SERIAL PRIMARY KEY,
    id_tenant INTEGER NOT NULL REFERENCES tbl_tenant(id) ON DELETE CASCADE,
    nome VARCHAR(120) NOT NULL,
    descricao TEXT,
    atributos JSONB NOT NULL DEFAULT '[]',
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_variacao_preset_tenant_nome
    ON tbl_variacao_preset (id_tenant, LOWER(nome));

CREATE INDEX IF NOT EXISTS ix_variacao_preset_tenant ON tbl_variacao_preset(id_tenant);

-- Menu Variações (fornecedor)
INSERT INTO tbl_menu (nome_menu, descricao, data_page, icone, ordem, pai, status, nav_codigo, contexto_modulo)
SELECT v.nome, v.descricao, v.page, v.ico, v.ord, TRUE, TRUE, v.nav, v.ctx
FROM (VALUES
    ('Variações', 'Modelos de atributos para produtos', '/fornecedor/variacoes', 'git-branch', 23, 'fn_variacoes', 'fornecedor')
) AS v(nome, descricao, page, ico, ord, nav, ctx)
WHERE NOT EXISTS (SELECT 1 FROM tbl_menu m WHERE m.nav_codigo = v.nav);

INSERT INTO tbl_permissao (codigo, modulo, descricao) VALUES
    ('fn_variacoes.ver', 'fn_variacoes', 'Ver modelos de variação'),
    ('fn_variacoes.editar', 'fn_variacoes', 'Editar modelos de variação')
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO tbl_perfil_permissao (id_perfil, id_permissao)
SELECT p.id, m.id
FROM tbl_perfil p
CROSS JOIN tbl_permissao m
WHERE p.codigo IN ('dono', 'admin')
  AND m.codigo IN ('fn_variacoes.ver', 'fn_variacoes.editar')
ON CONFLICT DO NOTHING;

INSERT INTO tbl_perfil_menu (id_perfil, id_menu, exibir)
SELECT p.id, m.id, TRUE
FROM tbl_perfil p
CROSS JOIN tbl_menu m
WHERE m.status = TRUE
  AND p.codigo IN ('dono', 'admin')
  AND m.nav_codigo = 'fn_variacoes'
ON CONFLICT DO NOTHING;
