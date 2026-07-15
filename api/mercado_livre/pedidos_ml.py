"""Importação de pedidos Mercado Livre → DropNexo (pedido + estoque)."""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from global_utils import agora_utc

_log = logging.getLogger(__name__)


def _pedido_ml_ja_processado(cur, id_tenant: int, id_ml_pedido: str) -> bool:
    try:
        cur.execute(
            """
            SELECT 1 FROM tbl_pedido
            WHERE id_tenant_vendedor = %s AND id_ml_pedido = %s
            LIMIT 1
            """,
            (id_tenant, str(id_ml_pedido)),
        )
        if cur.fetchone():
            return True
    except Exception:
        pass

    cur.execute(
        """
        SELECT id_dropnexo FROM tbl_integracao_map
        WHERE id_tenant = %s AND provedor = 'mercado_livre'
          AND contexto = 'vendedor' AND entidade = 'pedido'
          AND (id_bling = %s OR id_bling LIKE %s)
        LIMIT 1
        """,
        (id_tenant, str(id_ml_pedido), f"{id_ml_pedido}:%"),
    )
    row = cur.fetchone()
    # Marcações antigas (só estoque, id_dropnexo=0) não bloqueiam criação do pedido.
    return bool(row and int(row[0] or 0) > 0)


def _digitos(s: str | None) -> str:
    return re.sub(r"\D+", "", str(s or ""))


def _nome_comprador_ml(buyer: dict) -> str:
    first = (buyer.get("first_name") or "").strip()
    last = (buyer.get("last_name") or "").strip()
    nome = f"{first} {last}".strip()
    if nome:
        return nome
    return (buyer.get("nickname") or "Cliente Mercado Livre").strip()


def _telefone_ml(buyer: dict, shipment: dict | None) -> str:
    for fonte in (buyer, (shipment or {}).get("receiver_address") or {}):
        if not isinstance(fonte, dict):
            continue
        phone = fonte.get("phone") or fonte.get("receiver_phone") or {}
        if isinstance(phone, dict):
            area = str(phone.get("area_code") or "").strip()
            num = str(phone.get("number") or "").strip()
            if num:
                return f"{area}{num}".strip()
        elif phone:
            return str(phone).strip()
    return ""


def _documento_ml(buyer: dict, order: dict) -> str:
    billing = buyer.get("billing_info") or {}
    if isinstance(billing, dict):
        doc = billing.get("doc_number")
        if not doc:
            ident_b = billing.get("identification") or {}
            if isinstance(ident_b, dict):
                doc = ident_b.get("number")
        if doc:
            return _digitos(str(doc))
    ident = buyer.get("identification") or {}
    if isinstance(ident, dict) and ident.get("number"):
        return _digitos(str(ident["number"]))
    taxes = order.get("taxes") or {}
    if isinstance(taxes, dict):
        return _digitos(str(taxes.get("id") or ""))
    return ""


def _entrega_de_shipment(shipment: dict | None) -> dict[str, str]:
    if not isinstance(shipment, dict):
        return {}
    dest = shipment.get("destination") if isinstance(shipment.get("destination"), dict) else {}
    addr = (
        shipment.get("receiver_address")
        or (dest.get("shipping_address") if dest else None)
        or {}
    )
    if not isinstance(addr, dict):
        return {}
    city = addr.get("city") or {}
    state = addr.get("state") or {}
    neighborhood = addr.get("neighborhood") or {}
    cidade = city.get("name") if isinstance(city, dict) else str(addr.get("city") or "")
    uf_raw = ""
    if isinstance(state, dict):
        uf_raw = str(state.get("id") or state.get("name") or "")
    else:
        uf_raw = str(addr.get("state") or "")
    bairro = ""
    if isinstance(neighborhood, dict):
        bairro = str(neighborhood.get("name") or "")
    elif isinstance(addr.get("neighborhood"), str):
        bairro = addr.get("neighborhood") or ""
    return {
        "cep": _digitos(addr.get("zip_code") or addr.get("zipCode")),
        "logradouro": (addr.get("street_name") or addr.get("address_line") or "").strip()[:200],
        "numero": str(addr.get("street_number") or "S/N")[:40],
        "complemento": (addr.get("comment") or "").strip()[:120],
        "bairro": bairro.strip()[:120],
        "cidade": str(cidade or "").strip()[:120],
        "uf": uf_raw.replace("BR-", "").strip()[:2].upper(),
    }


