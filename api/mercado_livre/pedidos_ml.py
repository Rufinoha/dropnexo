"""Importação de pedidos Mercado Livre → DropNexo (estoque local)."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from api.mercado_livre.eco_estoque import suprimir_sync_ml
from api.mercado_livre.sync_runtime import _variante_por_ml_item, baixar_estoque_pedido_ml
from global_utils import agora_utc

_log = logging.getLogger(__name__)


def _pedido_ml_ja_processado(cur, id_tenant: int, id_ml_pedido: str) -> bool:
    cur.execute(
        """
        SELECT 1 FROM tbl_integracao_map
        WHERE id_tenant = %s AND provedor = 'mercado_livre'
          AND contexto = 'vendedor' AND entidade = 'pedido' AND id_bling = %s
        LIMIT 1
        """,
        (id_tenant, str(id_ml_pedido)),
    )
    if cur.fetchone():
        return True
    cur.execute(
        """
        SELECT 1 FROM tbl_pedido
        WHERE id_tenant_vendedor = %s AND id_ml_pedido = %s
        LIMIT 1
        """,
        (id_tenant, str(id_ml_pedido)),
    )
    return bool(cur.fetchone())


def _marcar_pedido_ml_processado(cur, id_tenant: int, id_ml_pedido: str, meta: dict) -> None:
    cur.execute(
        """
        INSERT INTO tbl_integracao_map (
            id_tenant, provedor, contexto, entidade, id_bling, id_dropnexo, sku, meta, atualizado_em
        ) VALUES (%s, 'mercado_livre', 'vendedor', 'pedido', %s, 0, NULL, %s::jsonb, %s)
        ON CONFLICT (id_tenant, provedor, contexto, entidade, id_bling)
        DO UPDATE SET meta = EXCLUDED.meta, atualizado_em = EXCLUDED.atualizado_em
        """,
        (
            id_tenant,
            str(id_ml_pedido),
            json.dumps(meta, ensure_ascii=False),
            agora_utc(),
        ),
    )


def _importar_um_pedido_ml(cur, id_tenant: int, id_ml_pedido: str) -> dict[str, Any]:
    from api.mercado_livre.mercado_livre import api_request

    id_ml = str(id_ml_pedido or "").strip()
    if not id_ml:
        return {"importado": False, "motivo": "id_invalido"}

    if _pedido_ml_ja_processado(cur, id_tenant, id_ml):
        return {"importado": False, "motivo": "ja_importado"}

    try:
        pedido = api_request(cur, id_tenant, "GET", f"/orders/{id_ml}")
    except RuntimeError as e:
        return {"importado": False, "motivo": "erro_api", "mensagem": str(e)[:200]}

    if not isinstance(pedido, dict):
        return {"importado": False, "motivo": "resposta_invalida"}

    status = (pedido.get("status") or "").lower()
    if status not in ("paid", "confirmed"):
        return {"importado": False, "motivo": "status_nao_pago", "status": status}

    itens_ajustados: list[dict] = []
    ignorados = 0

    with suprimir_sync_ml():
        for order_item in pedido.get("order_items") or []:
            if not isinstance(order_item, dict):
                ignorados += 1
                continue
            item = order_item.get("item") or {}
            ml_item_id = str(item.get("id") or "").strip()
            qtd = int(order_item.get("quantity") or 0)
            if not ml_item_id or qtd <= 0:
                ignorados += 1
                continue
            id_variante = _variante_por_ml_item(cur, id_tenant, ml_item_id)
            if not id_variante:
                ignorados += 1
                continue
            baixar_estoque_pedido_ml(cur, id_tenant, id_variante, qtd)
            itens_ajustados.append(
                {
                    "id_variante": id_variante,
                    "ml_item_id": ml_item_id,
                    "quantidade": qtd,
                }
            )

    if not itens_ajustados:
        return {"importado": False, "motivo": "sem_match", "ignorados": ignorados}

    _marcar_pedido_ml_processado(
        cur,
        id_tenant,
        id_ml,
        {
            "itens": itens_ajustados,
            "status": status,
            "total": pedido.get("total_amount"),
        },
    )
    return {
        "importado": True,
        "id_ml_pedido": id_ml,
        "itens": len(itens_ajustados),
        "ignorados": ignorados,
    }


def importar_pedidos_mercado_livre(cur, id_tenant: int, *, dias: int = 7) -> dict:
    from api.mercado_livre.mercado_livre import api_request, carregar_config_ml

    cfg = carregar_config_ml(cur, id_tenant)
    ml_user_id = cfg.get("ml_user_id")
    if not ml_user_id:
        raise RuntimeError("Perfil Mercado Livre sem user_id. Reconecte a conta.")

    desde = datetime.now(timezone.utc) - timedelta(days=max(1, min(dias, 60)))
    params = {
        "seller": ml_user_id,
        "order.status": "paid",
        "sort": "date_desc",
        "order.date_created.from": desde.strftime("%Y-%m-%dT%H:%M:%S.000-00:00"),
        "limit": 50,
    }
    data = api_request(cur, id_tenant, "GET", "/orders/search", params=params)
    resultados = data.get("results") or []
    ids = [str(o.get("id")) for o in resultados if isinstance(o, dict) and o.get("id")]

    importados = 0
    ignorados = 0
    erros: list[str] = []

    for id_ml in ids:
        try:
            res = _importar_um_pedido_ml(cur, id_tenant, id_ml)
            if res.get("importado"):
                importados += 1
            else:
                ignorados += 1
        except Exception as e:
            erros.append(f"#{id_ml}: {str(e)[:120]}")
            ignorados += 1

    agora = agora_utc()
    cur.execute(
        """
        UPDATE tbl_integracao_mercado_livre
        SET ultima_sync_pedidos = %s, atualizado_em = %s
        WHERE id_tenant = %s
        """,
        (agora, agora, id_tenant),
    )

    msg = (
        f"{importados} pedido(s) importado(s) — estoque atualizado no DropNexo. "
        f"{ignorados} ignorado(s)."
    )
    if erros:
        msg += f" {len(erros)} erro(s)."

    return {
        "message": msg,
        "total_encontrados": len(ids),
        "importados": importados,
        "ignorados": ignorados,
        "detalhes_erros": erros[:5],
    }
