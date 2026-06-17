# api/bling/sync_estoque.py — importação/exportação de estoque por depósito
from __future__ import annotations

from api.bling.cliente import api_request, listar_depositos_bling, obter_saldos_estoque
from api.bling.depositos import resolver_deposito_dropnexo, sincronizar_depositos_bling_api
from fornecedor.catalogo.servico_estoque_deposito import (
    garantir_linhas_estoque_depositos,
    sincronizar_total_variante,
)
from global_utils import agora_utc


def _estoque_modo_permite_importar(cur, id_tenant: int, contexto: str) -> bool:
    cur.execute(
        """
        SELECT estoque_modo FROM tbl_integracao_bling_config
        WHERE id_tenant = %s AND contexto = %s AND ativo = TRUE
        """,
        (id_tenant, contexto),
    )
    row = cur.fetchone()
    if not row:
        return True
    return (row[0] or "importar") in ("importar", "atualizar")


def importar_estoque_produto_bling(
    cur,
    id_tenant: int,
    contexto: str,
    *,
    id_produto: int,
    id_variante: int,
    id_bling_override: str | None = None,
) -> int:
    if not _estoque_modo_permite_importar(cur, id_tenant, contexto):
        return 0
    id_bling = (id_bling_override or "").strip() or None
    if not id_bling:
        from fornecedor.catalogo.servico_estoque_deposito import id_bling_produto as buscar_id_bling

        id_bling = buscar_id_bling(cur, id_tenant, id_produto, contexto=contexto)
    if not id_bling:
        return 0

    try:
        saldos = obter_saldos_estoque(id_tenant, id_bling)
    except Exception:
        return 0

    garantir_linhas_estoque_depositos(cur, id_tenant, id_variante)
    atualizados = 0
    agora = agora_utc()
    depositos = saldos.get("depositos") or []
    if not isinstance(depositos, list):
        depositos = []

    for dep in depositos:
        if not isinstance(dep, dict):
            continue
        id_bling_dep = str(dep.get("id") or (dep.get("deposito") or {}).get("id") or "")
        if not id_bling_dep:
            continue
        id_dep_drop = resolver_deposito_dropnexo(cur, id_tenant, id_bling_dep)
        if not id_dep_drop:
            continue
        qtd = dep.get("saldoFisico")
        if qtd is None:
            qtd = dep.get("saldoVirtual")
        if qtd is None:
            qtd = dep.get("quantidade")
        try:
            quantidade = max(0, int(float(qtd or 0)))
        except (TypeError, ValueError):
            quantidade = 0
        cur.execute(
            """
            INSERT INTO tbl_produto_estoque_deposito (id_variante, id_deposito, quantidade, atualizado_em)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (id_variante, id_deposito) DO UPDATE SET
                quantidade = EXCLUDED.quantidade, atualizado_em = EXCLUDED.atualizado_em
            """,
            (id_variante, id_dep_drop, quantidade, agora),
        )
        atualizados += 1

    if atualizados:
        sincronizar_total_variante(cur, id_variante)
    return atualizados


def exportar_saldo_deposito_bling(
    cur,
    id_tenant: int,
    *,
    contexto: str,
    id_produto: int,
    id_deposito: int,
    quantidade: int,
    id_bling_override: str | None = None,
) -> tuple[bool, str | None]:
    cur.execute(
        """
        SELECT estoque_modo FROM tbl_integracao_bling_config
        WHERE id_tenant = %s AND contexto = %s AND ativo = TRUE
        """,
        (id_tenant, contexto),
    )
    row = cur.fetchone()
    modo = (row[0] or "importar") if row else "importar"
    if modo not in ("exportar", "atualizar"):
        return False, "Modo de estoque não permite exportar ao Bling."

    from fornecedor.catalogo.servico_estoque_deposito import id_bling_produto as buscar_id_bling

    id_bling = id_bling_override or buscar_id_bling(cur, id_tenant, id_produto, contexto=contexto)
    if not id_bling:
        return False, "Produto sem vínculo no Bling."

    cur.execute(
        """
        SELECT id_bling_deposito FROM tbl_integracao_deposito_map
        WHERE id_tenant = %s AND id_deposito_dropnexo = %s
        LIMIT 1
        """,
        (id_tenant, id_deposito),
    )
    row = cur.fetchone()
    if not row or not row[0]:
        return False, "Depósito não vinculado ao Bling."

    id_bling_dep = str(row[0])
    try:
        api_request(
            id_tenant,
            "POST",
            "/estoques",
            json_body={
                "produto": {"id": int(id_bling)},
                "deposito": {"id": int(id_bling_dep)},
                "operacao": "B",
                "quantidade": max(0, int(quantidade)),
                "observacoes": "Ajuste via DropNexo",
            },
        )
        return True, None
    except Exception as e:
        return False, str(e)


def sincronizar_depositos_tenant(cur, id_tenant: int) -> int:
    depositos = listar_depositos_bling(id_tenant)
    return sincronizar_depositos_bling_api(cur, id_tenant, depositos)
