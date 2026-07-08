# api/mercado_livre/sync_pedidos.py — importação de pedidos ML (fase inicial)
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from api.mercado_livre.cliente import api_request, carregar_config_ml


def importar_pedidos_mercado_livre(cur, id_tenant: int, *, dias: int = 7) -> dict:
    """
    Lista pedidos pagos recentes no ML e prepara importação.
    A gravação em tbl_pedido (origem mercado_livre) será expandida na próxima etapa.
    """
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
    ids = [str(o.get("id")) for o in resultados if o.get("id")]

    return {
        "message": (
            f"{len(ids)} pedido(s) pago(s) encontrado(s) nos últimos {dias} dia(s). "
            "A importação automática para DropNexo será habilitada na próxima etapa."
        ),
        "total_encontrados": len(ids),
        "ids_amostra": ids[:10],
        "importados": 0,
        "ignorados": len(ids),
    }
