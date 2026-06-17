# fornecedor/catalogo/servico_estoque_deposito.py — estoque por depósito
from __future__ import annotations

from global_utils import agora_utc


def produto_integrado_bling(cur, id_tenant: int, id_produto: int) -> bool:
    cur.execute(
        """
        SELECT 1 FROM tbl_integracao_map
        WHERE id_tenant = %s AND provedor = 'bling' AND entidade = 'produto'
          AND id_dropnexo = %s
        LIMIT 1
        """,
        (id_tenant, id_produto),
    )
    if cur.fetchone():
        return True
    cur.execute(
        """
        SELECT 1 FROM tbl_produto
        WHERE id = %s AND id_tenant = %s AND origem IN ('integracao', 'arquivo')
        """,
        (id_produto, id_tenant),
    )
    return bool(cur.fetchone())


def id_bling_produto(cur, id_tenant: int, id_produto: int, *, contexto: str = "fornecedor") -> str | None:
    cur.execute(
        """
        SELECT id_bling FROM tbl_integracao_map
        WHERE id_tenant = %s AND provedor = 'bling' AND contexto = %s
          AND entidade = 'produto' AND id_dropnexo = %s
        LIMIT 1
        """,
        (id_tenant, contexto, id_produto),
    )
    row = cur.fetchone()
    return str(row[0]) if row and row[0] else None


def garantir_linhas_estoque_depositos(cur, id_tenant: int, id_variante: int) -> None:
    cur.execute(
        """
        INSERT INTO tbl_produto_estoque_deposito (id_variante, id_deposito, quantidade, atualizado_em)
        SELECT %s, d.id, 0, %s
        FROM tbl_deposito_expedicao d
        WHERE d.id_tenant = %s AND d.ativo = TRUE
          AND NOT EXISTS (
              SELECT 1 FROM tbl_produto_estoque_deposito ped
              WHERE ped.id_variante = %s AND ped.id_deposito = d.id
          )
        """,
        (id_variante, agora_utc(), id_tenant, id_variante),
    )


def sincronizar_total_variante(cur, id_variante: int) -> int:
    cur.execute(
        """
        SELECT COALESCE(SUM(quantidade), 0) FROM tbl_produto_estoque_deposito
        WHERE id_variante = %s
        """,
        (id_variante,),
    )
    total = int(cur.fetchone()[0] or 0)
    agora = agora_utc()
    cur.execute(
        """
        INSERT INTO tbl_produto_variante_estoque (id_variante, quantidade, atualizado_em)
        VALUES (%s, %s, %s)
        ON CONFLICT (id_variante) DO UPDATE SET
            quantidade = EXCLUDED.quantidade, atualizado_em = EXCLUDED.atualizado_em
        """,
        (id_variante, total, agora),
    )
    return total


def listar_estoque_por_deposito(
    cur,
    id_tenant: int,
    id_produto: int,
) -> tuple[int | None, list[dict], bool]:
    cur.execute(
        """
        SELECT id_variante_padrao, formato FROM tbl_produto
        WHERE id = %s AND id_tenant = %s
        """,
        (id_produto, id_tenant),
    )
    row = cur.fetchone()
    if not row:
        return None, [], False
    id_variante, formato = row[0], row[1] or "S"
    if formato == "E":
        return id_variante, [], produto_integrado_bling(cur, id_tenant, id_produto)

    if not id_variante:
        from fornecedor.catalogo.srotas_catalogo import garantir_variante_padrao as _gvp

        id_variante = _gvp(cur, id_produto, id_tenant)

    garantir_linhas_estoque_depositos(cur, id_tenant, id_variante)
    cur.execute(
        """
        SELECT ped.id_deposito, d.nome, ped.quantidade, ped.atualizado_em,
               dm.id_bling_deposito, dm.nome_bling
        FROM tbl_produto_estoque_deposito ped
        JOIN tbl_deposito_expedicao d ON d.id = ped.id_deposito
        LEFT JOIN tbl_integracao_deposito_map dm
            ON dm.id_tenant = %s AND dm.id_deposito_dropnexo = d.id
        WHERE ped.id_variante = %s AND d.id_tenant = %s AND d.ativo = TRUE
        ORDER BY d.principal DESC, d.nome
        """,
        (id_tenant, id_variante, id_tenant),
    )
    itens = []
    for r in cur.fetchall():
        itens.append(
            {
                "id_deposito": r[0],
                "nome": r[1],
                "quantidade": int(r[2] or 0),
                "atualizado_em": r[3].isoformat() if r[3] else None,
                "id_bling_deposito": r[4],
                "nome_bling": r[5],
                "vinculado_bling": bool(r[4]),
            }
        )
    integrado = produto_integrado_bling(cur, id_tenant, id_produto)
    return id_variante, itens, integrado


