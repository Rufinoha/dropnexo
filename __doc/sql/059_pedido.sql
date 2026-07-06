-- Pedidos B2B vendedor → fornecedor (Fase 0)

CREATE TABLE IF NOT EXISTS tbl_pedido_grupo (
    id SERIAL PRIMARY KEY,
    id_tenant_vendedor INTEGER NOT NULL REFERENCES tbl_tenant(id) ON DELETE CASCADE,
    numero VARCHAR(30) NOT NULL,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_pedido_grupo_numero
    ON tbl_pedido_grupo(id_tenant_vendedor, numero);

CREATE TABLE IF NOT EXISTS tbl_pedido (
    id SERIAL PRIMARY KEY,
    id_grupo INTEGER REFERENCES tbl_pedido_grupo(id) ON DELETE SET NULL,
    numero VARCHAR(30) NOT NULL,
    id_tenant_vendedor INTEGER NOT NULL REFERENCES tbl_tenant(id) ON DELETE CASCADE,
    id_tenant_fornecedor INTEGER NOT NULL REFERENCES tbl_tenant(id) ON DELETE CASCADE,
    origem VARCHAR(20) NOT NULL DEFAULT 'manual'
        CHECK (origem IN ('manual', 'bling', 'outro_erp')),
    status VARCHAR(30) NOT NULL DEFAULT 'rascunho'
        CHECK (status IN (
            'rascunho', 'aguardando_pagamento', 'pago',
            'em_expedicao', 'entregue', 'cancelado'
        )),
    status_pagamento VARCHAR(20) NOT NULL DEFAULT 'pendente'
        CHECK (status_pagamento IN ('pendente', 'pago', 'cancelado')),

    cliente_nome VARCHAR(200) NOT NULL DEFAULT '',
    cliente_email VARCHAR(200),
    cliente_telefone VARCHAR(40),
    cliente_documento VARCHAR(20),

    entrega_cep VARCHAR(10),
    entrega_logradouro VARCHAR(200),
    entrega_numero VARCHAR(20),
    entrega_complemento VARCHAR(100),
    entrega_bairro VARCHAR(100),
    entrega_cidade VARCHAR(100),
    entrega_uf CHAR(2),

    subtotal_produtos NUMERIC(12, 2) NOT NULL DEFAULT 0,
    valor_taxa_pedido NUMERIC(12, 2) NOT NULL DEFAULT 0,
    valor_frete NUMERIC(12, 2) NOT NULL DEFAULT 0,
    valor_total NUMERIC(12, 2) NOT NULL DEFAULT 0,
    observacoes TEXT,

    confirmado_em TIMESTAMPTZ,
    pago_em TIMESTAMPTZ,
    cancelado_em TIMESTAMPTZ,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_pedido_numero_vendedor
    ON tbl_pedido(id_tenant_vendedor, numero);
CREATE INDEX IF NOT EXISTS ix_pedido_fornecedor_status
    ON tbl_pedido(id_tenant_fornecedor, status);
CREATE INDEX IF NOT EXISTS ix_pedido_vendedor_status
    ON tbl_pedido(id_tenant_vendedor, status);
CREATE INDEX IF NOT EXISTS ix_pedido_grupo ON tbl_pedido(id_grupo);

CREATE TABLE IF NOT EXISTS tbl_pedido_item (
    id SERIAL PRIMARY KEY,
    id_pedido INTEGER NOT NULL REFERENCES tbl_pedido(id) ON DELETE CASCADE,
    id_variante INTEGER NOT NULL REFERENCES tbl_produto_variante(id),
    id_produto INTEGER NOT NULL REFERENCES tbl_produto(id),
    id_produto_vendedor INTEGER REFERENCES tbl_produto_vendedor(id) ON DELETE SET NULL,
    sku VARCHAR(80),
    nome_produto VARCHAR(255) NOT NULL,
    quantidade INTEGER NOT NULL CHECK (quantidade > 0),
    valor_drop NUMERIC(12, 2) NOT NULL DEFAULT 0,
    preco_venda NUMERIC(12, 2) NOT NULL DEFAULT 0,
    subtotal_drop NUMERIC(12, 2) NOT NULL DEFAULT 0,
    id_deposito_fornecedor INTEGER REFERENCES tbl_deposito_expedicao(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS ix_pedido_item_pedido ON tbl_pedido_item(id_pedido);

CREATE TABLE IF NOT EXISTS tbl_pedido_historico (
    id SERIAL PRIMARY KEY,
    id_pedido INTEGER NOT NULL REFERENCES tbl_pedido(id) ON DELETE CASCADE,
    evento VARCHAR(50) NOT NULL,
    detalhe TEXT,
    id_usuario INTEGER REFERENCES tbl_usuario(id) ON DELETE SET NULL,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_pedido_historico_pedido ON tbl_pedido_historico(id_pedido);

-- Menus e permissões
UPDATE tbl_menu SET
    descricao = 'Pedidos para fornecedores',
    nome_menu = 'Pedidos'
WHERE nav_codigo = 'vd_pedidos';

INSERT INTO tbl_permissao (codigo, modulo, descricao) VALUES
    ('vd_pedidos.ver', 'vd_pedidos', 'Ver pedidos (vendedor)'),
    ('vd_pedidos.editar', 'vd_pedidos', 'Gerenciar pedidos (vendedor)'),
    ('fn_pedidos.ver', 'fn_pedidos', 'Ver pedidos recebidos (fornecedor)'),
    ('fn_pedidos.editar', 'fn_pedidos', 'Gerenciar pedidos recebidos (fornecedor)')
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO tbl_perfil_permissao (id_perfil, id_permissao)
SELECT p.id, m.id
FROM tbl_perfil p
JOIN tbl_permissao m ON m.codigo IN (
    'vd_pedidos.ver', 'vd_pedidos.editar',
    'fn_pedidos.ver', 'fn_pedidos.editar'
)
WHERE p.codigo IN ('dono', 'admin', 'vendedor', 'fornecedor')
ON CONFLICT DO NOTHING;

INSERT INTO tbl_menu (
    nome_menu, descricao, data_page, icone, tipo_abrir, ordem, parent_id, pai, status,
    obs, id_modulo, nav_codigo, contexto_modulo
)
SELECT 'Pedidos', 'Pedidos recebidos dos vendedores', '/fornecedor/pedidos', 'clipboard-list',
       'Mesma Janela', 48, NULL, TRUE, TRUE, NULL,
       (SELECT id FROM tbl_menu_modulo WHERE modulo = 'Operacional' LIMIT 1),
       'fn_pedidos', 'fornecedor'
WHERE NOT EXISTS (SELECT 1 FROM tbl_menu WHERE nav_codigo = 'fn_pedidos');
