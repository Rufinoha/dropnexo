-- DropNexo — módulos, menu dinâmico, perfil×menu, novidades

CREATE TABLE IF NOT EXISTS tbl_menu_modulo (
    id SERIAL PRIMARY KEY,
    modulo VARCHAR(80) NOT NULL UNIQUE,
    icone VARCHAR(40),
    ordem INTEGER NOT NULL DEFAULT 0,
    ativo BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS tbl_menu (
    id SERIAL PRIMARY KEY,
    nome_menu VARCHAR(120) NOT NULL,
    descricao TEXT,
    data_page VARCHAR(255) NOT NULL DEFAULT '/',
    icone VARCHAR(40),
    tipo_abrir VARCHAR(40) NOT NULL DEFAULT 'Mesma Janela',
    ordem INTEGER,
    parent_id INTEGER REFERENCES tbl_menu(id) ON DELETE SET NULL,
    pai BOOLEAN NOT NULL DEFAULT FALSE,
    status BOOLEAN NOT NULL DEFAULT TRUE,
    obs TEXT,
    id_modulo INTEGER REFERENCES tbl_menu_modulo(id) ON DELETE SET NULL,
    nav_codigo VARCHAR(32)
);

CREATE INDEX IF NOT EXISTS ix_menu_parent ON tbl_menu(parent_id);
CREATE INDEX IF NOT EXISTS ix_menu_status ON tbl_menu(status) WHERE status = TRUE;

CREATE TABLE IF NOT EXISTS tbl_perfil_menu (
    id_perfil INTEGER NOT NULL REFERENCES tbl_perfil(id) ON DELETE CASCADE,
    id_menu INTEGER NOT NULL REFERENCES tbl_menu(id) ON DELETE CASCADE,
    exibir BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (id_perfil, id_menu)
);

CREATE TABLE IF NOT EXISTS tbl_novidade (
    id SERIAL PRIMARY KEY,
    titulo VARCHAR(160) NOT NULL,
    resumo TEXT,
    conteudo TEXT,
    ordem INTEGER NOT NULL DEFAULT 0,
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    publicado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Módulos
INSERT INTO tbl_menu_modulo (modulo, icone, ordem, ativo) VALUES
    ('Operacional', 'layout-grid', 10, TRUE),
    ('Configuração', 'settings', 90, TRUE)
ON CONFLICT (modulo) DO NOTHING;

-- Menus principais (sidebar) — data_page = path Flask
INSERT INTO tbl_menu (nome_menu, descricao, data_page, icone, ordem, pai, status, id_modulo, nav_codigo)
SELECT v.nome, v.descricao, v.page, v.ico, v.ord, TRUE, TRUE, mm.id, v.nav
FROM (VALUES
    ('Dashboard', 'Painel inicial', '/index', 'layout-dashboard', 10, 'inicio'),
    ('Fornecedores', 'Rede de fornecedores', '/fornecedores', 'users', 20, 'fornecedores'),
    ('Catálogos', 'Gestão de catálogos', '/catalogos', 'package', 30, 'catalogos'),
    ('Meus produtos', 'Produtos do vendedor', '/meus-produtos', 'shopping-bag', 40, 'produtos'),
    ('Integrações', 'Marketplaces e ERPs', '/integracoes', 'plug', 50, 'integracoes')
) AS v(nome, descricao, page, ico, ord, nav)
LEFT JOIN tbl_menu_modulo mm ON mm.modulo = 'Operacional'
WHERE NOT EXISTS (SELECT 1 FROM tbl_menu m WHERE m.nav_codigo = v.nav);

-- Perfil × menu: dono e admin veem tudo; demais conforme operação
INSERT INTO tbl_perfil_menu (id_perfil, id_menu, exibir)
SELECT p.id, m.id, TRUE
FROM tbl_perfil p
CROSS JOIN tbl_menu m
WHERE m.status = TRUE
  AND p.codigo IN ('dono', 'admin')
ON CONFLICT DO NOTHING;

INSERT INTO tbl_perfil_menu (id_perfil, id_menu, exibir)
SELECT p.id, m.id, TRUE
FROM tbl_perfil p
JOIN tbl_menu m ON m.status = TRUE AND m.nav_codigo IN ('inicio', 'fornecedores', 'catalogos', 'produtos')
WHERE p.codigo = 'vendedor'
ON CONFLICT DO NOTHING;

INSERT INTO tbl_perfil_menu (id_perfil, id_menu, exibir)
SELECT p.id, m.id, TRUE
FROM tbl_perfil p
JOIN tbl_menu m ON m.status = TRUE AND m.nav_codigo IN ('inicio', 'catalogos', 'produtos')
WHERE p.codigo = 'operador'
ON CONFLICT DO NOTHING;

INSERT INTO tbl_perfil_menu (id_perfil, id_menu, exibir)
SELECT p.id, m.id, TRUE
FROM tbl_perfil p
JOIN tbl_menu m ON m.status = TRUE AND m.nav_codigo IN ('inicio', 'financeiro')
WHERE p.codigo = 'financeiro'
ON CONFLICT DO NOTHING;

INSERT INTO tbl_perfil_menu (id_perfil, id_menu, exibir)
SELECT p.id, m.id, TRUE
FROM tbl_perfil p
JOIN tbl_menu m ON m.status = TRUE
WHERE p.codigo = 'visualizador'
ON CONFLICT DO NOTHING;
