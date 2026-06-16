-- DropNexo — Segmentos marketplace B2B (master data expandido)
-- Arquivo UTF-8. Após rodar, execute também 025_segmentos_textos_utf8.sql se os acentos falharem.

SET client_encoding TO 'UTF8';

ALTER TABLE tbl_segmento ADD COLUMN IF NOT EXISTS icone VARCHAR(40);
ALTER TABLE tbl_segmento ADD COLUMN IF NOT EXISTS cor VARCHAR(16);
ALTER TABLE tbl_segmento ADD COLUMN IF NOT EXISTS meta JSONB NOT NULL DEFAULT '{}';

-- Ocultar menu Segmentos (gestão em Minha empresa → Minha empresa)
UPDATE tbl_menu SET status = FALSE, descricao = 'Movido para Minha empresa'
WHERE nav_codigo = 'fn_segmentos';

-- Upsert 14 segmentos oficiais
INSERT INTO tbl_segmento (id_tenant, nome, slug, descricao, ordem, ativo, icone, cor, meta)
SELECT NULL, v.nome, v.slug, v.descr, v.ord, TRUE, v.icone, v.cor, v.meta::jsonb
FROM (VALUES
    ('Casa, Decoração e Jardim', 'casa-decoracao-jardim',
     'Produtos destinados à residência, decoração, organização e áreas externas.', 10, 'home', '#0ea5e9',
     '{"exemplos_categorias":["Decoração","Iluminação","Jardinagem","Organização","Cozinha","Cama, mesa e banho","Utilidades domésticas"],"exemplos_fornecedores":["Fabricantes de quadros decorativos","Empresas de iluminação LED","Distribuidores de utensílios domésticos","Fabricantes de vasos e jardinagem"],"aplicacao":"Ideal para revendedores focados em lar, decoração e utilidades."}'),
    ('Moda e Acessórios', 'moda-acessorios',
     'Produtos relacionados a vestuário e acessórios pessoais.', 20, 'shirt', '#ec4899',
     '{"exemplos_categorias":["Moda feminina","Moda masculina","Moda infantil","Bolsas","Relógios","Semijoias","Óculos"],"exemplos_fornecedores":["Confecções","Atacadistas de acessórios","Fabricantes de semijoias"],"aplicacao":"Atende lojas de moda e marketplaces especializados."}'),
    ('Beleza, Saúde e Bem-estar', 'beleza-saude-bem-estar',
     'Produtos voltados para estética, cuidados pessoais e qualidade de vida.', 30, 'sparkles', '#a855f7',
     '{"exemplos_categorias":["Skincare","Cosméticos","Massagem","Ergonomia","Cuidados pessoais"],"exemplos_fornecedores":["Indústrias cosméticas","Distribuidores de beleza","Fabricantes de massageadores"],"aplicacao":"Mercado recorrente e de alta demanda.","observacao":"Implementar validações para produtos regulados."}'),
    ('Infantil e Bebês', 'infantil-bebes',
     'Produtos voltados ao público infantil e maternidade.', 40, 'baby', '#f472b6',
     '{"exemplos_categorias":["Brinquedos","Maternidade","Acessórios infantis","Organização infantil"],"exemplos_fornecedores":["Fabricantes de brinquedos","Distribuidores infantis"],"aplicacao":"Mercado com alta recorrência e sazonalidade."}'),
    ('Pet Shop', 'pet-shop',
     'Produtos para animais domésticos.', 50, 'dog', '#84cc16',
     '{"exemplos_categorias":["Alimentação","Higiene","Brinquedos","Camas","Coleiras"],"exemplos_fornecedores":["Distribuidores pet","Fabricantes de acessórios"],"aplicacao":"Mercado em forte crescimento e recorrência."}'),
    ('Esportes e Lazer', 'esportes-lazer',
     'Produtos para atividades físicas e entretenimento.', 60, 'dumbbell', '#22c55e',
     '{"exemplos_categorias":["Fitness","Camping","Ciclismo","Lazer"],"exemplos_fornecedores":["Fabricantes esportivos","Distribuidores fitness"],"aplicacao":"Alta demanda e boa margem."}'),
    ('Automotivo', 'automotivo',
     'Produtos e acessórios para veículos.', 70, 'car', '#64748b',
     '{"exemplos_categorias":["Acessórios automotivos","Organização","Iluminação","Limpeza automotiva"],"exemplos_fornecedores":["Distribuidores automotivos","Fabricantes de acessórios"],"aplicacao":"Mercado amplo e especializado."}'),
    ('Construção e Ferramentas', 'construcao-ferramentas',
     'Produtos para construção civil e manutenção.', 80, 'hammer', '#f59e0b',
     '{"exemplos_categorias":["Ferramentas","Ferragens","Elétrica","Hidráulica"],"exemplos_fornecedores":["Home centers","Distribuidores de ferramentas","Fabricantes de materiais"],"aplicacao":"Atende consumidores e empresas."}'),
    ('Tecnologia e Eletrônicos', 'tecnologia-eletronicos',
     'Produtos tecnológicos e eletrônicos em geral.', 90, 'smartphone', '#3b82f6',
     '{"exemplos_categorias":["Gadgets","Celulares","Acessórios","Áudio e vídeo"],"exemplos_fornecedores":["Importadores","Distribuidores de eletrônicos"],"aplicacao":"Segmento de alto volume e alta competitividade."}'),
    ('Escritório e Papelaria', 'escritorio-papelaria',
     'Produtos para escritórios, estudo e home office.', 100, 'briefcase', '#6366f1',
     '{"exemplos_categorias":["Papelaria","Organização","Home office","Material escolar"],"exemplos_fornecedores":["Distribuidores de papelaria","Fabricantes de escritório"],"aplicacao":"Mercado estável e recorrente."}'),
    ('Segurança e Smart Home', 'seguranca-smart-home',
     'Produtos voltados à segurança e automação residencial.', 110, 'shield', '#14b8a6',
     '{"exemplos_categorias":["Câmeras","Alarmes","Fechaduras inteligentes","Automação residencial"],"exemplos_fornecedores":["Fabricantes de segurança","Empresas de IoT"],"aplicacao":"Mercado em expansão."}'),
    ('Industrial e Empresas (B2B)', 'industrial-b2b',
     'Produtos destinados a empresas e operações industriais.', 120, 'factory', '#475569',
     '{"exemplos_categorias":["EPIs","Equipamentos industriais","Ferramentas profissionais","Embalagens"],"exemplos_fornecedores":["Indústrias","Distribuidores B2B"],"aplicacao":"Segmento estratégico para o DropNexo."}'),
    ('Personalizados e Artesanato', 'personalizados-artesanato',
     'Produtos personalizados e artesanais.', 130, 'palette', '#d946ef',
     '{"exemplos_categorias":["Brindes","Produtos customizados","Artesanato","Presentes"],"exemplos_fornecedores":["Pequenos fabricantes","Artesãos","Empresas de personalização"],"aplicacao":"Alta margem e diferenciação."}'),
    ('Utilidades Domésticas', 'utilidades-domesticas',
     'Produtos de uso cotidiano para o lar.', 140, 'package', '#0d9488',
     '{"exemplos_categorias":["Limpeza","Organização","Cozinha","Utilidades diversas"],"exemplos_fornecedores":["Distribuidores domésticos","Fabricantes de utilidades"],"aplicacao":"Segmento com alta recorrência e grande volume."}')
) AS v(nome, slug, descr, ord, icone, cor, meta)
WHERE NOT EXISTS (SELECT 1 FROM tbl_segmento s WHERE s.slug = v.slug);

