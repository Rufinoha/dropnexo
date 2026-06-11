-- DropNexo — Usuários no Vendedor + Integrações compartilhada + ordem do menu

-- Vendedor: menu Usuários
INSERT INTO tbl_menu (nome_menu, descricao, data_page, icone, ordem, pai, status, nav_codigo, contexto_modulo)
SELECT v.nome, v.descricao, v.page, v.ico, v.ord, TRUE, TRUE, v.nav, v.ctx
FROM (VALUES
    ('Usuários', 'Equipe e convites de acesso', '/vendedor/usuarios', 'user-plus', 62, 'vd_usuarios', 'vendedor')
) AS v(nome, descricao, page, ico, ord, nav, ctx)
WHERE NOT EXISTS (SELECT 1 FROM tbl_menu m WHERE m.nav_codigo = v.nav);

INSERT INTO tbl_permissao (codigo, modulo, descricao) VALUES
    ('vd_usuarios.ver', 'vd_usuarios', 'Ver equipe do vendedor'),
    ('vd_usuarios.editar', 'vd_usuarios', 'Gerenciar equipe e convites do vendedor')
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO tbl_perfil_permissao (id_perfil, id_permissao)
SELECT p.id, m.id
FROM tbl_perfil p
CROSS JOIN tbl_permissao m
WHERE p.codigo IN ('dono', 'admin')
  AND m.codigo IN ('vd_usuarios.ver', 'vd_usuarios.editar')
ON CONFLICT DO NOTHING;

INSERT INTO tbl_perfil_menu (id_perfil, id_menu, exibir)
SELECT p.id, m.id, TRUE
FROM tbl_perfil p
CROSS JOIN tbl_menu m
WHERE m.status = TRUE
  AND p.codigo IN ('dono', 'admin')
  AND m.nav_codigo = 'vd_usuarios'
ON CONFLICT DO NOTHING;

-- Integrações: mesma tela (/integracoes) no módulo vendedor — por último
UPDATE tbl_menu
SET contexto_modulo = 'vendedor',
    data_page = '/integracoes',
    nome_menu = 'Integrações',
    descricao = 'Marketplaces, e-commerce, frete e ERP',
    ordem = 70
WHERE nav_codigo = 'integracoes';

-- Fornecedor: Usuários e Integrações por último
UPDATE tbl_menu SET ordem = 62 WHERE nav_codigo = 'fn_usuarios';
UPDATE tbl_menu SET ordem = 70 WHERE nav_codigo = 'fn_integracoes';

-- Vendedor: demais itens antes de Usuários/Integrações
UPDATE tbl_menu SET ordem = 25 WHERE nav_codigo = 'fornecedores';
UPDATE tbl_menu SET ordem = 30 WHERE nav_codigo = 'vd_catalogo';
UPDATE tbl_menu SET ordem = 35 WHERE nav_codigo = 'produtos';
UPDATE tbl_menu SET ordem = 45 WHERE nav_codigo = 'vd_precificacao';
UPDATE tbl_menu SET ordem = 50 WHERE nav_codigo = 'vd_pedidos';
UPDATE tbl_menu SET ordem = 55 WHERE nav_codigo = 'vd_expedicao';

-- Fornecedor dono/admin também vê integrações do vendedor (mesma permissão legada)
INSERT INTO tbl_perfil_permissao (id_perfil, id_permissao)
SELECT p.id, m.id
FROM tbl_perfil p
CROSS JOIN tbl_permissao m
WHERE p.codigo IN ('dono', 'admin')
  AND m.codigo IN ('integracoes.ver', 'integracoes.editar')
ON CONFLICT DO NOTHING;