def atualizar_saldo_deposito(
    cur,
    id_tenant: int,
    *,
    id_produto: int,
    id_deposito: int,
    quantidade: int,
    sincronizar_bling: bool = False,
    contexto: str = "fornecedor",
) -> dict:
    quantidade = max(0, int(quantidade))
    cur.execute(
        """
        SELECT p.id_variante_padrao, p.formato FROM tbl_produto p
        WHERE p.id = %s AND p.id_tenant = %s
        """,
        (id_produto, id_tenant),
    )
    row = cur.fetchone()
    if not row:
        raise ValueError("Produto não encontrado.")
    id_variante, formato = row[0], row[1] or "S"
    if formato == "E":
        raise ValueError("Produto com variações: edite o estoque por SKU na aba Variações.")

    if not id_variante:
        from fornecedor.catalogo.srotas_catalogo import garantir_variante_padrao as _gvp

        id_variante = _gvp(cur, id_produto, id_tenant)

    cur.execute(
        """
        SELECT 1 FROM tbl_deposito_expedicao
        WHERE id = %s AND id_tenant = %s AND ativo = TRUE
        """,
        (id_deposito, id_tenant),
    )
    if not cur.fetchone():
        raise ValueError("Depósito inválido.")

    garantir_linhas_estoque_depositos(cur, id_tenant, id_variante)
    agora = agora_utc()
    cur.execute(
        """
        INSERT INTO tbl_produto_estoque_deposito (id_variante, id_deposito, quantidade, atualizado_em)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (id_variante, id_deposito) DO UPDATE SET
            quantidade = EXCLUDED.quantidade, atualizado_em = EXCLUDED.atualizado_em
        """,
        (id_variante, id_deposito, quantidade, agora),
    )
    total = sincronizar_total_variante(cur, id_variante)

    bling_ok = False
    bling_msg = None
    integrado = produto_integrado_bling(cur, id_tenant, id_produto)
    if sincronizar_bling and integrado:
        from api.bling.sync_estoque import exportar_saldo_deposito_bling

        bling_ok, bling_msg = exportar_saldo_deposito_bling(
            cur,
            id_tenant,
            contexto=contexto,
            id_produto=id_produto,
            id_deposito=id_deposito,
            quantidade=quantidade,
        )

    return {
        "quantidade": quantidade,
        "total_variante": total,
        "integrado_bling": integrado,
        "bling_sincronizado": bling_ok,
        "bling_mensagem": bling_msg,
    }


def sincronizar_estoque_produto_bling(
    cur,
    id_tenant: int,
    id_produto: int,
    *,
    contexto: str = "fornecedor",
) -> tuple[bool, str | None, int]:
    """Importa saldos do Bling para o produto (simples ou variações)."""
    import json

    from api.bling.sync_estoque import importar_estoque_produto_bling

    cur.execute(
        """
        SELECT id_bling, sku, meta FROM tbl_integracao_map
        WHERE id_tenant = %s AND id_dropnexo = %s AND provedor = 'bling'
          AND entidade = 'produto'
        """,
        (id_tenant, id_produto),
    )
    maps = cur.fetchall()
    if not maps:
        return False, "Produto sem vínculo no Bling.", 0

    total = 0
    for id_bling, sku, meta in maps:
        meta_obj = meta if isinstance(meta, dict) else {}
        if isinstance(meta, str):
            try:
                meta_obj = json.loads(meta) or {}
            except json.JSONDecodeError:
                meta_obj = {}
        fmt = str(meta_obj.get("formato") or "").upper()
        id_variante = None
        if fmt == "V":
            cur.execute(
                """
                SELECT id FROM tbl_produto_variante
                WHERE id_produto = %s AND sku IS NOT DISTINCT FROM %s
                LIMIT 1
                """,
                (id_produto, sku),
            )
            vrow = cur.fetchone()
            if not vrow:
                continue
            id_variante = int(vrow[0])
        else:
            cur.execute(
                "SELECT id_variante_padrao FROM tbl_produto WHERE id = %s AND id_tenant = %s",
                (id_produto, id_tenant),
            )
            vrow = cur.fetchone()
            id_variante = int(vrow[0]) if vrow and vrow[0] else None
        if not id_variante:
            continue
        total += importar_estoque_produto_bling(
            cur,
            id_tenant,
            contexto,
            id_produto=id_produto,
            id_variante=id_variante,
            id_bling_override=str(id_bling),
        )
    if total <= 0:
        return False, "Nenhum saldo importado (verifique vínculo de depósitos).", 0
    return True, None, total


def sincronizar_estoque_produtos_bling(
    cur,
    id_tenant: int,
    ids_produto: list[int],
    *,
    contexto: str = "fornecedor",
) -> dict:
    ok = 0
    falhas: list[str] = []
    for pid in ids_produto:
        sucesso, msg, _ = sincronizar_estoque_produto_bling(
            cur, id_tenant, int(pid), contexto=contexto
        )
        if sucesso:
            ok += 1
        else:
            falhas.append(f"#{pid}: {msg or 'falha'}")
    return {"sincronizados": ok, "falhas": falhas, "total": len(ids_produto)}