def parse_pedido_ml(order: dict, shipment: dict | None = None) -> dict[str, Any]:
    """Extrai cliente, entrega e itens de um order ML (+ shipment opcional)."""
    buyer = order.get("buyer") or {}
    if not isinstance(buyer, dict):
        buyer = {}

    itens: list[dict] = []
    for order_item in order.get("order_items") or []:
        if not isinstance(order_item, dict):
            continue
        item = order_item.get("item") or {}
        if not isinstance(item, dict):
            item = {}
        ml_item_id = str(item.get("id") or "").strip()
        qtd = int(order_item.get("quantity") or 0)
        if not ml_item_id or qtd <= 0:
            continue
        sku = (item.get("seller_sku") or item.get("seller_custom_field") or "").strip()
        preco = float(order_item.get("unit_price") or order_item.get("full_unit_price") or 0)
        itens.append(
            {
                "ml_item_id": ml_item_id,
                "sku": sku,
                "nome": (item.get("title") or "").strip(),
                "quantidade": qtd,
                "preco_venda": preco,
            }
        )

    frete = 0.0
    payments = order.get("payments") or []
    if isinstance(payments, list):
        for pay in payments:
            if isinstance(pay, dict) and (pay.get("status") or "").lower() == "approved":
                frete = float(pay.get("shipping_cost") or 0) or frete
    if frete <= 0 and isinstance(shipment, dict):
        opt = shipment.get("shipping_option") or {}
        frete = float(
            (opt.get("cost") if isinstance(opt, dict) else 0) or shipment.get("base_cost") or 0
        )

    return {
        "numero_ml": str(order.get("id") or ""),
        "cliente": {
            "nome": _nome_comprador_ml(buyer),
            "email": (buyer.get("email") or "").strip() or None,
            "telefone": _telefone_ml(buyer, shipment) or None,
            "documento": _documento_ml(buyer, order) or None,
        },
        "entrega": _entrega_de_shipment(shipment),
        "itens": itens,
        "valor_frete": frete if frete > 0 else 0.0,
        "observacoes": "",
        "total_ml": float(order.get("total_amount") or 0),
    }


def _buscar_shipment_ml(cur, id_tenant: int, order: dict) -> dict | None:
    from api.mercado_livre.mercado_livre import api_request

    shipping = order.get("shipping") or {}
    ship_id = shipping.get("id") if isinstance(shipping, dict) else None
    if not ship_id:
        return None
    try:
        data = api_request(cur, id_tenant, "GET", f"/shipments/{ship_id}")
        return data if isinstance(data, dict) else None
    except RuntimeError as e:
        _log.info("Shipment ML %s indisponível: %s", ship_id, e)
        return None


def _resolver_itens_variante(cur, id_tenant: int, dados: dict) -> dict:
    from api.mercado_livre.sync_runtime import _variante_por_ml_item

    resolvidos: list[dict] = []
    ignorados = 0
    for raw in dados.get("itens") or []:
        ml_item_id = str(raw.get("ml_item_id") or "").strip()
        id_variante = _variante_por_ml_item(cur, id_tenant, ml_item_id) if ml_item_id else None
        if not id_variante:
            ignorados += 1
            continue
        resolvidos.append({**raw, "id_variante": int(id_variante)})
    out = dict(dados)
    out["itens"] = resolvidos
    out["itens_ignorados"] = ignorados
    return out


def sincronizar_cancelamento_pedido_ml(
    cur,
    id_tenant: int,
    id_ml_pedido: str,
    *,
    motivo: str | None = None,
) -> dict[str, Any]:
    """Cancela pedidos DropNexo ligados a um pedido ML (cancelamento/devolução)."""
    from core.pedidos.servico import cancelar_pedido, listar_pedidos_por_id_ml

    id_ml = str(id_ml_pedido or "").strip()
    if not id_ml:
        return {"ok": False, "cancelado": False, "motivo": "id_invalido"}

    ids = listar_pedidos_por_id_ml(cur, int(id_tenant), id_ml)
    if not ids:
        return {
            "ok": True,
            "cancelado": False,
            "motivo": "pedido_local_nao_encontrado",
            "id_ml_pedido": id_ml,
        }

    motivo_txt = (motivo or "Pedido cancelado/devolvido no Mercado Livre.").strip()
    cancelados: list[int] = []
    erros: list[str] = []
    for pid in ids:
        try:
            cancelar_pedido(
                cur,
                int(pid),
                id_vendedor=int(id_tenant),
                motivo=motivo_txt,
                forcar_canal=True,
            )
            cancelados.append(int(pid))
        except Exception as e:
            erros.append(f"#{pid}: {str(e)[:120]}")
            _log.warning("Cancelamento ML pedido local %s: %s", pid, e)

    return {
        "ok": True,
        "cancelado": bool(cancelados),
        "importado": False,
        "id_ml_pedido": id_ml,
        "ids_pedido": cancelados,
        "erros": erros[:5],
        "motivo": "cancelado_ml" if cancelados else "falha_cancelar",
    }


