"""Tabelas da integração API Externa."""
from __future__ import annotations


def _add_column(cur, table: str, column: str, ddl: str) -> None:
    cur.execute(
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_schema = 'public'
           AND table_name = %s
           AND column_name = %s
         LIMIT 1
        """,
        (table, column),
    )
    if cur.fetchone():
        return
    cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


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
    _add_column(cur, "tbl_integracao_api_externa", "homolog_status", "VARCHAR(30) NOT NULL DEFAULT 'pendente'")
    _add_column(cur, "tbl_integracao_api_externa", "homolog_checklist", "JSONB NOT NULL DEFAULT '{}'::jsonb")
    _add_column(cur, "tbl_integracao_api_externa", "homolog_solicitado_em", "TIMESTAMPTZ NULL")
    _add_column(cur, "tbl_integracao_api_externa", "homolog_aprovado_em", "TIMESTAMPTZ NULL")
    _add_column(cur, "tbl_integracao_api_externa", "homolog_aprovado_por", "INTEGER NULL")
    _add_column(cur, "tbl_integracao_api_externa", "homolog_obs", "TEXT NULL")

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
