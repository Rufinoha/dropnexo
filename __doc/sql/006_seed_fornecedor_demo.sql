-- DropNexo — tenant fornecedor demo + produtos publicados (testar rede /fornecedores)

INSERT INTO tbl_tenant (
    tipo_pessoa, tipo_negocio, documento, nome_completo, nome, slug, plano, ativo,
    cep, logradouro, numero, bairro, cidade, uf
)
SELECT 'J', 'fornecedor', '11111111000191', 'Fornecedor Demo Ltda', 'Fornecedor Demo',
       'fornecedor-demo', 'starter', TRUE,
       '01310100', 'Av. Paulista', '200', 'Bela Vista', 'São Paulo', 'SP'
WHERE NOT EXISTS (SELECT 1 FROM tbl_tenant WHERE slug = 'fornecedor-demo');

INSERT INTO tbl_categoria (id_tenant, nome, ordem)
SELECT t.id, c.nome, c.ord
FROM tbl_tenant t
CROSS JOIN (VALUES ('Eletrônicos', 10), ('Moda', 20)) AS c(nome, ord)
WHERE t.slug = 'fornecedor-demo'
  AND NOT EXISTS (
      SELECT 1 FROM tbl_categoria cat
      WHERE cat.id_tenant = t.id AND cat.nome = c.nome
  );

INSERT INTO tbl_produto (
    id_tenant, id_categoria, sku, nome, descricao, preco, preco_promocional,
    unidade, imagem_url, ativo, publicado
)
SELECT t.id, cat.id, v.sku, v.nome, v.descricao, v.preco, v.preco_promo,
       'UN', NULL, TRUE, TRUE
FROM tbl_tenant t
CROSS JOIN (VALUES
    ('ELE-001', 'Fone Bluetooth Pro', 'Fone com cancelamento de ruído.', 'Eletrônicos', 89.90, 79.90),
    ('ELE-002', 'Carregador USB-C 65W', 'Carregamento rápido para notebook e celular.', 'Eletrônicos', 129.00, NULL),
    ('MOD-001', 'Camiseta Básica Algodão', 'Malha penteado, várias cores.', 'Moda', 39.90, 34.90)
) AS v(sku, nome, descricao, cat, preco, preco_promo)
JOIN tbl_categoria cat ON cat.id_tenant = t.id AND cat.nome = v.cat
WHERE t.slug = 'fornecedor-demo'
  AND NOT EXISTS (
      SELECT 1 FROM tbl_produto p
      WHERE p.id_tenant = t.id AND p.sku = v.sku
  );

INSERT INTO tbl_produto_estoque (id_produto, quantidade)
SELECT p.id, v.qtd
FROM tbl_produto p
JOIN tbl_tenant t ON t.id = p.id_tenant AND t.slug = 'fornecedor-demo'
JOIN (VALUES
    ('ELE-001', 120),
    ('ELE-002', 45),
    ('MOD-001', 200)
) AS v(sku, qtd) ON p.sku = v.sku
WHERE NOT EXISTS (SELECT 1 FROM tbl_produto_estoque e WHERE e.id_produto = p.id);
