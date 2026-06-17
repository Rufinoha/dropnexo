-- DropNexo — catálogo dinâmico do Marktplace (add-ons e treinamentos)

CREATE TABLE IF NOT EXISTS tbl_marktplace_produto (
    id SERIAL PRIMARY KEY,
    slug VARCHAR(64) NOT NULL UNIQUE,
    titulo VARCHAR(160) NOT NULL,
    resumo VARCHAR(500),
    descricao TEXT,
    valor_centavos INTEGER NOT NULL DEFAULT 0,
    tipo_pagamento VARCHAR(20) NOT NULL DEFAULT 'unico'
        CHECK (tipo_pagamento IN ('unico', 'mensal')),
    publico VARCHAR(20) NOT NULL DEFAULT 'ambos'
        CHECK (publico IN ('fornecedor', 'vendedor', 'ambos')),
    categoria VARCHAR(32) NOT NULL DEFAULT 'geral'
        CHECK (categoria IN ('modulo', 'armazenamento', 'treinamento', 'suporte', 'geral')),
    tipo_acao VARCHAR(40),
    meta JSONB NOT NULL DEFAULT '{}'::jsonb,
    icone VARCHAR(40) NOT NULL DEFAULT 'shopping-bag',
    cor_topo VARCHAR(16) NOT NULL DEFAULT '#5b57f5',
    ordem INTEGER NOT NULL DEFAULT 0,
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_marktplace_produto_ativo_ordem
    ON tbl_marktplace_produto (ativo, ordem, titulo);

-- Catálogo inicial (editável em Configurações → Marktplace)
-- Idempotente: pode rodar várias vezes (slug único).
INSERT INTO tbl_marktplace_produto
    (slug, titulo, resumo, descricao, valor_centavos, tipo_pagamento, publico, categoria, tipo_acao, meta, icone, cor_topo, ordem, ativo)
VALUES
    (
        'ativar-modulo-vendedor',
        'Ativar módulo Vendedor',
        'Opere como vendedor na rede DropNexo: busque fornecedores, monte vitrine e precifique produtos.',
        '<p>Ideal para quem já atua como <strong>fornecedor</strong> e quer também vender na rede.</p><ul><li>Acesso ao módulo Vendedor</li><li>Conta passa a operar em modo híbrido</li><li>Alternância entre painéis Fornecedor e Vendedor</li></ul>',
        19900, 'unico', 'fornecedor', 'modulo', 'modulo_vendedor', '{}'::jsonb, 'shopping-bag', '#5b57f5', 10, TRUE
    ),
    (
        'ativar-modulo-fornecedor',
        'Ativar módulo Fornecedor',
        'Publique catálogo, variações e integrações como fornecedor na plataforma.',
        '<p>Para contas <strong>vendedoras</strong> que desejam também disponibilizar produtos na rede.</p><ul><li>Catálogo, categorias e variações</li><li>Integração Bling e importação</li><li>Modo híbrido na mesma empresa</li></ul>',
        19900, 'unico', 'vendedor', 'modulo', 'modulo_fornecedor', '{}'::jsonb, 'truck', '#5b57f5', 20, TRUE
    ),
    (
        'armazenamento-100mb',
        '+ 100 MB de armazenamento',
        'Espaço extra para imagens e arquivos do catálogo.',
        '<p>Pacote adicional de <strong>100 MB</strong> para galeria de produtos e anexos.</p><p>Acumulativo conforme contratação.</p>',
        1900, 'mensal', 'ambos', 'armazenamento', 'storage', '{"mb": 100}'::jsonb, 'hard-drive', '#10b981', 30, TRUE
    ),
    (
        'armazenamento-1gb',
        '+ 1 GB de armazenamento',
        'Mais espaço para catálogos com muitas imagens e variações.',
        '<p>Pacote de <strong>1 GB</strong> para operações em escala.</p>',
        4900, 'mensal', 'ambos', 'armazenamento', 'storage', '{"mb": 1024}'::jsonb, 'hard-drive', '#059669', 40, TRUE
    ),
    (
        'implantacao-guiada-2h',
        'Implantação guiada — 2h online',
        'Sessão ao vivo com especialista para configurar sua conta e primeiros passos.',
        '<p>Treinamento online de <strong>2 horas</strong> com especialista DropNexo.</p><ul><li>Configuração da conta e segmentos</li><li>Primeiro produto ou vitrine</li><li>Tire dúvidas em tempo real</li></ul>',
        30000, 'unico', 'ambos', 'treinamento', 'treinamento', '{}'::jsonb, 'video', '#8b5cf6', 50, TRUE
    ),
    (
        'dominando-catalogo-variacoes',
        'Dominando Catálogo e Variações',
        'Aprenda variações, imagens, categorias e publicação na rede.',
        '<p>Curso prático focado no módulo <strong>Fornecedor</strong>.</p><ul><li>Produto pai e variantes</li><li>Galeria e imagem principal</li><li>Categorias por segmento</li></ul>',
        30000, 'unico', 'fornecedor', 'treinamento', 'treinamento', '{}'::jsonb, 'book-open', '#8b5cf6', 60, TRUE
    ),
    (
        'dominando-rede-fornecedores',
        'Dominando a Rede de Fornecedores',
        'Como buscar, favoritar e trabalhar com fornecedores na plataforma.',
        '<p>Treinamento para o módulo <strong>Vendedor</strong>.</p><ul><li>Busca e filtros na rede</li><li>Meus produtos e kits</li><li>Precificação e margens</li></ul>',
        30000, 'unico', 'vendedor', 'treinamento', 'treinamento', '{}'::jsonb, 'users', '#8b5cf6', 70, TRUE
    ),
    (
        'suporte-urgente-starter',
        'Suporte urgente (plano gratuito)',
        'Atendimento prioritário pontual para contas no plano Starter.',
        '<p>Para quem está no plano <strong>gratuito</strong> e precisa de ajuda urgente em uma operação crítica.</p><p><em>Não substitui o suporte dos planos pagos.</em></p>',
        9900, 'unico', 'ambos', 'suporte', 'suporte_urgente', '{"apenas_plano": "starter"}'::jsonb, 'headphones', '#f59e0b', 80, FALSE
    )
ON CONFLICT (slug) DO NOTHING;
