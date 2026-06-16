-- DropNexo — corrige textos dos segmentos (acentos/c cedilha) apos migration 024
-- Arquivo 100% ASCII (U& + jsonb_build_object). Seguro em qualquer client_encoding.

UPDATE tbl_segmento SET
    nome = U&'Casa, Decora\00E7\00E3o e Jardim',
    descricao = U&'Produtos destinados \00E0 resid\00EAncia, decora\00E7\00E3o, organiza\00E7\00E3o e \00E1reas externas.',
    meta = jsonb_build_object(
        'exemplos_categorias', jsonb_build_array(
            U&'Decora\00E7\00E3o', U&'Ilumina\00E7\00E3o', 'Jardinagem', U&'Organiza\00E7\00E3o',
            'Cozinha', 'Cama, mesa e banho', U&'Utilidades dom\00E9sticas'
        ),
        'exemplos_fornecedores', jsonb_build_array(
            'Fabricantes de quadros decorativos', U&'Empresas de ilumina\00E7\00E3o LED',
            U&'Distribuidores de utens\00EDlios dom\00E9sticos', 'Fabricantes de vasos e jardinagem'
        ),
        'aplicacao', U&'Ideal para revendedores focados em lar, decora\00E7\00E3o e utilidades.'
    )
WHERE slug = 'casa-decoracao-jardim' AND id_tenant IS NULL;

UPDATE tbl_segmento SET
    nome = U&'Moda e Acess\00F3rios',
    descricao = U&'Produtos relacionados a vestu\00E1rio e acess\00F3rios pessoais.',
    meta = jsonb_build_object(
        'exemplos_categorias', jsonb_build_array(
            'Moda feminina', 'Moda masculina', 'Moda infantil', 'Bolsas',
            U&'Rel\00F3gios', 'Semijoias', U&'\00D3culos'
        ),
        'exemplos_fornecedores', jsonb_build_array(
            U&'Confec\00E7\00F5es', U&'Atacadistas de acess\00F3rios', 'Fabricantes de semijoias'
        ),
        'aplicacao', 'Atende lojas de moda e marketplaces especializados.'
    )
WHERE slug = 'moda-acessorios' AND id_tenant IS NULL;

UPDATE tbl_segmento SET
    nome = U&'Beleza, Sa\00FAde e Bem-estar',
    descricao = U&'Produtos voltados para est\00E9tica, cuidados pessoais e qualidade de vida.',
    meta = jsonb_build_object(
        'exemplos_categorias', jsonb_build_array(
            'Skincare', U&'Cosm\00E9ticos', 'Massagem', 'Ergonomia', 'Cuidados pessoais'
        ),
        'exemplos_fornecedores', jsonb_build_array(
            U&'Ind\00FAstrias cosm\00E9ticas', 'Distribuidores de beleza', 'Fabricantes de massageadores'
        ),
        'aplicacao', 'Mercado recorrente e de alta demanda.',
        'observacao', U&'Implementar valida\00E7\00F5es para produtos regulados.'
    )
WHERE slug = 'beleza-saude-bem-estar' AND id_tenant IS NULL;

UPDATE tbl_segmento SET
    nome = U&'Infantil e Beb\00EAs',
    descricao = U&'Produtos voltados ao p\00FAblico infantil e maternidade.',
    meta = jsonb_build_object(
        'exemplos_categorias', jsonb_build_array(
            'Brinquedos', 'Maternidade', U&'Acess\00F3rios infantis', U&'Organiza\00E7\00E3o infantil'
        ),
        'exemplos_fornecedores', jsonb_build_array(
            'Fabricantes de brinquedos', 'Distribuidores infantis'
        ),
        'aplicacao', U&'Mercado com alta recorr\00EAncia e sazonalidade.'
    )
WHERE slug = 'infantil-bebes' AND id_tenant IS NULL;

UPDATE tbl_segmento SET
    nome = 'Pet Shop',
    descricao = U&'Produtos para animais dom\00E9sticos.',
    meta = jsonb_build_object(
        'exemplos_categorias', jsonb_build_array(
            U&'Alimenta\00E7\00E3o', 'Higiene', 'Brinquedos', 'Camas', 'Coleiras'
        ),
        'exemplos_fornecedores', jsonb_build_array(
            'Distribuidores pet', U&'Fabricantes de acess\00F3rios'
        ),
        'aplicacao', U&'Mercado em forte crescimento e recorr\00EAncia.'
    )
WHERE slug = 'pet-shop' AND id_tenant IS NULL;

UPDATE tbl_segmento SET
    nome = 'Esportes e Lazer',
    descricao = U&'Produtos para atividades f\00EDsicas e entretenimento.',
    meta = jsonb_build_object(
        'exemplos_categorias', jsonb_build_array('Fitness', 'Camping', 'Ciclismo', 'Lazer'),
        'exemplos_fornecedores', jsonb_build_array('Fabricantes esportivos', 'Distribuidores fitness'),
        'aplicacao', 'Alta demanda e boa margem.'
    )
WHERE slug = 'esportes-lazer' AND id_tenant IS NULL;

