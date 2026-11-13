"""Tabelas da integração API Externa."""
from __future__ import annotations


def garantir_tabelas(conn) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tbl_integracao_api_externa (
            id SERIAL PRIMARY KEY,
            id_tenant INTEGER NOT NULL UNIQUE,
            liberado BOOLEAN NOT NULL DEFAULT FALSE,
            liberado_em TIMESTAMPTZ NULL,
            liberado_por INTEGER NULL,
            nome_parceiro TEXT NULL,
            contato_tecnico TEXT NULL,
            ambiente VARCHAR(20) NOT NULL DEFAULT 'homologacao',
            base_url TEXT NULL,
            auth_tipo VARCHAR(20) NOT NULL DEFAULT 'bearer',
            token_parceiro_enc TEXT NULL,
            token_parceiro_hint TEXT NULL,
            webhook_url TEXT NULL,
            webhook_secret_enc TEXT NULL,
            dn_token_hash TEXT NULL,
            dn_token_hint TEXT NULL,
            dn_token_gerado_em TIMESTAMPTZ NULL,
            ativo BOOLEAN NOT NULL DEFAULT FALSE,
            cap_produtos_cadastrar BOOLEAN NOT NULL DEFAULT TRUE,
            cap_produtos_atualizar BOOLEAN NOT NULL DEFAULT TRUE,
            cap_estoque_atualizar BOOLEAN NOT NULL DEFAULT TRUE,
            cap_pedidos_enviar BOOLEAN NOT NULL DEFAULT FALSE,
            cap_pedidos_status BOOLEAN NOT NULL DEFAULT FALSE,
            status VARCHAR(20) NOT NULL DEFAULT 'desligado',
            ultima_sync_em TIMESTAMPTZ NULL,
            ultima_sync_ok BOOLEAN NULL,
            ultima_mensagem TEXT NULL,
            opcoes JSONB NOT NULL DEFAULT '{}'::jsonb,
            dt_criacao TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            dt_atualizacao TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tbl_integracao_api_externa_log (
            id BIGSERIAL PRIMARY KEY,
            id_tenant INTEGER NOT NULL,
            evento TEXT NOT NULL,
            direcao VARCHAR(20) NULL,
            referencia TEXT NULL,
            http_status INTEGER NULL,
            sucesso BOOLEAN NOT NULL DEFAULT FALSE,
            mensagem TEXT NULL,
            detalhe JSONB NULL,
            dt_criacao TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_api_ext_log_tenant_dt
            ON tbl_integracao_api_externa_log (id_tenant, dt_criacao DESC)
        """
    )