UPDATE tbl_segmento s SET
    nome = v.nome,
    descricao = v.descr,
    ordem = v.ord,
    ativo = TRUE,
    icone = v.icone,
    cor = v.cor,
    meta = v.meta::jsonb
FROM (VALUES
    ('casa-decoracao-jardim', 'Casa, Decoração e Jardim', 'Produtos destinados à residência, decoração, organização e áreas externas.', 10, 'home', '#0ea5e9', '{"exemplos_categorias":["Decoração","Iluminação","Jardinagem","Organização","Cozinha","Cama, mesa e banho","Utilidades domésticas"],"exemplos_fornecedores":["Fabricantes de quadros decorativos","Empresas de iluminação LED","Distribuidores de utensílios domésticos","Fabricantes de vasos e jardinagem"],"aplicacao":"Ideal para revendedores focados em lar, decoração e utilidades."}'),
    ('moda-acessorios', 'Moda e Acessórios', 'Produtos relacionados a vestuário e acessórios pessoais.', 20, 'shirt', '#ec4899', '{"exemplos_categorias":["Moda feminina","Moda masculina","Moda infantil","Bolsas","Relógios","Semijoias","Óculos"],"exemplos_fornecedores":["Confecções","Atacadistas de acessórios","Fabricantes de semijoias"],"aplicacao":"Atende lojas de moda e marketplaces especializados."}'),
    ('beleza-saude-bem-estar', 'Beleza, Saúde e Bem-estar', 'Produtos voltados para estética, cuidados pessoais e qualidade de vida.', 30, 'sparkles', '#a855f7', '{"exemplos_categorias":["Skincare","Cosméticos","Massagem","Ergonomia","Cuidados pessoais"],"exemplos_fornecedores":["Indústrias cosméticas","Distribuidores de beleza","Fabricantes de massageadores"],"aplicacao":"Mercado recorrente e de alta demanda.","observacao":"Implementar validações para produtos regulados."}'),
    ('infantil-bebes', 'Infantil e Bebês', 'Produtos voltados ao público infantil e maternidade.', 40, 'baby', '#f472b6', '{"exemplos_categorias":["Brinquedos","Maternidade","Acessórios infantis","Organização infantil"],"exemplos_fornecedores":["Fabricantes de brinquedos","Distribuidores infantis"],"aplicacao":"Mercado com alta recorrência e sazonalidade."}'),
    ('pet-shop', 'Pet Shop', 'Produtos para animais domésticos.', 50, 'dog', '#84cc16', '{"exemplos_categorias":["Alimentação","Higiene","Brinquedos","Camas","Coleiras"],"exemplos_fornecedores":["Distribuidores pet","Fabricantes de acessórios"],"aplicacao":"Mercado em forte crescimento e recorrência."}'),
    ('esportes-lazer', 'Esportes e Lazer', 'Produtos para atividades físicas e entretenimento.', 60, 'dumbbell', '#22c55e', '{"exemplos_categorias":["Fitness","Camping","Ciclismo","Lazer"],"exemplos_fornecedores":["Fabricantes esportivos","Distribuidores fitness"],"aplicacao":"Alta demanda e boa margem."}'),
    ('automotivo', 'Automotivo', 'Produtos e acessórios para veículos.', 70, 'car', '#64748b', '{"exemplos_categorias":["Acessórios automotivos","Organização","Iluminação","Limpeza automotiva"],"exemplos_fornecedores":["Distribuidores automotivos","Fabricantes de acessórios"],"aplicacao":"Mercado amplo e especializado."}'),
    ('construcao-ferramentas', 'Construção e Ferramentas', 'Produtos para construção civil e manutenção.', 80, 'hammer', '#f59e0b', '{"exemplos_categorias":["Ferramentas","Ferragens","Elétrica","Hidráulica"],"exemplos_fornecedores":["Home centers","Distribuidores de ferramentas","Fabricantes de materiais"],"aplicacao":"Atende consumidores e empresas."}'),
    ('tecnologia-eletronicos', 'Tecnologia e Eletrônicos', 'Produtos tecnológicos e eletrônicos em geral.', 90, 'smartphone', '#3b82f6', '{"exemplos_categorias":["Gadgets","Celulares","Acessórios","Áudio e vídeo"],"exemplos_fornecedores":["Importadores","Distribuidores de eletrônicos"],"aplicacao":"Segmento de alto volume e alta competitividade."}'),
    ('escritorio-papelaria', 'Escritório e Papelaria', 'Produtos para escritórios, estudo e home office.', 100, 'briefcase', '#6366f1', '{"exemplos_categorias":["Papelaria","Organização","Home office","Material escolar"],"exemplos_fornecedores":["Distribuidores de papelaria","Fabricantes de escritório"],"aplicacao":"Mercado estável e recorrente."}'),
    ('seguranca-smart-home', 'Segurança e Smart Home', 'Produtos voltados à segurança e automação residencial.', 110, 'shield', '#14b8a6', '{"exemplos_categorias":["Câmeras","Alarmes","Fechaduras inteligentes","Automação residencial"],"exemplos_fornecedores":["Fabricantes de segurança","Empresas de IoT"],"aplicacao":"Mercado em expansão."}'),
    ('industrial-b2b', 'Industrial e Empresas (B2B)', 'Produtos destinados a empresas e operações industriais.', 120, 'factory', '#475569', '{"exemplos_categorias":["EPIs","Equipamentos industriais","Ferramentas profissionais","Embalagens"],"exemplos_fornecedores":["Indústrias","Distribuidores B2B"],"aplicacao":"Segmento estratégico para o DropNexo."}'),
    ('personalizados-artesanato', 'Personalizados e Artesanato', 'Produtos personalizados e artesanais.', 130, 'palette', '#d946ef', '{"exemplos_categorias":["Brindes","Produtos customizados","Artesanato","Presentes"],"exemplos_fornecedores":["Pequenos fabricantes","Artesãos","Empresas de personalização"],"aplicacao":"Alta margem e diferenciação."}'),
    ('utilidades-domesticas', 'Utilidades Domésticas', 'Produtos de uso cotidiano para o lar.', 140, 'package', '#0d9488', '{"exemplos_categorias":["Limpeza","Organização","Cozinha","Utilidades diversas"],"exemplos_fornecedores":["Distribuidores domésticos","Fabricantes de utilidades"],"aplicacao":"Segmento com alta recorrência e grande volume."}')
) AS v(slug, nome, descr, ord, icone, cor, meta)
WHERE s.slug = v.slug AND s.id_tenant IS NULL;

