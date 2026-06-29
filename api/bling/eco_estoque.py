# api/bling/eco_estoque.py — supressão de eco (webhook após envio DropNexo → Bling)
from __future__ import annotations

from datetime import timedelta

from global_utils import agora_utc

ECO_TTL_SEGUNDOS = 180


def registrar_eco_pendente(
    cur,
    id_tenant: int,
    *,
    id_bling_produto: str,
    id_bling_deposito: str,
    quantidade_esperada: int | None,
    origem: str,
    ttl_segundos: int = ECO_TTL_SEGUNDOS,
) -> None:
    agora = agora_utc()
    expira = agora + timedelta(seconds=max(30, ttl_segundos))
    cur.execute(
        """
        INSERT INTO tbl_integracao_bling_eco_estoque (
            id_tenant, id_bling_produto, id_bling_deposito,
            quantidade_esperada, origem, criado_em, expira_em
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            id_tenant,
            str(id_bling_produto),
            str(id_bling_deposito),
            quantidade_esperada,
            origem,
            agora,
            expira,
        ),
    )


def limpar_ecos_expirados(cur) -> None:
    cur.execute(
        """
        DELETE FROM tbl_integracao_bling_eco_estoque
        WHERE expira_em < %s AND consumido_em IS NULL
        """,
        (agora_utc(),),
    )


def eco_deve_ignorar_webhook(
    cur,
    id_tenant: int,
    *,
    id_bling_produto: str,
    id_bling_deposito: str,
    quantidade: int | None,
) -> bool:
    """True se o webhook é eco de operação originada pelo DropNexo."""
    limpar_ecos_expirados(cur)
    cur.execute(
        """
        SELECT id, quantidade_esperada FROM tbl_integracao_bling_eco_estoque
        WHERE id_tenant = %s
          AND id_bling_produto = %s
          AND id_bling_deposito = %s
          AND consumido_em IS NULL
          AND expira_em >= %s
        ORDER BY id DESC
        LIMIT 1
        """,
        (id_tenant, str(id_bling_produto), str(id_bling_deposito), agora_utc()),
    )
    row = cur.fetchone()
    if not row:
        return False
    eco_id, qtd_esperada = row[0], row[1]
    if qtd_esperada is not None and quantidade is not None and int(qtd_esperada) != int(quantidade):
        return False
    cur.execute(
        "UPDATE tbl_integracao_bling_eco_estoque SET consumido_em = %s WHERE id = %s",
        (agora_utc(), eco_id),
    )
    return True
