-- DropNexo — sync tbl_menu DEV -> PROD (17 registros)
-- Chave: nav_codigo | Requer tbl_menu_modulo (003_menu_sistema.sql)
-- Executar em bd_dropnexo produção (faça backup antes)

BEGIN;

-- inicio
INSERT INTO tbl_menu (nome_menu, descricao, data_page, icone, tipo_abrir, ordem, parent_id, pai, status, obs, id_modulo, nav_codigo, contexto_modulo)
SELECT 'Dashboard', 'Painel inicial', '/index', 'layout-dashboard', 'Mesma Janela', 5, NULL, TRUE, TRUE, NULL,
       (SELECT id FROM tbl_menu_modulo WHERE modulo = 'Operacional' LIMIT 1), 'inicio', 'comum'
WHERE NOT EXISTS (SELECT 1 FROM tbl_menu WHERE nav_codigo = 'inicio');
UPDATE tbl_menu SET nome_menu = 'Dashboard', descricao = 'Painel inicial', data_page = '/index', icone = 'layout-dashboard',
    tipo_abrir = 'Mesma Janela', ordem = 5, parent_id = NULL, pai = TRUE, status = TRUE, obs = NULL,
    id_modulo = (SELECT id FROM tbl_menu_modulo WHERE modulo = 'Operacional' LIMIT 1), contexto_modulo = 'comum'
WHERE nav_codigo = 'inicio';

-- fn_depositos
INSERT INTO tbl_menu (nome_menu, descricao, data_page, icone, tipo_abrir, ordem, parent_id, pai, status, obs, id_modulo, nav_codigo, contexto_modulo)
SELECT 'Depósitos', 'Filiais de expedição', '/fornecedor/depositos', 'map-pin', 'Mesma Janela', 15, NULL, TRUE, TRUE, NULL, NULL, 'fn_depositos', 'fornecedor'
WHERE NOT EXISTS (SELECT 1 FROM tbl_menu WHERE nav_codigo = 'fn_depositos');
UPDATE tbl_menu SET nome_menu = 'Depósitos', descricao = 'Filiais de expedição', data_page = '/fornecedor/depositos', icone = 'map-pin',
    tipo_abrir = 'Mesma Janela', ordem = 15, parent_id = NULL, pai = TRUE, status = TRUE, obs = NULL, id_modulo = NULL, contexto_modulo = 'fornecedor'
WHERE nav_codigo = 'fn_depositos';

-- fn_segmentos
INSERT INTO tbl_menu (nome_menu, descricao, data_page, icone, tipo_abrir, ordem, parent_id, pai, status, obs, id_modulo, nav_codigo, contexto_modulo)
SELECT 'Segmentos', 'Nichos e categorias', '/fornecedor/segmentos', 'layers', 'Mesma Janela', 20, NULL, TRUE, TRUE, NULL, NULL, 'fn_segmentos', 'fornecedor'
WHERE NOT EXISTS (SELECT 1 FROM tbl_menu WHERE nav_codigo = 'fn_segmentos');
UPDATE tbl_menu SET nome_menu = 'Segmentos', descricao = 'Nichos e categorias', data_page = '/fornecedor/segmentos', icone = 'layers',
    tipo_abrir = 'Mesma Janela', ordem = 20, parent_id = NULL, pai = TRUE, status = TRUE, obs = NULL, id_modulo = NULL, contexto_modulo = 'fornecedor'
WHERE nav_codigo = 'fn_segmentos';

-- fn_categorias
INSERT INTO tbl_menu (nome_menu, descricao, data_page, icone, tipo_abrir, ordem, parent_id, pai, status, obs, id_modulo, nav_codigo, contexto_modulo)
SELECT 'Categorias', 'Árvore de categorias por segmento', '/fornecedor/categorias', 'folder', 'Mesma Janela', 22, NULL, TRUE, TRUE, NULL, NULL, 'fn_categorias', 'fornecedor'
WHERE NOT EXISTS (SELECT 1 FROM tbl_menu WHERE nav_codigo = 'fn_categorias');
UPDATE tbl_menu SET nome_menu = 'Categorias', descricao = 'Árvore de categorias por segmento', data_page = '/fornecedor/categorias', icone = 'folder',
    tipo_abrir = 'Mesma Janela', ordem = 22, parent_id = NULL, pai = TRUE, status = TRUE, obs = NULL, id_modulo = NULL, contexto_modulo = 'fornecedor'
WHERE nav_codigo = 'fn_categorias';