def _importar_um_pedido_ml(cur, id_tenant: int, id_ml_pedido: str) -> dict[str, Any]:
    from api.mercado_livre.mercado_livre import api_request
    from core.pedidos.servico import importar_pedido_ml

    id_ml = str(id_ml_pedido or "").strip()
    if not id_ml:
        return {"importado": False, "motivo": "id_invalido"}

    try:
        pedido = api_request(cur, id_tenant, "GET", f"/orders/{id_ml}")
    except RuntimeError as e:
        return {"importado": False, "motivo": "erro_api", "mensagem": str(e)[:200]}

    if not isinstance(pedido, dict):
        return {"importado": False, "motivo": "resposta_invalida"}

    status = (pedido.get("status") or "").lower()
    if status in ("cancelled", "canceled"):
        return sincronizar_cancelamento_pedido_ml(
            cur, id_tenant, id_ml, motivo="Pedido cancelado no Mercado Livre."
        )

    if _pedido_ml_ja_processado(cur, id_tenant, id_ml):
        ship = _buscar_shipment_ml(cur, id_tenant, pedido)
        ship_id = (ship or {}).get("id") if isinstance(ship, dict) else None
        if not ship_id and isinstance(pedido.get("shipping"), dict):
            ship_id = (pedido.get("shipping") or {}).get("id")
        if ship_id:
            from core.pedidos.servico import listar_pedidos_por_id_ml, salvar_id_ml_shipment

            for pid in listar_pedidos_por_id_ml(cur, int(id_tenant), id_ml):
                salvar_id_ml_shipment(cur, int(pid), ship_id)
        return {
            "importado": False,
            "motivo": "ja_importado",
            "id_ml_pedido": id_ml,
            "id_ml_shipment": ship_id,
        }

    if status not in ("paid", "confirmed"):
        return {"importado": False, "motivo": "status_nao_pago", "status": status}

    shipment = _buscar_shipment_ml(cur, id_tenant, pedido)
    dados = _resolver_itens_variante(cur, id_tenant, parse_pedido_ml(pedido, shipment))
    if not dados.get("itens"):
        return {
            "importado": False,
            "motivo": "sem_match",
            "ignorados": dados.get("itens_ignorados") or 0,
        }

    try:
        ids = importar_pedido_ml(cur, id_tenant, id_ml, dados)
    except Exception as e:
        _log.exception("Falha ao criar pedido ML %s", id_ml)
        return {"importado": False, "motivo": "erro_criar", "mensagem": str(e)[:250]}

    if not ids:
        return {"importado": False, "motivo": "ja_importado"}

    ship_id = None
    if isinstance(shipment, dict) and shipment.get("id"):
        ship_id = shipment.get("id")
    elif isinstance(pedido.get("shipping"), dict):
        ship_id = (pedido.get("shipping") or {}).get("id")
    if ship_id:
        from core.pedidos.servico import salvar_id_ml_shipment

        for pid in ids:
            salvar_id_ml_shipment(cur, int(pid), ship_id)

    cur.execute(
        """
        INSERT INTO tbl_integracao_map (
            id_tenant, provedor, contexto, entidade, id_bling, id_dropnexo, sku, meta, atualizado_em
        ) VALUES (%s, 'mercado_livre', 'vendedor', 'pedido', %s, %s, NULL, %s::jsonb, %s)
        ON CONFLICT (id_tenant, provedor, contexto, entidade, id_bling)
        DO UPDATE SET id_dropnexo = EXCLUDED.id_dropnexo,
                      meta = EXCLUDED.meta,
                      atualizado_em = EXCLUDED.atualizado_em
        """,
        (
            id_tenant,
            id_ml,
            int(ids[0]),
            json.dumps(
                {
                    "ids_pedido": ids,
                    "status": status,
                    "total": pedido.get("total_amount"),
                    "id_ml_shipment": ship_id,
                },
                ensure_ascii=False,
            ),
            agora_utc(),
        ),
    )

    return {
        "importado": True,
        "id_ml_pedido": id_ml,
        "ids_pedido": ids,
        "itens": len(dados["itens"]),
        "ignorados": dados.get("itens_ignorados") or 0,
        "id_ml_shipment": ship_id,
    }


