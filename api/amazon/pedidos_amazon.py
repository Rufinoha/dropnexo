"""Importação de pedidos Amazon → DropNexo."""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from global_utils import agora_utc

_log = logging.getLogger(__name__)

_STATUS_IMPORTAVEIS = frozenset(
    {
        "unshipped",
        "partiallyshipped",
        "shipped",
        "invoiceunconfirmed",
        "pending",
    }
)
_STATUS_CANCELADO = frozenset({"canceled", "cancelled"})


def _digitos(s: str | None) -> str:
    return re.sub(r"\D+", "", str(s or ""))


def _pedido_amazon_ja_processado(cur, id_tenant: int, id_amazon_pedido: str) -> bool:
    try:
        cur.execute(
            """
            SELECT 1 FROM tbl_pedido
            WHERE id_tenant_vendedor = %s AND id_amazon_pedido = %s
            LIMIT 1
            """,
            (id_tenant, str(id_amazon_pedido)),
        )
        if cur.fetchone():
            return True
    except Exception:
        pass

    cur.execute(
        """
        SELECT id_dropnexo FROM tbl_integracao_map
        WHERE id_tenant = %s AND provedor = 'amazon'
          AND contexto = 'vendedor' AND entidade = 'pedido'
          AND (id_bling = %s OR id_bling LIKE %s)
        LIMIT 1
        """,
        (id_tenant, str(id_amazon_pedido), f"{id_amazon_pedido}:%"),
    )
    row = cur.fetchone()
    return bool(row and int(row[0] or 0) > 0)


def _entrega_de_endereco(addr: dict | None) -> dict[str, str]:
    if not isinstance(addr, dict):
        return {}
    return {
        "cep": _digitos(addr.get("PostalCode") or addr.get("postalCode")),
        "logradouro": (addr.get("AddressLine1") or addr.get("Name") or "").strip()[:200],
        "numero": str(addr.get("AddressLine2") or "S/N")[:40],
        "complemento": (addr.get("AddressLine3") or "").strip()[:120],
        "bairro": "",
        "cidade": str(addr.get("City") or "")[:120],
        "uf": str(addr.get("StateOrRegion") or addr.get("State") or "")[:2].upper(),
    }


def parse_pedido_amazon(order: dict, order_items: list | None = None) -> dict[str, Any]:
    """Extrai cliente, entrega e itens de um pedido Amazon."""
    shipping = order.get("ShippingAddress") or {}
    if not isinstance(shipping, dict):
        shipping = {}

    buyer_info_raw = order.get("BuyerInfo") or {}
    if not isinstance(buyer_info_raw, dict):
        buyer_info_raw = {}
    buyer_name = (
        (shipping.get("Name") or "").strip()
        or (buyer_info_raw.get("BuyerName") or "").strip()
        or "Cliente Amazon"
    )

    buyer_email = (buyer_info_raw.get("BuyerEmail") or "").strip()

    itens: list[dict] = []
    raw_items = order_items if order_items is not None else (order.get("OrderItems") or [])
    for line in raw_items or []:
        if not isinstance(line, dict):
            continue
        qtd = int(line.get("QuantityOrdered") or line.get("QuantityShipped") or 0)
        if qtd <= 0:
            continue
        sku = (line.get("SellerSKU") or line.get("seller_sku") or "").strip()
        asin = (line.get("ASIN") or "").strip()
        preco = 0.0
        item_price = line.get("ItemPrice") or {}
        if isinstance(item_price, dict):
            try:
                preco = float(item_price.get("Amount") or 0)
            except (TypeError, ValueError):
                preco = 0.0
        itens.append(
            {
                "asin": asin,
                "sku": sku,
                "nome": (line.get("Title") or "").strip(),
                "quantidade": qtd,
                "preco_venda": preco,
                "order_item_id": str(line.get("OrderItemId") or ""),
            }
        )

    frete = 0.0
    for line in raw_items or []:
        if not isinstance(line, dict):
            continue
        ship = line.get("ShippingPrice") or {}
        if isinstance(ship, dict):
            try:
                frete += float(ship.get("Amount") or 0)
            except (TypeError, ValueError):
                pass

    total = 0.0
    order_total = order.get("OrderTotal") or {}
    if isinstance(order_total, dict):
        try:
            total = float(order_total.get("Amount") or 0)
        except (TypeError, ValueError):
            total = 0.0

    return {
        "numero_amazon": str(order.get("AmazonOrderId") or order.get("amazon_order_id") or ""),
        "cliente": {
            "nome": str(buyer_name)[:200],
            "email": buyer_email or None,
            "telefone": _digitos(shipping.get("Phone")) or None,
            "documento": None,
        },
        "entrega": _entrega_de_endereco(shipping),
        "itens": itens,
        "valor_frete": frete if frete > 0 else 0.0,
        "observacoes": "",
        "total_amazon": total,
        "fulfillment_channel": (order.get("FulfillmentChannel") or "").strip(),
    }


