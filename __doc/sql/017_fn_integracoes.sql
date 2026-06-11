-- DropNexo — integrações do fornecedor (hub estilo marketplace)

INSERT INTO tbl_menu (nome_menu, descricao, data_page, icone, ordem, pai, status, nav_codigo, contexto_modulo)
SELECT v.nome, v.descricao, v.page, v.ico, v.ord, TRUE, TRUE, v.nav, v.ctx
FROM (VALUES
    ('Integrações', 'Marketplaces, e-commerce, frete e ERP', '/fornecedor/integracoes', 'plug', 60, 'fn_integracoes', 'fornecedor')
) AS v(nome, descricao, page, ico, ord, nav, ctx)
WHERE NOT EXISTS (SELECT 1 FROM tbl_menu m WHERE m.nav_codigo = v.nav);

INSERT INTO tbl_permissao (codigo, modulo, descricao) VALUES
    ('fn_integracoes.ver', 'fn_integracoes', 'Ver integrações do fornecedor'),
    ('fn_integracoes.editar', 'fn_integracoes', 'Configurar integrações do fornecedor')
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO tbl_perfil_permissao (id_perfil, id_permissao)
SELECT p.id, m.id
FROM tbl_perfil p
CROSS JOIN tbl_permissao m
WHERE p.codigo IN ('dono', 'admin')
  AND m.codigo IN ('fn_integracoes.ver', 'fn_integracoes.editar')
ON CONFLICT DO NOTHING;

INSERT INTO tbl_perfil_menu (id_perfil, id_menu, exibir)
SELECT p.id, m.id, TRUE
FROM tbl_perfil p
CROSS JOIN tbl_menu m
WHERE m.status = TRUE
  AND p.codigo IN ('dono', 'admin')
  AND m.nav_codigo = 'fn_integracoes'
ON CONFLICT DO NOTHING;