-- fn_variacoes
INSERT INTO tbl_menu (nome_menu, descricao, data_page, icone, tipo_abrir, ordem, parent_id, pai, status, obs, id_modulo, nav_codigo, contexto_modulo)
SELECT 'Variações', 'Modelos de atributos para produtos', '/fornecedor/variacoes', 'git-branch', 'Mesma Janela', 23, NULL, TRUE, TRUE, NULL, NULL, 'fn_variacoes', 'fornecedor'
WHERE NOT EXISTS (SELECT 1 FROM tbl_menu WHERE nav_codigo = 'fn_variacoes');
UPDATE tbl_menu SET nome_menu = 'Variações', descricao = 'Modelos de atributos para produtos', data_page = '/fornecedor/variacoes', icone = 'git-branch',
    tipo_abrir = 'Mesma Janela', ordem = 23, parent_id = NULL, pai = TRUE, status = TRUE, obs = NULL, id_modulo = NULL, contexto_modulo = 'fornecedor'
WHERE nav_codigo = 'fn_variacoes';

-- fornecedores (vendedor)
INSERT INTO tbl_menu (nome_menu, descricao, data_page, icone, tipo_abrir, ordem, parent_id, pai, status, obs, id_modulo, nav_codigo, contexto_modulo)
SELECT 'Fornecedores', 'Rede de fornecedores', '/fornecedores', 'users', 'Mesma Janela', 25, NULL, TRUE, TRUE, NULL,
       (SELECT id FROM tbl_menu_modulo WHERE modulo = 'Operacional' LIMIT 1), 'fornecedores', 'vendedor'
WHERE NOT EXISTS (SELECT 1 FROM tbl_menu WHERE nav_codigo = 'fornecedores');
UPDATE tbl_menu SET nome_menu = 'Fornecedores', descricao = 'Rede de fornecedores', data_page = '/fornecedores', icone = 'users',
    tipo_abrir = 'Mesma Janela', ordem = 25, parent_id = NULL, pai = TRUE, status = TRUE, obs = NULL,
    id_modulo = (SELECT id FROM tbl_menu_modulo WHERE modulo = 'Operacional' LIMIT 1), contexto_modulo = 'vendedor'
WHERE nav_codigo = 'fornecedores';

-- catalogos (fornecedor)
INSERT INTO tbl_menu (nome_menu, descricao, data_page, icone, tipo_abrir, ordem, parent_id, pai, status, obs, id_modulo, nav_codigo, contexto_modulo)
SELECT 'Catálogos', 'Gestão de catálogos', '/catalogos', 'package', 'Mesma Janela', 30, NULL, TRUE, TRUE, NULL,
       (SELECT id FROM tbl_menu_modulo WHERE modulo = 'Operacional' LIMIT 1), 'catalogos', 'fornecedor'
WHERE NOT EXISTS (SELECT 1 FROM tbl_menu WHERE nav_codigo = 'catalogos');
UPDATE tbl_menu SET nome_menu = 'Catálogos', descricao = 'Gestão de catálogos', data_page = '/catalogos', icone = 'package',
    tipo_abrir = 'Mesma Janela', ordem = 30, parent_id = NULL, pai = TRUE, status = TRUE, obs = NULL,
    id_modulo = (SELECT id FROM tbl_menu_modulo WHERE modulo = 'Operacional' LIMIT 1), contexto_modulo = 'fornecedor'
WHERE nav_codigo = 'catalogos';

-- vd_catalogo
INSERT INTO tbl_menu (nome_menu, descricao, data_page, icone, tipo_abrir, ordem, parent_id, pai, status, obs, id_modulo, nav_codigo, contexto_modulo)
SELECT 'Catálogo', 'Produtos dos fornecedores aprovados', '/vendedor/catalogo', 'package', 'Mesma Janela', 30, NULL, TRUE, TRUE, NULL, NULL, 'vd_catalogo', 'vendedor'
WHERE NOT EXISTS (SELECT 1 FROM tbl_menu WHERE nav_codigo = 'vd_catalogo');
UPDATE tbl_menu SET nome_menu = 'Catálogo', descricao = 'Produtos dos fornecedores aprovados', data_page = '/vendedor/catalogo', icone = 'package',
    tipo_abrir = 'Mesma Janela', ordem = 30, parent_id = NULL, pai = TRUE, status = TRUE, obs = NULL, id_modulo = NULL, contexto_modulo = 'vendedor'
WHERE nav_codigo = 'vd_catalogo';

-- produtos (vendedor)
INSERT INTO tbl_menu (nome_menu, descricao, data_page, icone, tipo_abrir, ordem, parent_id, pai, status, obs, id_modulo, nav_codigo, contexto_modulo)
SELECT 'Meus produtos', 'Produtos do vendedor', '/meus-produtos', 'shopping-bag', 'Mesma Janela', 35, NULL, TRUE, TRUE, NULL,
       (SELECT id FROM tbl_menu_modulo WHERE modulo = 'Operacional' LIMIT 1), 'produtos', 'vendedor'