UPDATE tbl_segmento SET
    nome = 'Automotivo',
    descricao = U&'Produtos e acess\00F3rios para ve\00EDculos.',
    meta = jsonb_build_object(
        'exemplos_categorias', jsonb_build_array(
            U&'Acess\00F3rios automotivos', U&'Organiza\00E7\00E3o', U&'Ilumina\00E7\00E3o', 'Limpeza automotiva'
        ),
        'exemplos_fornecedores', jsonb_build_array(
            'Distribuidores automotivos', U&'Fabricantes de acess\00F3rios'
        ),
        'aplicacao', 'Mercado amplo e especializado.'
    )
WHERE slug = 'automotivo' AND id_tenant IS NULL;

UPDATE tbl_segmento SET
    nome = U&'Constru\00E7\00E3o e Ferramentas',
    descricao = U&'Produtos para constru\00E7\00E3o civil e manuten\00E7\00E3o.',
    meta = jsonb_build_object(
        'exemplos_categorias', jsonb_build_array(
            'Ferramentas', 'Ferragens', U&'El\00E9trica', U&'Hidr\00E1ulica'
        ),
        'exemplos_fornecedores', jsonb_build_array(
            'Home centers', 'Distribuidores de ferramentas', 'Fabricantes de materiais'
        ),
        'aplicacao', 'Atende consumidores e empresas.'
    )
WHERE slug = 'construcao-ferramentas' AND id_tenant IS NULL;

UPDATE tbl_segmento SET
    nome = U&'Tecnologia e Eletr\00F4nicos',
    descricao = U&'Produtos tecnol\00F3gicos e eletr\00F4nicos em geral.',
    meta = jsonb_build_object(
        'exemplos_categorias', jsonb_build_array(
            'Gadgets', 'Celulares', U&'Acess\00F3rios', U&'\00C1udio e v\00EDdeo'
        ),
        'exemplos_fornecedores', jsonb_build_array(
            'Importadores', U&'Distribuidores de eletr\00F4nicos'
        ),
        'aplicacao', 'Segmento de alto volume e alta competitividade.'
    )
WHERE slug = 'tecnologia-eletronicos' AND id_tenant IS NULL;

UPDATE tbl_segmento SET
    nome = U&'Escrit\00F3rio e Papelaria',
    descricao = U&'Produtos para escrit\00F3rios, estudo e home office.',
    meta = jsonb_build_object(
        'exemplos_categorias', jsonb_build_array(
            'Papelaria', U&'Organiza\00E7\00E3o', 'Home office', 'Material escolar'
        ),
        'exemplos_fornecedores', jsonb_build_array(
            'Distribuidores de papelaria', U&'Fabricantes de escrit\00F3rio'
        ),
        'aplicacao', U&'Mercado est\00E1vel e recorrente.'
    )
WHERE slug = 'escritorio-papelaria' AND id_tenant IS NULL;

UPDATE tbl_segmento SET
    nome = U&'Seguran\00E7a e Smart Home',
    descricao = U&'Produtos voltados \00E0 seguran\00E7a e automa\00E7\00E3o residencial.',
    meta = jsonb_build_object(
        'exemplos_categorias', jsonb_build_array(
            U&'C\00E2meras', 'Alarmes', 'Fechaduras inteligentes', U&'Automa\00E7\00E3o residencial'
        ),
        'exemplos_fornecedores', jsonb_build_array(
            U&'Fabricantes de seguran\00E7a', 'Empresas de IoT'
        ),
        'aplicacao', U&'Mercado em expans\00E3o.'
    )
WHERE slug = 'seguranca-smart-home' AND id_tenant IS NULL;

UPDATE tbl_segmento SET
    nome = 'Industrial e Empresas (B2B)',
    descricao = U&'Produtos destinados a empresas e opera\00E7\00F5es industriais.',
    meta = jsonb_build_object(
        'exemplos_categorias', jsonb_build_array(
            'EPIs', 'Equipamentos industriais', 'Ferramentas profissionais', 'Embalagens'
        ),
        'exemplos_fornecedores', jsonb_build_array(
            U&'Ind\00FAstrias', 'Distribuidores B2B'
        ),
        'aplicacao', U&'Segmento estrat\00E9gico para o DropNexo.'
    )
WHERE slug = 'industrial-b2b' AND id_tenant IS NULL;

UPDATE tbl_segmento SET
    nome = 'Personalizados e Artesanato',
    descricao = U&'Produtos personalizados e artesanais.',
    meta = jsonb_build_object(
        'exemplos_categorias', jsonb_build_array(
            'Brindes', 'Produtos customizados', 'Artesanato', 'Presentes'
        ),
        'exemplos_fornecedores', jsonb_build_array(
            'Pequenos fabricantes', U&'Artes\00E3os', U&'Empresas de personaliza\00E7\00E3o'
        ),
        'aplicacao', U&'Alta margem e diferencia\00E7\00E3o.'
    )
WHERE slug = 'personalizados-artesanato' AND id_tenant IS NULL;

UPDATE tbl_segmento SET
    nome = U&'Utilidades Dom\00E9sticas',
    descricao = U&'Produtos de uso cotidiano para o lar.',
    meta = jsonb_build_object(
        'exemplos_categorias', jsonb_build_array(
            'Limpeza', U&'Organiza\00E7\00E3o', 'Cozinha', 'Utilidades diversas'
        ),
        'exemplos_fornecedores', jsonb_build_array(
            U&'Distribuidores dom\00E9sticos', 'Fabricantes de utilidades'
        ),
        'aplicacao', U&'Segmento com alta recorr\00EAncia e grande volume.'
    )
WHERE slug = 'utilidades-domesticas' AND id_tenant IS NULL;