def importar_pedido_ml_por_id(cur, id_tenant: int, id_ml_pedido: str) -> dict[str, Any]:
    return _importar_um_pedido_ml(cur, int(id_tenant), str(id_ml_pedido))


def importar_pedidos_mercado_livre(cur, id_tenant: int, *, dias: int = 7) -> dict:
    from api.mercado_livre.mercado_livre import api_request, carregar_config_ml

    cfg = carregar_config_ml(cur, id_tenant)
    ml_user_id = cfg.get("ml_user_id")
    if not ml_user_id:
        raise RuntimeError("Perfil Mercado Livre sem user_id. Reconecte a conta.")

    desde = datetime.now(timezone.utc) - timedelta(days=max(1, min(dias, 60)))
    base_params = {
        "seller": ml_user_id,
        "sort": "date_desc",
        "order.date_created.from": desde.strftime("%Y-%m-%dT%H:%M:%S.000-00:00"),
        "limit": 50,
    }

    ids: list[str] = []
    for st in ("paid", "cancelled"):
        params = {**base_params, "order.status": st}
        try:
            data = api_request(cur, id_tenant, "GET", "/orders/search", params=params)
        except RuntimeError as e:
            if st == "paid":
                raise
            _log.info("Busca pedidos ML cancelados: %s", e)
            continue
        resultados = data.get("results") or []
        for o in resultados:
            if isinstance(o, dict) and o.get("id"):
                sid = str(o.get("id"))
                if sid not in ids:
                    ids.append(sid)

    importados = 0
    cancelados = 0
    ignorados = 0
    erros: list[str] = []
    ids_pedidos: list[int] = []

    for id_ml in ids:
        try:
            res = _importar_um_pedido_ml(cur, id_tenant, id_ml)
            if res.get("importado"):
                importados += 1
                ids_pedidos.extend(int(x) for x in (res.get("ids_pedido") or []))
            elif res.get("cancelado"):
                cancelados += 1
                ids_pedidos.extend(int(x) for x in (res.get("ids_pedido") or []))
            else:
                ignorados += 1
                if res.get("motivo") == "erro_criar" and res.get("mensagem"):
                    erros.append(f"#{id_ml}: {res['mensagem']}")
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
        f"{importados} pedido(s) do Mercado Livre criado(s) em Pedidos. "
        f"{cancelados} cancelamento(s) sincronizado(s). "
        f"{ignorados} ignorado(s)."
    )
    if erros:
        msg += f" {len(erros)} erro(s)."

    return {
        "message": msg,
        "total_encontrados": len(ids),
        "importados": importados,
        "cancelados": cancelados,
        "ignorados": ignorados,
        "ids_pedido": ids_pedidos[:20],
        "detalhes_erros": erros[:5],
    }


def _tenant_por_ml_user(cur, ml_user_id: int | str) -> int | None:
    try:
        uid = int(ml_user_id)
    except (TypeError, ValueError):
        return None
    cur.execute(
        """
        SELECT id_tenant FROM tbl_integracao_mercado_livre
        WHERE ml_user_id = %s AND status = 'conectado'
        LIMIT 1
        """,
        (uid,),
    )
    row = cur.fetchone()
    return int(row[0]) if row and row[0] else None


