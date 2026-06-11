-- DropNexo — Integração Bling (OAuth multi-tenant)

CREATE TABLE IF NOT EXISTS tbl_integracao_bling (
    id_tenant INTEGER PRIMARY KEY REFERENCES tbl_tenant(id) ON DELETE CASCADE,
    status VARCHAR(20) NOT NULL DEFAULT 'desconectado'
        CHECK (status IN ('desconectado', 'conectado', 'erro')),
    access_token_enc TEXT,
    refresh_token_enc TEXT,
    token_expires_em TIMESTAMPTZ,
    bling_conta_info JSONB NOT NULL DEFAULT '{}',
    conectado_em TIMESTAMPTZ,
    ultimo_erro TEXT,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS tbl_integracao_bling_config (
    id SERIAL PRIMARY KEY,
    id_tenant INTEGER NOT NULL REFERENCES tbl_tenant(id) ON DELETE CASCADE,
    contexto VARCHAR(20) NOT NULL CHECK (contexto IN ('fornecedor', 'vendedor')),
    fonte_principal VARCHAR(20) NOT NULL DEFAULT 'bling'
        CHECK (fonte_principal IN ('bling', 'dropnexo')),
    modo_imagem VARCHAR(20) NOT NULL DEFAULT 'link'
        CHECK (modo_imagem IN ('link', 'download')),
    produtos_modo VARCHAR(20) NOT NULL DEFAULT 'importar'
        CHECK (produtos_modo IN ('importar', 'exportar', 'atualizar')),
    estoque_modo VARCHAR(20) NOT NULL DEFAULT 'importar'
        CHECK (estoque_modo IN ('importar', 'exportar', 'atualizar')),
    pedidos_modo VARCHAR(20) NOT NULL DEFAULT 'importar'
        CHECK (pedidos_modo IN ('importar', 'exportar', 'atualizar')),
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    ultima_sync_produtos TIMESTAMPTZ,
    ultima_sync_estoque TIMESTAMPTZ,
    ultima_sync_pedidos TIMESTAMPTZ,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (id_tenant, contexto)
);

CREATE TABLE IF NOT EXISTS tbl_integracao_map (
    id SERIAL PRIMARY KEY,
    id_tenant INTEGER NOT NULL REFERENCES tbl_tenant(id) ON DELETE CASCADE,
    provedor VARCHAR(30) NOT NULL DEFAULT 'bling',
    contexto VARCHAR(20) NOT NULL CHECK (contexto IN ('fornecedor', 'vendedor')),
    entidade VARCHAR(30) NOT NULL CHECK (entidade IN ('produto', 'estoque', 'pedido', 'deposito')),
    id_bling VARCHAR(64) NOT NULL,
    id_dropnexo INTEGER,
    sku VARCHAR(64),
    meta JSONB NOT NULL DEFAULT '{}',
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (id_tenant, provedor, contexto, entidade, id_bling)
);

CREATE INDEX IF NOT EXISTS ix_integracao_map_tenant_sku
    ON tbl_integracao_map(id_tenant, sku) WHERE sku IS NOT NULL AND sku <> '';

CREATE TABLE IF NOT EXISTS tbl_integracao_log (
    id SERIAL PRIMARY KEY,
    id_tenant INTEGER NOT NULL REFERENCES tbl_tenant(id) ON DELETE CASCADE,
    provedor VARCHAR(30) NOT NULL DEFAULT 'bling',
    contexto VARCHAR(20),
    entidade VARCHAR(30),
    direcao VARCHAR(20),
    status VARCHAR(20) NOT NULL DEFAULT 'ok' CHECK (status IN ('ok', 'aviso', 'erro')),
    resumo TEXT,
    detalhe TEXT,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_integracao_log_tenant ON tbl_integracao_log(id_tenant, criado_em DESC);

CREATE TABLE IF NOT EXISTS tbl_integracao_deposito_map (
    id SERIAL PRIMARY KEY,
    id_tenant INTEGER NOT NULL REFERENCES tbl_tenant(id) ON DELETE CASCADE,
    id_bling_deposito VARCHAR(64) NOT NULL,
    nome_bling VARCHAR(120),
    id_deposito_dropnexo INTEGER REFERENCES tbl_deposito_expedicao(id) ON DELETE SET NULL,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (id_tenant, id_bling_deposito)
);