WHERE NOT EXISTS (SELECT 1 FROM tbl_menu WHERE nav_codigo = 'produtos');
UPDATE tbl_menu SET nome_menu = 'Meus produtos', descricao = 'Produtos do vendedor', data_page = '/meus-produtos', icone = 'shopping-bag',
    tipo_abrir = 'Mesma Janela', ordem = 35, parent_id = NULL, pai = TRUE, status = TRUE, obs = NULL,
    id_modulo = (SELECT id FROM tbl_menu_modulo WHERE modulo = 'Operacional' LIMIT 1), contexto_modulo = 'vendedor'
WHERE nav_codigo = 'produtos';

-- vd_precificacao
INSERT INTO tbl_menu (nome_menu, descricao, data_page, icone, tipo_abrir, ordem, parent_id, pai, status, obs, id_modulo, nav_codigo, contexto_modulo)
SELECT 'Precificação', 'Margens e preços de venda', '/vendedor/precificacao', 'percent', 'Mesma Janela', 45, NULL, TRUE, TRUE, NULL, NULL, 'vd_precificacao', 'vendedor'
WHERE NOT EXISTS (SELECT 1 FROM tbl_menu WHERE nav_codigo = 'vd_precificacao');
UPDATE tbl_menu SET nome_menu = 'Precificação', descricao = 'Margens e preços de venda', data_page = '/vendedor/precificacao', icone = 'percent',
    tipo_abrir = 'Mesma Janela', ordem = 45, parent_id = NULL, pai = TRUE, status = TRUE, obs = NULL, id_modulo = NULL, contexto_modulo = 'vendedor'
WHERE nav_codigo = 'vd_precificacao';

-- vd_pedidos
INSERT INTO tbl_menu (nome_menu, descricao, data_page, icone, tipo_abrir, ordem, parent_id, pai, status, obs, id_modulo, nav_codigo, contexto_modulo)
SELECT 'Pedidos', 'Pedidos (em breve)', '/vendedor/pedidos', 'clipboard-list', 'Mesma Janela', 50, NULL, TRUE, TRUE, NULL, NULL, 'vd_pedidos', 'vendedor'
WHERE NOT EXISTS (SELECT 1 FROM tbl_menu WHERE nav_codigo = 'vd_pedidos');
UPDATE tbl_menu SET nome_menu = 'Pedidos', descricao = 'Pedidos (em breve)', data_page = '/vendedor/pedidos', icone = 'clipboard-list',
    tipo_abrir = 'Mesma Janela', ordem = 50, parent_id = NULL, pai = TRUE, status = TRUE, obs = NULL, id_modulo = NULL, contexto_modulo = 'vendedor'
WHERE nav_codigo = 'vd_pedidos';

-- fn_vendedores
INSERT INTO tbl_menu (nome_menu, descricao, data_page, icone, tipo_abrir, ordem, parent_id, pai, status, obs, id_modulo, nav_codigo, contexto_modulo)
SELECT 'Vendedores', 'Parceiros e aprovações', '/fornecedor/vendedores', 'users', 'Mesma Janela', 55, NULL, TRUE, TRUE, NULL, NULL, 'fn_vendedores', 'fornecedor'
WHERE NOT EXISTS (SELECT 1 FROM tbl_menu WHERE nav_codigo = 'fn_vendedores');
UPDATE tbl_menu SET nome_menu = 'Vendedores', descricao = 'Parceiros e aprovações', data_page = '/fornecedor/vendedores', icone = 'users',
    tipo_abrir = 'Mesma Janela', ordem = 55, parent_id = NULL, pai = TRUE, status = TRUE, obs = NULL, id_modulo = NULL, contexto_modulo = 'fornecedor'
WHERE nav_codigo = 'fn_vendedores';

-- vd_expedicao
INSERT INTO tbl_menu (nome_menu, descricao, data_page, icone, tipo_abrir, ordem, parent_id, pai, status, obs, id_modulo, nav_codigo, contexto_modulo)
SELECT 'Expedição', 'Entrega ao cliente final', '/vendedor/expedicao', 'truck', 'Mesma Janela', 55, NULL, TRUE, TRUE, NULL, NULL, 'vd_expedicao', 'vendedor'
WHERE NOT EXISTS (SELECT 1 FROM tbl_menu WHERE nav_codigo = 'vd_expedicao');
UPDATE tbl_menu SET nome_menu = 'Expedição', descricao = 'Entrega ao cliente final', data_page = '/vendedor/expedicao', icone = 'truck',
    tipo_abrir = 'Mesma Janela', ordem = 55, parent_id = NULL, pai = TRUE, status = TRUE, obs = NULL, id_modulo = NULL, contexto_modulo = 'vendedor'