-- Remapear vínculos de slugs antigos → novos
INSERT INTO tbl_fornecedor_segmento (id_tenant, id_segmento)
SELECT DISTINCT fs.id_tenant, novo.id
FROM tbl_fornecedor_segmento fs
JOIN tbl_segmento antigo ON antigo.id = fs.id_segmento
JOIN (VALUES
    ('moda-vestuario', 'moda-acessorios'),
    ('calcados', 'moda-acessorios'),
    ('joias-acessorios', 'moda-acessorios'),
    ('eletronicos', 'tecnologia-eletronicos'),
    ('casa-decoracao', 'casa-decoracao-jardim'),
    ('beleza-perfumaria', 'beleza-saude-bem-estar'),
    ('esporte-lazer', 'esportes-lazer'),
    ('infantil', 'infantil-bebes'),
    ('pet', 'pet-shop'),
    ('papelaria-escritorio', 'escritorio-papelaria'),
    ('automotivo', 'automotivo'),
    ('saude-bem-estar', 'beleza-saude-bem-estar')
) AS m(old_slug, new_slug) ON antigo.slug = m.old_slug
JOIN tbl_segmento novo ON novo.slug = m.new_slug
ON CONFLICT DO NOTHING;

UPDATE tbl_categoria c SET id_segmento = novo.id
FROM tbl_segmento antigo
JOIN (VALUES
    ('moda-vestuario', 'moda-acessorios'),
    ('calcados', 'moda-acessorios'),
    ('joias-acessorios', 'moda-acessorios'),
    ('eletronicos', 'tecnologia-eletronicos'),
    ('casa-decoracao', 'casa-decoracao-jardim'),
    ('beleza-perfumaria', 'beleza-saude-bem-estar'),
    ('esporte-lazer', 'esportes-lazer'),
    ('infantil', 'infantil-bebes'),
    ('pet', 'pet-shop'),
    ('papelaria-escritorio', 'escritorio-papelaria'),
    ('automotivo', 'automotivo'),
    ('saude-bem-estar', 'beleza-saude-bem-estar')
) AS m(old_slug, new_slug) ON antigo.slug = m.old_slug
JOIN tbl_segmento novo ON novo.slug = m.new_slug
WHERE c.id_segmento = antigo.id;

-- Desativar segmentos legados substituídos
UPDATE tbl_segmento SET ativo = FALSE
WHERE id_tenant IS NULL
  AND slug IN (
    'moda-vestuario', 'calcados', 'joias-acessorios', 'eletronicos', 'casa-decoracao',
    'beleza-perfumaria', 'esporte-lazer', 'infantil', 'pet', 'papelaria-escritorio', 'saude-bem-estar'
  )
  AND slug NOT IN (
    'casa-decoracao-jardim', 'moda-acessorios', 'beleza-saude-bem-estar', 'infantil-bebes',
    'pet-shop', 'esportes-lazer', 'automotivo', 'construcao-ferramentas', 'tecnologia-eletronicos',
    'escritorio-papelaria', 'seguranca-smart-home', 'industrial-b2b', 'personalizados-artesanato',
    'utilidades-domesticas'
  );

DELETE FROM tbl_fornecedor_segmento fs
USING tbl_segmento s
WHERE fs.id_segmento = s.id AND s.id_tenant IS NULL AND s.ativo = FALSE;
