# api/bling/depositos.py — pareamento e consulta de depósitos Bling
from __future__ import annotations

from global_utils import agora_utc


def listar_mapa_depositos(cur, id_tenant: int) -> list[dict]:
    cur.execute(
        """
        SELECT dm.id, dm.id_bling_deposito, dm.nome_bling, dm.id_deposito_dropnexo, d.nome
        FROM tbl_integracao_deposito_map dm
        LEFT JOIN tbl_deposito_expedicao d ON d.id = dm.id_deposito_dropnexo
        WHERE dm.id_tenant = %s
        ORDER BY dm.nome_bling NULLS LAST, dm.id_bling_deposito
        """,
        (id_tenant,),
    )
    out = []
    for r in cur.fetchall():
        out.append(
            {
                "id": r[0],
                "id_bling_deposito": r[1],
                "nome_bling": r[2] or "",
                "id_deposito_dropnexo": r[3],
                "nome_dropnexo": r[4] or "",
            }
        )
    return out


def resolver_deposito_dropnexo(cur, id_tenant: int, id_bling_deposito: str) -> int | None:
    cur.execute(
        """
        SELECT id_deposito_dropnexo FROM tbl_integracao_deposito_map
        WHERE id_tenant = %s AND id_bling_deposito = %s AND id_deposito_dropnexo IS NOT NULL
        LIMIT 1
        """,
        (id_tenant, str(id_bling_deposito)),
    )
    row = cur.fetchone()
    return int(row[0]) if row and row[0] else None


def salvar_vinculo_deposito(
    cur,
    id_tenant: int,
    *,
    id_bling_deposito: str,
    nome_bling: str | None,
    id_deposito_dropnexo: int | None,
) -> int:
    id_bling = str(id_bling_deposito).strip()
    if not id_bling:
        raise ValueError("Depósito Bling inválido.")
    if id_deposito_dropnexo:
        cur.execute(
            """
            SELECT 1 FROM tbl_deposito_expedicao
            WHERE id = %s AND id_tenant = %s AND ativo = TRUE
            """,
            (id_deposito_dropnexo, id_tenant),
        )
        if not cur.fetchone():
            raise ValueError("Depósito DropNexo inválido.")

    cur.execute(
        """
        INSERT INTO tbl_integracao_deposito_map (
            id_tenant, id_bling_deposito, nome_bling, id_deposito_dropnexo, atualizado_em
        ) VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (id_tenant, id_bling_deposito) DO UPDATE SET
            nome_bling = EXCLUDED.nome_bling,
            id_deposito_dropnexo = EXCLUDED.id_deposito_dropnexo,
            atualizado_em = EXCLUDED.atualizado_em
        RETURNING id
        """,
        (id_tenant, id_bling, (nome_bling or "").strip() or None, id_deposito_dropnexo, agora_utc()),
    )
    return int(cur.fetchone()[0])


def sincronizar_depositos_bling_api(cur, id_tenant: int, depositos_bling: list[dict]) -> int:
    """Garante registros no mapa para cada depósito retornado pela API (sem vínculo)."""
    n = 0
    for dep in depositos_bling:
        id_b = str(dep.get("id") or "")
        if not id_b:
            continue
        nome = (dep.get("descricao") or dep.get("nome") or "").strip()
        cur.execute(
            """
            INSERT INTO tbl_integracao_deposito_map (id_tenant, id_bling_deposito, nome_bling, atualizado_em)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (id_tenant, id_bling_deposito) DO UPDATE SET
                nome_bling = COALESCE(EXCLUDED.nome_bling, tbl_integracao_deposito_map.nome_bling),
                atualizado_em = EXCLUDED.atualizado_em
            """,
            (id_tenant, id_b, nome or None, agora_utc()),
        )
        n += 1
    return n