def processar_webhook_pedido_ml(cur, payload: dict) -> dict[str, Any]:
    """Processa notificações ML: orders_v2, shipments e claims (cancel/import)."""
    topic = (payload.get("topic") or payload.get("type") or "").strip().lower()
    resource = str(payload.get("resource") or "").strip()
    user_id = payload.get("user_id") or payload.get("user_id_aplicacion")

    id_tenant = _tenant_por_ml_user(cur, user_id) if user_id else None
    if not id_tenant:
        return {"ok": False, "motivo": "tenant_nao_encontrado", "user_id": user_id}

    from api.mercado_livre.mercado_livre import carregar_config_ml

    cfg = carregar_config_ml(cur, int(id_tenant))
    if not cfg.get("conectado"):
        return {"ok": False, "motivo": "ml_desconectado"}

    if topic in ("shipments", "shipment"):
        return _processar_webhook_shipment_ml(cur, int(id_tenant), resource, payload)

    if topic in ("claims", "post_purchase", "claim"):
        return _processar_webhook_claim_ml(cur, int(id_tenant), resource, payload)

    if topic and topic not in ("orders_v2", "orders", "created_orders", "payments"):
        return {"ok": True, "ignorado": True, "motivo": f"topic_{topic}"}

    id_ml = None
    m = re.search(r"/orders/(\d+)", resource)
    if m:
        id_ml = m.group(1)
    if not id_ml:
        id_ml = str(payload.get("id") or "").strip() or None
    if not id_ml:
        return {"ok": True, "ignorado": True, "motivo": "sem_order_id"}

    # Cancelamento sempre sincroniza; importação nova respeita o flag.
    from api.mercado_livre.mercado_livre import api_request

    try:
        pedido = api_request(cur, int(id_tenant), "GET", f"/orders/{id_ml}")
    except RuntimeError as e:
        return {"ok": False, "motivo": "erro_api", "mensagem": str(e)[:200]}

    status = (pedido.get("status") or "").lower() if isinstance(pedido, dict) else ""
    if status in ("cancelled", "canceled"):
        res = sincronizar_cancelamento_pedido_ml(
            cur, int(id_tenant), str(id_ml), motivo="Pedido cancelado no Mercado Livre."
        )
        return {"ok": True, "id_tenant": id_tenant, **res}

    if not cfg.get("pedidos_importar_auto"):
        return {"ok": True, "ignorado": True, "motivo": "importacao_auto_desligada"}

    res = _importar_um_pedido_ml(cur, int(id_tenant), str(id_ml))
    return {"ok": True, "id_tenant": id_tenant, **res}


def _processar_webhook_shipment_ml(
    cur, id_tenant: int, resource: str, payload: dict
) -> dict[str, Any]:
    from api.mercado_livre.mercado_livre import api_request

    ship_id = None
    m = re.search(r"/shipments/(\d+)", resource)
    if m:
        ship_id = m.group(1)
    if not ship_id:
        ship_id = str(payload.get("id") or "").strip() or None
    if not ship_id:
        return {"ok": True, "ignorado": True, "motivo": "sem_shipment_id"}

    try:
        ship = api_request(cur, id_tenant, "GET", f"/shipments/{ship_id}")
    except RuntimeError as e:
        return {"ok": False, "motivo": "erro_api_shipment", "mensagem": str(e)[:200]}

    if not isinstance(ship, dict):
        return {"ok": True, "ignorado": True, "motivo": "shipment_invalido"}

    st = (ship.get("status") or "").lower()
    order_id = ship.get("order_id") or ship.get("order_id")
    if not order_id:
        orders = ship.get("order_ids") or []
        if isinstance(orders, list) and orders:
            order_id = orders[0]

    if st in ("cancelled", "canceled") and order_id:
        res = sincronizar_cancelamento_pedido_ml(
            cur,
            id_tenant,
            str(order_id),
            motivo="Envio cancelado no Mercado Livre.",
        )
        return {"ok": True, "topic": "shipments", **res}

    if order_id:
        from core.pedidos.servico import listar_pedidos_por_id_ml, salvar_id_ml_shipment

        for pid in listar_pedidos_por_id_ml(cur, id_tenant, str(order_id)):
            salvar_id_ml_shipment(cur, int(pid), ship_id)

    return {
        "ok": True,
        "topic": "shipments",
        "id_ml_shipment": ship_id,
        "status": st,
        "order_id": order_id,
    }