WHERE nav_codigo = 'vd_expedicao';

-- fn_usuarios
INSERT INTO tbl_menu (nome_menu, descricao, data_page, icone, tipo_abrir, ordem, parent_id, pai, status, obs, id_modulo, nav_codigo, contexto_modulo)
SELECT 'Usuários', 'Equipe e convites de acesso', '/fornecedor/usuarios', 'user-plus', 'Mesma Janela', 62, NULL, TRUE, TRUE, NULL, NULL, 'fn_usuarios', 'fornecedor'
WHERE NOT EXISTS (SELECT 1 FROM tbl_menu WHERE nav_codigo = 'fn_usuarios');
UPDATE tbl_menu SET nome_menu = 'Usuários', descricao = 'Equipe e convites de acesso', data_page = '/fornecedor/usuarios', icone = 'user-plus',
    tipo_abrir = 'Mesma Janela', ordem = 62, parent_id = NULL, pai = TRUE, status = TRUE, obs = NULL, id_modulo = NULL, contexto_modulo = 'fornecedor'
WHERE nav_codigo = 'fn_usuarios';

-- vd_usuarios
INSERT INTO tbl_menu (nome_menu, descricao, data_page, icone, tipo_abrir, ordem, parent_id, pai, status, obs, id_modulo, nav_codigo, contexto_modulo)
SELECT 'Usuários', 'Equipe e convites de acesso', '/vendedor/usuarios', 'user-plus', 'Mesma Janela', 62, NULL, TRUE, TRUE, NULL, NULL, 'vd_usuarios', 'vendedor'
WHERE NOT EXISTS (SELECT 1 FROM tbl_menu WHERE nav_codigo = 'vd_usuarios');
UPDATE tbl_menu SET nome_menu = 'Usuários', descricao = 'Equipe e convites de acesso', data_page = '/vendedor/usuarios', icone = 'user-plus',
    tipo_abrir = 'Mesma Janela', ordem = 62, parent_id = NULL, pai = TRUE, status = TRUE, obs = NULL, id_modulo = NULL, contexto_modulo = 'vendedor'
WHERE nav_codigo = 'vd_usuarios';

-- integracoes (vendedor)
INSERT INTO tbl_menu (nome_menu, descricao, data_page, icone, tipo_abrir, ordem, parent_id, pai, status, obs, id_modulo, nav_codigo, contexto_modulo)
SELECT 'Integrações', 'Marketplaces, e-commerce, frete e ERP', '/integracoes', 'plug', 'Mesma Janela', 70, NULL, TRUE, TRUE, NULL,
       (SELECT id FROM tbl_menu_modulo WHERE modulo = 'Operacional' LIMIT 1), 'integracoes', 'vendedor'
WHERE NOT EXISTS (SELECT 1 FROM tbl_menu WHERE nav_codigo = 'integracoes');
UPDATE tbl_menu SET nome_menu = 'Integrações', descricao = 'Marketplaces, e-commerce, frete e ERP', data_page = '/integracoes', icone = 'plug',
    tipo_abrir = 'Mesma Janela', ordem = 70, parent_id = NULL, pai = TRUE, status = TRUE, obs = NULL,
    id_modulo = (SELECT id FROM tbl_menu_modulo WHERE modulo = 'Operacional' LIMIT 1), contexto_modulo = 'vendedor'
WHERE nav_codigo = 'integracoes';

-- fn_integracoes (fornecedor)
INSERT INTO tbl_menu (nome_menu, descricao, data_page, icone, tipo_abrir, ordem, parent_id, pai, status, obs, id_modulo, nav_codigo, contexto_modulo)
SELECT 'Integrações', 'Marketplaces, e-commerce, frete e ERP', '/fornecedor/integracoes', 'plug', 'Mesma Janela', 70, NULL, TRUE, TRUE, NULL, NULL, 'fn_integracoes', 'fornecedor'
WHERE NOT EXISTS (SELECT 1 FROM tbl_menu WHERE nav_codigo = 'fn_integracoes');
UPDATE tbl_menu SET nome_menu = 'Integrações', descricao = 'Marketplaces, e-commerce, frete e ERP', data_page = '/fornecedor/integracoes', icone = 'plug',
    tipo_abrir = 'Mesma Janela', ordem = 70, parent_id = NULL, pai = TRUE, status = TRUE, obs = NULL, id_modulo = NULL, contexto_modulo = 'fornecedor'
WHERE nav_codigo = 'fn_integracoes';

COMMIT;
