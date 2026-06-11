-- DropNexo — perfis e permissões (seed)
-- Ordem fixa: dono = id 1 (usado em validações)

INSERT INTO tbl_perfil (codigo, nome, descricao, nivel, eh_sistema) VALUES
    ('dono', 'Dono da conta', 'Acesso total à conta do tenant.', 100, TRUE),
    ('admin', 'Administrador', 'Gestão operacional completa, exceto troca de titularidade.', 80, TRUE),
    ('financeiro', 'Financeiro', 'Financeiro, relatórios e configurações de cobrança.', 60, TRUE),
    ('vendedor', 'Vendedor', 'Busca de produtos, catálogos e operação comercial.', 50, TRUE),
    ('operador', 'Operador', 'Cadastro e manutenção de catálogos e produtos.', 40, TRUE),
    ('visualizador', 'Visualizador', 'Somente leitura nos módulos liberados.', 10, TRUE)
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO tbl_permissao (codigo, modulo, descricao) VALUES
    ('dashboard.ver', 'dashboard', 'Ver painel inicial'),
    ('fornecedores.ver', 'fornecedores', 'Ver fornecedores'),
    ('fornecedores.editar', 'fornecedores', 'Editar fornecedores'),
    ('catalogos.ver', 'catalogos', 'Ver catálogos'),
    ('catalogos.editar', 'catalogos', 'Editar catálogos'),
    ('produtos.ver', 'produtos', 'Ver meus produtos'),
    ('produtos.editar', 'produtos', 'Editar meus produtos'),
    ('integracoes.ver', 'integracoes', 'Ver integrações'),
    ('integracoes.editar', 'integracoes', 'Configurar integrações'),
    ('financeiro.ver', 'financeiro', 'Ver módulo financeiro'),
    ('financeiro.editar', 'financeiro', 'Editar módulo financeiro'),
    ('configuracoes.ver', 'configuracoes', 'Ver configurações'),
    ('configuracoes.editar', 'configuracoes', 'Editar configurações'),
    ('usuarios.ver', 'usuarios', 'Ver equipe e convites'),
    ('usuarios.editar', 'usuarios', 'Gerenciar equipe e perfis'),
    ('planos.ver', 'planos', 'Ver plano e assinatura'),
    ('planos.editar', 'planos', 'Alterar plano e pagamento'),
    ('plataforma.dev', 'plataforma', 'Ferramentas exclusivas de desenvolvedor')
ON CONFLICT (codigo) DO NOTHING;

-- Dono: tudo do tenant (sem plataforma.dev — isso é eh_desenvolvedor)
INSERT INTO tbl_perfil_permissao (id_perfil, id_permissao)
SELECT p.id, m.id
FROM tbl_perfil p
CROSS JOIN tbl_permissao m
WHERE p.codigo = 'dono' AND m.codigo <> 'plataforma.dev'
ON CONFLICT DO NOTHING;

-- Admin
INSERT INTO tbl_perfil_permissao (id_perfil, id_permissao)
SELECT p.id, m.id FROM tbl_perfil p
JOIN tbl_permissao m ON m.codigo IN (
    'dashboard.ver','fornecedores.ver','fornecedores.editar',
    'catalogos.ver','catalogos.editar','produtos.ver','produtos.editar',
    'integracoes.ver','integracoes.editar','financeiro.ver',
    'configuracoes.ver','configuracoes.editar',
    'usuarios.ver','usuarios.editar','planos.ver'
) WHERE p.codigo = 'admin'
ON CONFLICT DO NOTHING;

-- Financeiro
INSERT INTO tbl_perfil_permissao (id_perfil, id_permissao)
SELECT p.id, m.id FROM tbl_perfil p
JOIN tbl_permissao m ON m.codigo IN (
    'dashboard.ver','financeiro.ver','financeiro.editar',
    'configuracoes.ver','planos.ver'
) WHERE p.codigo = 'financeiro'
ON CONFLICT DO NOTHING;

-- Vendedor (perfil de equipe — não confundir com tipo_negocio do tenant)
INSERT INTO tbl_perfil_permissao (id_perfil, id_permissao)
SELECT p.id, m.id FROM tbl_perfil p
JOIN tbl_permissao m ON m.codigo IN (
    'dashboard.ver','fornecedores.ver','catalogos.ver','produtos.ver','produtos.editar'
) WHERE p.codigo = 'vendedor'
ON CONFLICT DO NOTHING;

-- Operador
INSERT INTO tbl_perfil_permissao (id_perfil, id_permissao)
SELECT p.id, m.id FROM tbl_perfil p
JOIN tbl_permissao m ON m.codigo IN (
    'dashboard.ver','catalogos.ver','catalogos.editar','produtos.ver','produtos.editar'
) WHERE p.codigo = 'operador'
ON CONFLICT DO NOTHING;

-- Visualizador
INSERT INTO tbl_perfil_permissao (id_perfil, id_permissao)
SELECT p.id, m.id FROM tbl_perfil p
JOIN tbl_permissao m ON m.codigo LIKE '%.ver'
WHERE p.codigo = 'visualizador'
ON CONFLICT DO NOTHING;
