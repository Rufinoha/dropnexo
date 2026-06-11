-- DropNexo — schema inicial + RBAC (perfis e permissões)
-- Executar em: bd_dropnexo

-- ─── Perfis de acesso (por tenant) ───
CREATE TABLE IF NOT EXISTS tbl_perfil (
    id SERIAL PRIMARY KEY,
    codigo VARCHAR(32) NOT NULL UNIQUE,
    nome VARCHAR(80) NOT NULL,
    descricao TEXT,
    nivel INTEGER NOT NULL DEFAULT 0,
    eh_sistema BOOLEAN NOT NULL DEFAULT TRUE,
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── Permissões granulares (módulo.ação) ───
CREATE TABLE IF NOT EXISTS tbl_permissao (
    id SERIAL PRIMARY KEY,
    codigo VARCHAR(64) NOT NULL UNIQUE,
    modulo VARCHAR(40) NOT NULL,
    descricao TEXT,
    ativo BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS tbl_perfil_permissao (
    id_perfil INTEGER NOT NULL REFERENCES tbl_perfil(id) ON DELETE CASCADE,
    id_permissao INTEGER NOT NULL REFERENCES tbl_permissao(id) ON DELETE CASCADE,
    PRIMARY KEY (id_perfil, id_permissao)
);

-- ─── Tenant (empresa / conta) ───
CREATE TABLE IF NOT EXISTS tbl_tenant (
    id SERIAL PRIMARY KEY,
    tipo_pessoa CHAR(1) NOT NULL CHECK (tipo_pessoa IN ('F', 'J')),
    tipo_negocio VARCHAR(20) NOT NULL DEFAULT 'vendedor'
        CHECK (tipo_negocio IN ('fornecedor', 'vendedor', 'hibrido')),
    documento VARCHAR(14) NOT NULL UNIQUE,
    nome_completo VARCHAR(255) NOT NULL,
    nome VARCHAR(120) NOT NULL,
    slug VARCHAR(64) NOT NULL UNIQUE,
    plano VARCHAR(20) NOT NULL DEFAULT 'starter'
        CHECK (plano IN ('starter', 'professional', 'enterprise')),
    ativo BOOLEAN NOT NULL DEFAULT FALSE,
    cep VARCHAR(8) NOT NULL,
    logradouro VARCHAR(255) NOT NULL,
    numero VARCHAR(20) NOT NULL,
    complemento VARCHAR(120),
    bairro VARCHAR(120) NOT NULL,
    cidade VARCHAR(120) NOT NULL,
    uf CHAR(2) NOT NULL,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── Usuário (login global) ───
CREATE TABLE IF NOT EXISTS tbl_usuario (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    whatsapp VARCHAR(20),
    senha_hash TEXT,
    ativo BOOLEAN NOT NULL DEFAULT FALSE,
    token_ativacao VARCHAR(64),
    token_expira_em TIMESTAMPTZ,
    foto_caminho TEXT,
    eh_desenvolvedor BOOLEAN NOT NULL DEFAULT FALSE,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON COLUMN tbl_usuario.eh_desenvolvedor IS
    'Desenvolvedor da plataforma: acesso total (bypass RBAC) para testes e suporte.';

-- ─── Vínculo usuário ↔ tenant + perfil de acesso ───
CREATE TABLE IF NOT EXISTS tbl_usuario_tenant (
    id SERIAL PRIMARY KEY,
    id_usuario INTEGER NOT NULL REFERENCES tbl_usuario(id) ON DELETE CASCADE,
    id_tenant INTEGER NOT NULL REFERENCES tbl_tenant(id) ON DELETE CASCADE,
    id_perfil INTEGER NOT NULL REFERENCES tbl_perfil(id),
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    ultimo_acesso_em TIMESTAMPTZ,
    UNIQUE (id_usuario, id_tenant)
);

-- Regra "um dono por tenant" validada na aplicação (cadastro/equipe).

-- E-mail (Brevo log)
CREATE TABLE IF NOT EXISTS tbl_email_envio (
    id_envio SERIAL PRIMARY KEY,
    tag_email VARCHAR(64),
    assunto VARCHAR(255),
    corpo TEXT,
    dt_envio TIMESTAMPTZ,
    criado_por INTEGER
);

CREATE TABLE IF NOT EXISTS tbl_email_destinatario (
    id SERIAL PRIMARY KEY,
    id_envio INTEGER REFERENCES tbl_email_envio(id_envio) ON DELETE CASCADE,
    email VARCHAR(255),
    status_atual VARCHAR(40),
    dt_ultimo_evento TIMESTAMPTZ,
    tag_email VARCHAR(64)
);

CREATE TABLE IF NOT EXISTS tbl_email_log (
    id SERIAL PRIMARY KEY,
    assunto VARCHAR(255),
    corpo TEXT,
    destinatario TEXT,
    status VARCHAR(40),
    tag VARCHAR(64),
    data_envio TIMESTAMPTZ,
    criado_por INTEGER
);