def _resolver_itens_variante(cur, id_tenant: int, dados: dict) -> dict:
    from api.amazon.sync_runtime import variante_por_amazon_sku

    resolvidos: list[dict] = []
    ignorados = 0
    for raw in dados.get("itens") or []:
        sku = str(raw.get("sku") or "").strip()
        asin = str(raw.get("asin") or "").strip()
        id_variante = variante_por_amazon_sku(cur, id_tenant, sku, asin)
        if not id_variante and sku:
            cur.execute(
                """
                SELECT id_dropnexo FROM tbl_integracao_map
                WHERE id_tenant = %s AND provedor = 'amazon' AND contexto = 'vendedor'
                  AND entidade = 'produto' AND sku = %s
                LIMIT 1
                """,
                (id_tenant, sku),
            )
            row = cur.fetchone()
            id_variante = int(row[0]) if row and row[0] else None
        if not id_variante:
            ignorados += 1
            continue
        resolvidos.append({**raw, "id_variante": int(id_variante)})
    out = dict(dados)
    out["itens"] = resolvidos
    out["itens_ignorados"] = ignorados
    return out


def sincronizar_cancelamento_pedido_amazon(
    cur,
    id_tenant: int,
    id_amazon_pedido: str,
    *,
    motivo: str | None = None,
) -> dict[str, Any]:
    from core.pedidos.servico import cancelar_pedido, listar_pedidos_por_id_amazon

    id_amz = str(id_amazon_pedido or "").strip()
    if not id_amz:
        return {"ok": False, "cancelado": False, "motivo": "id_invalido"}

    ids = listar_pedidos_por_id_amazon(cur, int(id_tenant), id_amz)
    if not ids:
        return {
            "ok": True,
            "cancelado": False,
            "motivo": "pedido_local_nao_encontrado",
            "id_amazon_pedido": id_amz,
        }

    motivo_txt = (motivo or "Pedido cancelado na Amazon.").strip()
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
            _log.warning("Cancelamento Amazon pedido local %s: %s", pid, e)

    return {
        "ok": True,
        "cancelado": bool(cancelados),
        "importado": False,
        "id_amazon_pedido": id_amz,
        "ids_pedido": cancelados,
        "erros": erros[:5],
        "motivo": "cancelado_amazon" if cancelados else "falha_cancelar",
    }


def _buscar_itens_pedido(cur, id_tenant: int, order_id: str) -> list[dict]:
    from api.amazon.amazon import api_request

    try:
        data = api_request(
            cur,
            id_tenant,
            "GET",
            f"/orders/v0/orders/{order_id}/orderItems",
        )
    except RuntimeError as e:
        _log.warning("Itens Amazon pedido %s: %s", order_id, e)
        return []
    payload = data.get("payload") if isinstance(data, dict) else None
    if isinstance(payload, dict):
        items = payload.get("OrderItems") or []
        return [i for i in items if isinstance(i, dict)]
    if isinstance(data, dict):
        items = data.get("OrderItems") or []
        return [i for i in items if isinstance(i, dict)]
    return []


