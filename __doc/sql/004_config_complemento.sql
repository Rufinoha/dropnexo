-- DropNexo — complemento config: novidades lidas + menu Configurações + seeds

ALTER TABLE tbl_usuario
    ADD COLUMN IF NOT EXISTS id_ultima_novidade_lida INTEGER NOT NULL DEFAULT 0;

-- Menu Configurações na sidebar (admins / quem tiver perfil_menu)
INSERT INTO tbl_menu (nome_menu, descricao, data_page, icone, ordem, pai, status, id_modulo, nav_codigo)
SELECT 'Configurações', 'Painel de configurações do tenant', '/configuracoes', 'settings', 95, TRUE, TRUE, mm.id, 'config'
FROM tbl_menu_modulo mm
WHERE mm.modulo = 'Configuração'
  AND NOT EXISTS (SELECT 1 FROM tbl_menu m WHERE m.nav_codigo = 'config');

INSERT INTO tbl_perfil_menu (id_perfil, id_menu, exibir)
SELECT p.id, m.id, TRUE
FROM tbl_perfil p
JOIN tbl_menu m ON m.nav_codigo = 'config' AND m.status = TRUE
WHERE p.codigo IN ('dono', 'admin')
ON CONFLICT DO NOTHING;

INSERT INTO tbl_novidade (titulo, resumo, conteudo, ordem, ativo)
SELECT v.titulo, v.resumo, v.conteudo, v.ord, TRUE
FROM (VALUES
    ('Bem-vindo ao DropNexo', 'Sua conta está pronta para conectar fornecedores e vendedores.', 'Explore o painel, configure sua equipe em Configurações e publique seu primeiro catálogo em breve.', 10),
    ('Menu dinâmico', 'Os itens da barra lateral agora vêm do banco de dados.', 'Administradores podem ajustar menus por perfil em Configurações → Itens de menu.', 20)
) AS v(titulo, resumo, conteudo, ord)
WHERE NOT EXISTS (SELECT 1 FROM tbl_novidade LIMIT 1);