def _processar_webhook_claim_ml(
    cur, id_tenant: int, resource: str, payload: dict
) -> dict[str, Any]:
    """Devolução/reclamação: cancela pedido local quando o claim aponta para order."""
    from api.mercado_livre.mercado_livre import api_request

    claim_id = None
    m = re.search(r"/claims/(\d+)", resource) or re.search(r"/claims/(\d+)", str(payload.get("resource") or ""))
    if m:
        claim_id = m.group(1)
    if not claim_id:
        claim_id = str(payload.get("id") or "").strip() or None
    if not claim_id:
        return {"ok": True, "ignorado": True, "motivo": "sem_claim_id"}

    claim = None
    for path in (
        f"/post-purchase/v1/claims/{claim_id}",
        f"/claims/{claim_id}",
    ):
        try:
            claim = api_request(cur, id_tenant, "GET", path)
            if isinstance(claim, dict):
                break
        except RuntimeError:
            continue

    if not isinstance(claim, dict):
        return {"ok": True, "ignorado": True, "motivo": "claim_indisponivel", "claim_id": claim_id}

    order_id = claim.get("resource_id") or claim.get("order_id")
    if not order_id:
        resource_data = claim.get("resource") or ""
        m2 = re.search(r"/orders/(\d+)", str(resource_data))
        if m2:
            order_id = m2.group(1)

    tipo = (claim.get("type") or claim.get("stage") or "").lower()
    status_claim = (claim.get("status") or "").lower()
    # Devolução / cancelamento / mediations relevantes
    acionar = any(
        x in f"{tipo} {status_claim}"
        for x in ("return", "cancel", "refund", "mediations", "dispute", "claim")
    )
    if not order_id or not acionar:
        return {
            "ok": True,
            "ignorado": True,
            "motivo": "claim_sem_acao",
            "claim_id": claim_id,
            "type": tipo,
            "status": status_claim,
        }

    res = sincronizar_cancelamento_pedido_ml(
        cur,
        id_tenant,
        str(order_id),
        motivo=f"Reclamação/devolução no Mercado Livre (claim {claim_id}).",
    )
    return {"ok": True, "topic": "claims", "claim_id": claim_id, **res}


def _resolver_shipment_id_pedido(cur, id_tenant: int, ped: dict) -> str | None:
    ship_id = ped.get("id_ml_shipment")
    if ship_id:
        return str(ship_id)
    id_ml = ped.get("id_ml_pedido")
    if not id_ml:
        return None
    from api.mercado_livre.mercado_livre import api_request

    try:
        order = api_request(cur, id_tenant, "GET", f"/orders/{id_ml}")
    except RuntimeError:
        return None
    if not isinstance(order, dict):
        return None
    shipping = order.get("shipping") or {}
    if isinstance(shipping, dict) and shipping.get("id"):
        return str(shipping.get("id"))
    ship = _buscar_shipment_ml(cur, id_tenant, order)
    if isinstance(ship, dict) and ship.get("id"):
        return str(ship.get("id"))
    return None


def exportar_status_pedido_ml(cur, id_pedido: int, *, evento: str) -> bool:
    """
    Empurra expedido/entregue do DropNexo para o ML.
    - frete custom / not_specified: PUT /shipments/{id} com tracking + status
    - ME1/ME2: POST /shipments/{id}/seller_notifications (best-effort no ME2)
    """
    from api.mercado_livre.mercado_livre import api_request, carregar_config_ml, ml_conectado
    from core.pedidos.servico import obter_pedido, salvar_id_ml_shipment

    ped = obter_pedido(cur, int(id_pedido))
    if not ped or (ped.get("origem") or "") != "mercado_livre":
        return False

    id_tenant = int(ped["id_tenant_vendedor"])
    if not ml_conectado(cur, id_tenant):
        return False

    cfg = carregar_config_ml(cur, id_tenant)
    if not cfg.get("conectado"):
        return False

    evento_l = (evento or "").strip().lower()
    if evento_l not in ("expedido", "entregue"):
        return False

    ship_id = _resolver_shipment_id_pedido(cur, id_tenant, ped)
    if not ship_id:
        _log.info("ML status: pedido %s sem shipment", id_pedido)
        return False

    salvar_id_ml_shipment(cur, int(id_pedido), ship_id)

    try:
        ship = api_request(cur, id_tenant, "GET", f"/shipments/{ship_id}")
    except RuntimeError as e:
        _log.warning("ML GET shipment %s: %s", ship_id, e)
        return False

    mode = ""
    if isinstance(ship, dict):
        mode = str(ship.get("mode") or "").lower()
        if not mode and isinstance(ship.get("logistic"), dict):
            mode = str((ship.get("logistic") or {}).get("mode") or "").lower()

    tracking = (ped.get("codigo_rastreio") or "").strip() or None
    status_ml = "shipped" if evento_l == "expedido" else "delivered"

    try:
        if mode in ("custom", "not_specified"):
            body: dict[str, Any] = {"status": status_ml}
            if tracking:
                body["tracking_number"] = tracking
            api_request(cur, id_tenant, "PUT", f"/shipments/{ship_id}", json_body=body)
        else:
            notif: dict[str, Any] = {"status": status_ml, "substatus": None}
            if tracking:
                notif["tracking_number"] = tracking
            api_request(
                cur,
                id_tenant,
                "POST",
                f"/shipments/{ship_id}/seller_notifications",
                json_body=notif,
            )
        _log.info(
            "ML status pedido %s → %s (shipment %s, mode=%s)",
            id_pedido,
            status_ml,
            ship_id,
            mode or "?",
        )
        return True
    except RuntimeError as e:
        # ME2 frequentemente rejeita seller_notifications — não quebra o fluxo local.
        _log.warning(
            "ML export status pedido %s (evento=%s, mode=%s): %s",
            id_pedido,
            evento_l,
            mode,
            e,
        )
        return False