def _importar_um_pedido_amazon(cur, id_tenant: int, order: dict) -> dict[str, Any]:
    from api.amazon.eco_estoque import suprimir_sync_amazon
    from core.pedidos.servico import importar_pedido_amazon

    id_amz = str(order.get("AmazonOrderId") or "").strip()
    if not id_amz:
        return {"importado": False, "motivo": "id_invalido"}

    status = (order.get("OrderStatus") or "").strip().lower()
    if status in _STATUS_CANCELADO:
        return sincronizar_cancelamento_pedido_amazon(
            cur, id_tenant, id_amz, motivo="Pedido cancelado na Amazon."
        )

    if _pedido_amazon_ja_processado(cur, id_tenant, id_amz):
        return {
            "importado": False,
            "motivo": "ja_importado",
            "id_amazon_pedido": id_amz,
        }

    if status and status.replace(" ", "") not in _STATUS_IMPORTAVEIS:
        return {"importado": False, "motivo": "status_nao_importavel", "status": status}

    # FBA (AFN) — estoque Amazon; ainda importamos se mapeado
    order_items = _buscar_itens_pedido(cur, id_tenant, id_amz)
    dados = _resolver_itens_variante(cur, id_tenant, parse_pedido_amazon(order, order_items))
    if not dados.get("itens"):
        return {
            "importado": False,
            "motivo": "sem_match",
            "ignorados": dados.get("itens_ignorados") or 0,
        }

    try:
        with suprimir_sync_amazon():
            ids = importar_pedido_amazon(cur, id_tenant, id_amz, dados)
    except Exception as e:
        _log.exception("Falha ao criar pedido Amazon %s", id_amz)
        return {"importado": False, "motivo": "erro_criar", "mensagem": str(e)[:250]}

    if not ids:
        return {"importado": False, "motivo": "ja_importado"}

    cur.execute(
        """
        INSERT INTO tbl_integracao_map (
            id_tenant, provedor, contexto, entidade, id_bling, id_dropnexo, sku, meta, atualizado_em
        ) VALUES (%s, 'amazon', 'vendedor', 'pedido', %s, %s, NULL, %s::jsonb, %s)
        ON CONFLICT (id_tenant, provedor, contexto, entidade, id_bling)
        DO UPDATE SET id_dropnexo = EXCLUDED.id_dropnexo,
                      meta = EXCLUDED.meta,
                      atualizado_em = EXCLUDED.atualizado_em
        """,
        (
            id_tenant,
            id_amz,
            int(ids[0]),
            json.dumps(
                {
                    "ids_pedido": ids,
                    "status": status,
                    "total": dados.get("total_amazon"),
                },
                ensure_ascii=False,
            ),
            agora_utc(),
        ),
    )

    return {
        "importado": True,
        "id_amazon_pedido": id_amz,
        "ids_pedido": ids,
        "itens": len(dados["itens"]),
        "ignorados": dados.get("itens_ignorados") or 0,
    }


def importar_pedidos_amazon(cur, id_tenant: int, *, dias: int = 7) -> dict:
    from api.amazon.amazon import api_request, carregar_config_amazon, marketplace_id_padrao

    cfg = carregar_config_amazon(cur, id_tenant)
    if not cfg.get("conectado"):
        raise RuntimeError("Amazon não conectada.")

    desde = datetime.now(timezone.utc) - timedelta(days=max(1, min(dias, 60)))
    created_after = desde.strftime("%Y-%m-%dT%H:%M:%SZ")
    mp = cfg.get("marketplace_id") or marketplace_id_padrao()

    try:
        data = api_request(
            cur,
            id_tenant,
            "GET",
            "/orders/v0/orders",
            params={
                "MarketplaceIds": mp,
                "CreatedAfter": created_after,
                "OrderStatuses": "Unshipped,PartiallyShipped,Shipped",
            },
        )
    except RuntimeError as e:
        raise RuntimeError(f"Não foi possível buscar pedidos na Amazon: {e}") from e

    payload = data.get("payload") if isinstance(data, dict) else None
    pedidos = []
    if isinstance(payload, dict):
        pedidos = payload.get("Orders") or []
    elif isinstance(data, dict):
        pedidos = data.get("Orders") or []

    importados = 0
    cancelados = 0
    ignorados = 0
    erros: list[str] = []
    ids_pedidos: list[int] = []

    for ped in pedidos:
        if not isinstance(ped, dict):
            continue
        id_amz = str(ped.get("AmazonOrderId") or "").strip()
        try:
            res = _importar_um_pedido_amazon(cur, id_tenant, ped)
            if res.get("importado"):
                importados += 1
                ids_pedidos.extend(int(x) for x in (res.get("ids_pedido") or []))
            elif res.get("cancelado"):
                cancelados += 1
                ids_pedidos.extend(int(x) for x in (res.get("ids_pedido") or []))
            else:
                ignorados += 1
                if res.get("motivo") == "erro_criar" and res.get("mensagem"):
                    erros.append(f"#{id_amz}: {res['mensagem']}")
        except Exception as e:
            erros.append(f"#{id_amz}: {str(e)[:120]}")
            ignorados += 1

    agora = agora_utc()
    cur.execute(
        """
        UPDATE tbl_integracao_amazon
        SET ultima_sync_pedidos = %s, atualizado_em = %s
        WHERE id_tenant = %s
        """,
        (agora, agora, id_tenant),
    )

    msg = (
        f"{importados} pedido(s) da Amazon criado(s) em Pedidos. "
        f"{cancelados} cancelamento(s) sincronizado(s). "
        f"{ignorados} ignorado(s)."
    )
    if erros:
        msg += f" {len(erros)} erro(s)."

    return {
        "message": msg,
        "total_encontrados": len(pedidos),
        "importados": importados,
        "cancelados": cancelados,
        "ignorados": ignorados,
        "ids_pedido": ids_pedidos[:20],
        "detalhes_erros": erros[:5],
    }


