"""Eco de estoque Amazon — evita loop ao sincronizar quantidades."""
from __future__ import annotations

import threading
from contextlib import contextmanager
from datetime import timedelta

from global_utils import agora_utc

ECO_TTL_SEGUNDOS = 180

_suprimir_sync = threading.local()


def amazon_sync_suprimido() -> bool:
    return bool(getattr(_suprimir_sync, "ativo", False))


@contextmanager
def suprimir_sync_amazon():
    """Use ao baixar estoque por pedido importado da Amazon (não reenviar à Amazon)."""
    prev = getattr(_suprimir_sync, "ativo", False)
    _suprimir_sync.ativo = True
    try:
        yield
    finally:
        _suprimir_sync.ativo = prev


def _garantir_tabela_eco_amazon(cur) -> bool:
    try:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS tbl_integracao_amazon_eco_estoque (
                id SERIAL PRIMARY KEY,
                id_tenant INTEGER NOT NULL REFERENCES tbl_tenant(id) ON DELETE CASCADE,
                amazon_sku_key VARCHAR(128) NOT NULL,
                quantidade_esperada INTEGER,
                origem VARCHAR(32) NOT NULL DEFAULT 'dropnexo',
                criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                expira_em TIMESTAMPTZ NOT NULL,
                consumido_em TIMESTAMPTZ
            )
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_amazon_eco_estoque_lookup
                ON tbl_integracao_amazon_eco_estoque (id_tenant, amazon_sku_key, expira_em)
                WHERE consumido_em IS NULL
            """
        )
        return True
    except Exception:
        return False


def registrar_eco_amazon_pendente(
    cur,
    id_tenant: int,
    *,
    amazon_sku_key: str,
    quantidade_esperada: int | None,
    origem: str = "dropnexo",
    ttl_segundos: int = ECO_TTL_SEGUNDOS,
) -> None:
    if not _garantir_tabela_eco_amazon(cur):
        return
    agora = agora_utc()
    expira = agora + timedelta(seconds=max(30, ttl_segundos))
    cur.execute(
        """
        INSERT INTO tbl_integracao_amazon_eco_estoque (
            id_tenant, amazon_sku_key, quantidade_esperada, origem, criado_em, expira_em
        ) VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            id_tenant,
            str(amazon_sku_key),
            quantidade_esperada,
            origem,
            agora,
            expira,
        ),
    )


def limpar_ecos_amazon_expirados(cur) -> None:
    if not _garantir_tabela_eco_amazon(cur):
        return
    cur.execute(
        """
        DELETE FROM tbl_integracao_amazon_eco_estoque
        WHERE expira_em < %s AND consumido_em IS NULL
        """,
        (agora_utc(),),
    )


def eco_amazon_deve_ignorar(
    cur,
    id_tenant: int,
    *,
    amazon_sku_key: str,
    quantidade: int | None,
) -> bool:
    """True se a alteração na Amazon é eco de envio originado pelo DropNexo."""
    if not _garantir_tabela_eco_amazon(cur):
        return False
    limpar_ecos_amazon_expirados(cur)
    cur.execute(
        """
        SELECT id, quantidade_esperada FROM tbl_integracao_amazon_eco_estoque
        WHERE id_tenant = %s
          AND amazon_sku_key = %s
          AND consumido_em IS NULL
          AND expira_em >= %s
        ORDER BY id DESC
        LIMIT 1
        """,
        (id_tenant, str(amazon_sku_key), agora_utc()),
    )
    row = cur.fetchone()
    if not row:
        return False
    eco_id, qtd_esperada = row[0], row[1]
    if qtd_esperada is not None and quantidade is not None and int(qtd_esperada) != int(quantidade):
        return False
    cur.execute(
        "UPDATE tbl_integracao_amazon_eco_estoque SET consumido_em = %s WHERE id = %s",
        (agora_utc(), eco_id),
    )
    return True
