-- Vendedor: depósitos espelhados do fornecedor + menus Depósitos e Categorias

ALTER TABLE tbl_deposito_expedicao
    ADD COLUMN IF NOT EXISTS id_deposito_espelho INTEGER REFERENCES tbl_deposito_expedicao(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS id_tenant_espelho INTEGER REFERENCES tbl_tenant(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS espelho_somente_leitura BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN tbl_deposito_expedicao.id_deposito_espelho IS
    'Depósito de origem (fornecedor) quando espelhado na conta do vendedor.';
COMMENT ON COLUMN tbl_deposito_expedicao.espelho_somente_leitura IS
    'TRUE = espelho do fornecedor; vendedor não edita endereço, só visualiza.';

CREATE INDEX IF NOT EXISTS ix_deposito_espelho_vendedor
    ON tbl_deposito_expedicao(id_tenant, id_deposito_espelho)
    WHERE id_deposito_espelho IS NOT NULL;

-- Menus vendedor
INSERT INTO tbl_permissao (codigo, modulo, descricao) VALUES
    ('vd_depositos.ver', 'vd_depositos', 'Ver depósitos do vendedor'),
    ('vd_depositos.editar', 'vd_depositos', 'Gerenciar depósitos do vendedor'),
    ('vd_categorias.ver', 'vd_categorias', 'Ver categorias do vendedor'),
    ('vd_categorias.editar', 'vd_categorias', 'Gerenciar categorias do vendedor')
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO tbl_perfil_permissao (id_perfil, id_permissao)
SELECT p.id, m.id
FROM tbl_perfil p
JOIN tbl_permissao m ON m.codigo IN (
    'vd_depositos.ver', 'vd_depositos.editar',
    'vd_categorias.ver', 'vd_categorias.editar'
)
WHERE p.codigo IN ('dono', 'admin', 'vendedor')
ON CONFLICT DO NOTHING;

INSERT INTO tbl_menu (nome_menu, descricao, data_page, icone, ordem, pai, status, nav_codigo, id_modulo, contexto_modulo)
SELECT 'Depósitos', 'Filiais de expedição e espelhos de fornecedores', '/vendedor/depositos', 'map-pin',
       36, TRUE, TRUE, 'vd_depositos', (SELECT id FROM tbl_menu_modulo WHERE modulo = 'Operacional' LIMIT 1), 'vendedor'
WHERE NOT EXISTS (SELECT 1 FROM tbl_menu WHERE nav_codigo = 'vd_depositos');

INSERT INTO tbl_menu (nome_menu, descricao, data_page, icone, ordem, pai, status, nav_codigo, id_modulo, contexto_modulo)
SELECT 'Categorias', 'Árvore de categorias dos seus produtos', '/vendedor/categorias', 'folder',
       37, TRUE, TRUE, 'vd_categorias', (SELECT id FROM tbl_menu_modulo WHERE modulo = 'Operacional' LIMIT 1), 'vendedor'
WHERE NOT EXISTS (SELECT 1 FROM tbl_menu WHERE nav_codigo = 'vd_categorias');

INSERT INTO tbl_perfil_menu (id_perfil, id_menu, exibir)
SELECT p.id, m.id, TRUE
FROM tbl_perfil p
CROSS JOIN tbl_menu m
WHERE m.status = TRUE
  AND p.codigo IN ('dono', 'admin', 'vendedor')
  AND m.nav_codigo IN ('vd_depositos', 'vd_categorias')
ON CONFLICT DO NOTHING;