def exportar_status_pedido_amazon(cur, id_pedido: int, *, evento: str) -> bool:
    """Empurra expedido/entregue do DropNexo para a Amazon (best-effort)."""
    from api.amazon.amazon import amazon_conectado, api_request, carregar_config_amazon
    from core.pedidos.servico import _enriquecer_pedido_expedicao, obter_pedido

    ped = obter_pedido(cur, int(id_pedido))
    if not ped or (ped.get("origem") or "") != "amazon":
        return False

    id_tenant = int(ped["id_tenant_vendedor"])
    if not amazon_conectado(cur, id_tenant):
        return False

    cfg = carregar_config_amazon(cur, id_tenant)
    if not cfg.get("conectado"):
        return False

    evento_l = (evento or "").strip().lower()
    if evento_l not in ("expedido", "entregue"):
        return False

    _enriquecer_pedido_expedicao(cur, int(id_pedido), ped)
    order_id = ped.get("id_amazon_pedido")
    tracking = (ped.get("codigo_rastreio") or "").strip()
    transportadora = (ped.get("transportadora") or "").strip() or "Other"

    if not order_id:
        _log.info("Amazon status: pedido %s sem id_amazon_pedido", id_pedido)
        return False

    try:
        if evento_l == "expedido":
            # confirmShipment / updateShipmentStatus — best-effort
            body: dict[str, Any] = {
                "marketplaceId": cfg.get("marketplace_id"),
                "cod": False,
            }
            if tracking:
                body["packageDetail"] = {
                    "packageReferenceId": str(id_pedido),
                    "carrierCode": transportadora[:40],
                    "trackingNumber": tracking,
                    "shipDate": agora_utc().strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "orderItems": [],
                }
            try:
                api_request(
                    cur,
                    id_tenant,
                    "POST",
                    f"/orders/v0/orders/{order_id}/shipmentConfirmation",
                    json_body=body,
                )
            except RuntimeError:
                # Fallback: updateShipmentStatus
                api_request(
                    cur,
                    id_tenant,
                    "POST",
                    f"/orders/v0/orders/{order_id}/shipment",
                    json_body={
                        "marketplaceId": cfg.get("marketplace_id"),
                        "shipmentStatus": "Shipped",
                    },
                )
        else:
            _log.info(
                "Amazon status entregue pedido %s — sem endpoint dedicado; ignorado.",
                id_pedido,
            )
            return False
        _log.info(
            "Amazon status pedido %s → %s (order %s)",
            id_pedido,
            evento_l,
            order_id,
        )
        return True
    except RuntimeError as e:
        _log.warning(
            "Amazon export status pedido %s (evento=%s): %s",
            id_pedido,
            evento_l,
            e,
        )
        return False
    except Exception as e:
        _log.warning(
            "Amazon export status pedido %s (best-effort falhou): %s",
            id_pedido,
            e,
        )
        return False