def baixar_etiqueta_ml(
    cur,
    id_vendedor: int,
    id_pedido: int,
    pasta_destino,
    *,
    id_usuario: int | None = None,
) -> dict[str, Any]:
    """Baixa PDF da etiqueta Mercado Envios e grava como anexo do pedido."""
    from pathlib import Path

    from api.mercado_livre.mercado_livre import api_request_bytes, ml_conectado
    from core.pedidos.servico import (
        listar_anexos_pedido,
        obter_pedido,
        registrar_anexo_pedido,
        salvar_id_ml_shipment,
    )

    ped = obter_pedido(cur, int(id_pedido), id_vendedor=int(id_vendedor))
    if not ped:
        raise ValueError("Pedido não encontrado.")
    if (ped.get("origem") or "") != "mercado_livre":
        raise ValueError("Pedido não é do Mercado Livre.")
    if not ml_conectado(cur, int(id_vendedor)):
        raise ValueError("Mercado Livre não conectado.")

    ship_id = _resolver_shipment_id_pedido(cur, int(id_vendedor), ped)
    if not ship_id:
        raise ValueError("Shipment do Mercado Livre não encontrado para este pedido.")

    salvar_id_ml_shipment(cur, int(id_pedido), ship_id)

    # Evita duplicar se já baixamos a mesma etiqueta com o mesmo nome-base.
    existentes = listar_anexos_pedido(cur, int(id_pedido), id_vendedor=int(id_vendedor))
    nome_sugerido = f"etiqueta_ml_{ship_id}.pdf"
    for a in existentes:
        if a.get("tipo") == "etiqueta" and (a.get("nome_original") or "") == nome_sugerido:
            return {
                "message": "Etiqueta ML já anexada.",
                "anexo": a,
                "id_ml_shipment": ship_id,
                "ja_existia": True,
            }

    content = None
    last_err = None
    for params in (
        {"shipment_ids": ship_id, "response_type": "pdf"},
        {"shipment_ids": ship_id, "savePdf": "Y"},
    ):
        try:
            content = api_request_bytes(
                cur, int(id_vendedor), "GET", "/shipment_labels", params=params
            )
            if content:
                break
        except RuntimeError as e:
            last_err = e
            content = None

    if not content:
        raise ValueError(
            str(last_err)
            if last_err
            else "Etiqueta indisponível. No ML ela costuma liberar em ready_to_ship."
        )

    # ZIP (zpl/pdf bundle) — grava como .zip se magic ZIP
    pasta = Path(pasta_destino)
    pasta.mkdir(parents=True, exist_ok=True)
    is_zip = content[:2] == b"PK"
    ext = ".zip" if is_zip else ".pdf"
    nome_arquivo = f"etiqueta_ml_{ship_id}{ext}"
    destino = pasta / f"{id_pedido}_etiqueta_{int(datetime.now(timezone.utc).timestamp())}{ext}"
    destino.write_bytes(content)

    caminho_db = f"upload/tenant{id_vendedor}/pedidos/{destino.name}"
    anexo = registrar_anexo_pedido(
        cur,
        int(id_vendedor),
        int(id_pedido),
        "etiqueta",
        nome_arquivo if is_zip else nome_sugerido,
        caminho_db,
        len(content),
        id_usuario=id_usuario,
    )
    return {
        "message": "Etiqueta Mercado Livre baixada.",
        "anexo": anexo,
        "id_ml_shipment": ship_id,
        "ja_existia": False,
    }
