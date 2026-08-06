"""Importação de pedidos TikTok Shop → DropNexo."""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from global_utils import agora_utc

_log = logging.getLogger(__name__)

_STATUS_PAGO = frozenset(
    {
        "awaiting_shipment",
        "awaiting_collection",
        "in_transit",
        "delivered",
        "completed",
        "paid",
        "processing",
    }
)
_STATUS_CANCELADO = frozenset(
    {"cancelled", "canceled", "cancel", "closed", "refunded", "returned"}
)


def _digitos(s: str | None) -> str:
    return re.sub(r"\D+", "", str(s or ""))


def _pedido_tiktok_ja_processado(cur, id_tenant: int, id_tiktok_pedido: str) -> bool:
    try:
        cur.execute(
            """
            SELECT 1 FROM tbl_pedido
            WHERE id_tenant_vendedor = %s AND id_tiktok_pedido = %s
            LIMIT 1
            """,
            (id_tenant, str(id_tiktok_pedido)),
        )
        if cur.fetchone():
            return True
    except Exception:
        pass

    cur.execute(
        """
        SELECT id_dropnexo FROM tbl_integracao_map
        WHERE id_tenant = %s AND provedor = 'tiktok'
          AND contexto = 'vendedor' AND entidade = 'pedido'
          AND (id_bling = %s OR id_bling LIKE %s)
        LIMIT 1
        """,
        (id_tenant, str(id_tiktok_pedido), f"{id_tiktok_pedido}:%"),
    )
    row = cur.fetchone()
    return bool(row and int(row[0] or 0) > 0)


def _entrega_de_endereco(addr: dict | None) -> dict[str, str]:
    if not isinstance(addr, dict):
        return {}
    district = addr.get("district_info") or addr.get("district") or {}
    if not isinstance(district, dict):
        district = {}
    return {
        "cep": _digitos(addr.get("postal_code") or addr.get("zipcode") or addr.get("zip_code")),
        "logradouro": (addr.get("address_line1") or addr.get("full_address") or addr.get("address") or "").strip()[:200],
        "numero": str(addr.get("address_line2") or addr.get("house_number") or "S/N")[:40],
        "complemento": (addr.get("address_line3") or addr.get("address_detail") or "").strip()[:120],
        "bairro": str(district.get("address_level3") or addr.get("district") or "")[:120],
        "cidade": str(district.get("address_level2") or addr.get("city") or "")[:120],
        "uf": str(district.get("address_level1") or addr.get("state") or "")[:2].upper(),
    }


def parse_pedido_tiktok(order: dict) -> dict[str, Any]:
    """Extrai cliente, entrega e itens de um pedido TikTok Shop."""
    recipient = order.get("recipient_address") or order.get("shipping_address") or {}
    if not isinstance(recipient, dict):
        recipient = {}

    buyer = order.get("buyer_info") or order.get("buyer") or {}
    if not isinstance(buyer, dict):
        buyer = {}

    nome = (
        (recipient.get("name") or "").strip()
        or (buyer.get("name") or buyer.get("buyer_name") or "").strip()
        or "Cliente TikTok Shop"
    )

    itens: list[dict] = []
    for line in order.get("line_items") or order.get("item_list") or []:
        if not isinstance(line, dict):
            continue
        product_id = str(line.get("product_id") or "").strip()
        sku_id = str(line.get("sku_id") or line.get("skuId") or "").strip()
        qtd = int(line.get("quantity") or line.get("sku_count") or 0)
        if qtd <= 0:
            continue
        sku = (line.get("seller_sku") or line.get("sku_name") or "").strip()
        preco = float(
            line.get("sale_price")
            or line.get("original_price")
            or line.get("sku_sale_price")
            or 0
        )
        itens.append(
            {
                "product_id": product_id,
                "sku_id": sku_id,
                "sku": sku,
                "nome": (line.get("product_name") or line.get("sku_name") or "").strip(),
                "quantidade": qtd,
                "preco_venda": preco,
            }
        )

    packages = order.get("packages") or order.get("package_list") or []
    package_id = ""
    if isinstance(packages, list) and packages:
        pkg = packages[0]
        if isinstance(pkg, dict):
            package_id = str(pkg.get("id") or pkg.get("package_id") or "")

    payment = order.get("payment") or {}
    frete = 0.0
    if isinstance(payment, dict):
        frete = float(payment.get("shipping_fee") or payment.get("shipping_amount") or 0)

    return {
        "numero_tiktok": str(order.get("id") or order.get("order_id") or ""),
        "package_id": package_id,
        "cliente": {
            "nome": nome,
            "email": (buyer.get("email") or "").strip() or None,
            "telefone": _digitos(recipient.get("phone") or buyer.get("phone") or "") or None,
            "documento": _digitos(recipient.get("tax_id") or buyer.get("tax_id") or "") or None,
        },
        "entrega": _entrega_de_endereco(recipient),
        "itens": itens,
        "valor_frete": frete if frete > 0 else 0.0,
        "observacoes": "",
        "total_tiktok": float(order.get("payment_total") or order.get("total_amount") or 0),
    }


def _resolver_itens_variante(cur, id_tenant: int, dados: dict) -> dict:
    from api.tiktok.sync_runtime import variante_por_tiktok_sku

    resolvidos: list[dict] = []
    ignorados = 0
    for raw in dados.get("itens") or []:
        product_id = str(raw.get("product_id") or "").strip()
        sku_id = str(raw.get("sku_id") or "").strip()
        id_variante = variante_por_tiktok_sku(cur, id_tenant, product_id, sku_id)
        if not id_variante and raw.get("sku"):
            cur.execute(
                """
                SELECT id_dropnexo FROM tbl_integracao_map
                WHERE id_tenant = %s AND provedor = 'tiktok' AND contexto = 'vendedor'
                  AND entidade = 'produto' AND sku = %s
                LIMIT 1
                """,
                (id_tenant, str(raw.get("sku")).strip()),
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


def sincronizar_cancelamento_pedido_tiktok(
    cur,
    id_tenant: int,
    id_tiktok_pedido: str,
    *,
    motivo: str | None = None,
) -> dict[str, Any]:
    from core.pedidos.servico import cancelar_pedido, listar_pedidos_por_id_tiktok

    id_tt = str(id_tiktok_pedido or "").strip()
    if not id_tt:
        return {"ok": False, "cancelado": False, "motivo": "id_invalido"}

    ids = listar_pedidos_por_id_tiktok(cur, int(id_tenant), id_tt)
    if not ids:
        return {
            "ok": True,
            "cancelado": False,
            "motivo": "pedido_local_nao_encontrado",
            "id_tiktok_pedido": id_tt,
        }

    motivo_txt = (motivo or "Pedido cancelado/devolvido no TikTok Shop.").strip()
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
            _log.warning("Cancelamento TikTok pedido local %s: %s", pid, e)

    return {
        "ok": True,
        "cancelado": bool(cancelados),
        "importado": False,
        "id_tiktok_pedido": id_tt,
        "ids_pedido": cancelados,
        "erros": erros[:5],
        "motivo": "cancelado_tiktok" if cancelados else "falha_cancelar",
    }


def sincronizar_status_pedido_tiktok_inbound(
    cur,
    id_tenant: int,
    id_tiktok_pedido: str,
    *,
    status_tt: str | None = None,
    package_id: str | None = None,
    id_usuario: int | None = None,
) -> dict[str, Any]:
    """Avança status no DropNexo a partir do status TikTok (nunca regride)."""
    from core.pedidos.servico import listar_pedidos_por_id_tiktok, salvar_id_tiktok_package
    from core.pedidos.status_integracao import (
        STATUS_CANCELADO,
        aplicar_status_avancado,
        mapear_status_tiktok_para_dn,
    )

    id_tt = str(id_tiktok_pedido or "").strip()
    if not id_tt:
        return {"ok": False, "avancados": 0, "motivo": "id_invalido"}

    ids = listar_pedidos_por_id_tiktok(cur, int(id_tenant), id_tt)
    if not ids:
        return {
            "ok": True,
            "avancados": 0,
            "motivo": "pedido_local_nao_encontrado",
            "id_tiktok_pedido": id_tt,
        }

    # Se só veio o id, busca status atual na API
    st = (status_tt or "").strip().lower()
    pkg = (package_id or "").strip() or None
    if not st:
        try:
            from api.tiktok.tiktok import api_request

            data = api_request(
                cur,
                int(id_tenant),
                "GET",
                "/order/202309/orders",
                params={"ids": id_tt},
            )
            pedidos = []
            if isinstance(data, dict):
                pedidos = data.get("orders") or data.get("order_list") or []
            elif isinstance(data, list):
                pedidos = data
            pedido = pedidos[0] if pedidos else None
            if isinstance(pedido, dict):
                st = str(pedido.get("status") or pedido.get("order_status") or "").lower()
                if not pkg:
                    dados = parse_pedido_tiktok(pedido)
                    pkg = (dados.get("package_id") or "").strip() or None
        except Exception as e:
            _log.debug("TikTok status inbound API %s: %s", id_tt, e)

    novo = mapear_status_tiktok_para_dn(st)
    if not novo:
        # ainda pode gravar package_id
        if pkg:
            for pid in ids:
                salvar_id_tiktok_package(cur, int(pid), pkg)
        return {
            "ok": True,
            "avancados": 0,
            "motivo": "status_nao_mapeado",
            "status_tiktok": st,
            "id_tiktok_pedido": id_tt,
        }

    if novo == STATUS_CANCELADO:
        return sincronizar_cancelamento_pedido_tiktok(
            cur,
            int(id_tenant),
            id_tt,
            motivo=f"Status TikTok Shop: {st or 'cancelado'}.",
        )

    avancados: list[int] = []
    for pid in ids:
        if pkg:
            salvar_id_tiktok_package(cur, int(pid), pkg)
        if aplicar_status_avancado(
            cur,
            int(pid),
            novo,
            id_usuario=id_usuario,
            origem_evento="tiktok",
            detalhe=f"Status sincronizado do TikTok Shop ({st or novo}).",
        ):
            avancados.append(int(pid))

    return {
        "ok": True,
        "avancados": len(avancados),
        "ids_pedido": avancados,
        "status_tiktok": st,
        "status_dropnexo": novo,
        "id_tiktok_pedido": id_tt,
        "motivo": "status_avancado" if avancados else "sem_mudanca",
    }


def _importar_um_pedido_tiktok(cur, id_tenant: int, id_tiktok_pedido: str) -> dict[str, Any]:
    from api.tiktok.tiktok import api_request
    from core.pedidos.servico import importar_pedido_tiktok, salvar_id_tiktok_package

    id_tt = str(id_tiktok_pedido or "").strip()
    if not id_tt:
        return {"importado": False, "motivo": "id_invalido"}

    try:
        data = api_request(
            cur,
            id_tenant,
            "GET",
            "/order/202309/orders",
            params={"ids": id_tt},
        )
    except RuntimeError as e:
        return {"importado": False, "motivo": "erro_api", "mensagem": str(e)[:200]}

    pedidos = []
    if isinstance(data, dict):
        pedidos = data.get("orders") or data.get("order_list") or []
    elif isinstance(data, list):
        pedidos = data
    pedido = pedidos[0] if pedidos else None
    if not isinstance(pedido, dict):
        return {"importado": False, "motivo": "resposta_invalida"}

    status = (pedido.get("status") or pedido.get("order_status") or "").lower()
    if status in _STATUS_CANCELADO:
        return sincronizar_cancelamento_pedido_tiktok(
            cur, id_tenant, id_tt, motivo="Pedido cancelado no TikTok Shop."
        )

    if _pedido_tiktok_ja_processado(cur, id_tenant, id_tt):
        dados_parse = parse_pedido_tiktok(pedido)
        pkg = dados_parse.get("package_id")
        sync = sincronizar_status_pedido_tiktok_inbound(
            cur,
            id_tenant,
            id_tt,
            status_tt=status,
            package_id=pkg,
        )
        return {
            "importado": False,
            "motivo": "ja_importado",
            "id_tiktok_pedido": id_tt,
            "id_tiktok_package": pkg,
            "status_sync": sync,
        }

    if status and status not in _STATUS_PAGO:
        return {"importado": False, "motivo": "status_nao_pago", "status": status}

    dados = _resolver_itens_variante(cur, id_tenant, parse_pedido_tiktok(pedido))
    if not dados.get("itens"):
        return {
            "importado": False,
            "motivo": "sem_match",
            "ignorados": dados.get("itens_ignorados") or 0,
        }

    try:
        ids = importar_pedido_tiktok(cur, id_tenant, id_tt, dados)
    except Exception as e:
        _log.exception("Falha ao criar pedido TikTok %s", id_tt)
        return {"importado": False, "motivo": "erro_criar", "mensagem": str(e)[:250]}

    if not ids:
        return {"importado": False, "motivo": "ja_importado"}

    pkg = dados.get("package_id")
    if pkg:
        for pid in ids:
            salvar_id_tiktok_package(cur, int(pid), pkg)

    cur.execute(
        """
        INSERT INTO tbl_integracao_map (
            id_tenant, provedor, contexto, entidade, id_bling, id_dropnexo, sku, meta, atualizado_em
        ) VALUES (%s, 'tiktok', 'vendedor', 'pedido', %s, %s, NULL, %s::jsonb, %s)
        ON CONFLICT (id_tenant, provedor, contexto, entidade, id_bling)
        DO UPDATE SET id_dropnexo = EXCLUDED.id_dropnexo,
                      meta = EXCLUDED.meta,
                      atualizado_em = EXCLUDED.atualizado_em
        """,
        (
            id_tenant,
            id_tt,
            int(ids[0]),
            json.dumps(
                {
                    "ids_pedido": ids,
                    "status": status,
                    "total": pedido.get("payment_total") or pedido.get("total_amount"),
                    "id_tiktok_package": pkg,
                },
                ensure_ascii=False,
            ),
            agora_utc(),
        ),
    )

    return {
        "importado": True,
        "id_tiktok_pedido": id_tt,
        "ids_pedido": ids,
        "itens": len(dados["itens"]),
        "ignorados": dados.get("itens_ignorados") or 0,
        "id_tiktok_package": pkg,
    }


def importar_pedidos_tiktok(cur, id_tenant: int, *, dias: int = 7) -> dict:
    from api.tiktok.tiktok import api_request, carregar_config_tiktok

    cfg = carregar_config_tiktok(cur, id_tenant)
    if not cfg.get("conectado"):
        raise RuntimeError("TikTok Shop não conectado.")

    desde = datetime.now(timezone.utc) - timedelta(days=max(1, min(dias, 60)))
    create_time_ge = int(desde.timestamp())

    try:
        data = api_request(
            cur,
            id_tenant,
            "POST",
            "/order/202309/orders/search",
            json_body={
                "page_size": 50,
                "sort_field": "create_time",
                "sort_order": "DESC",
                "create_time_ge": create_time_ge,
            },
        )
    except RuntimeError as e:
        raise RuntimeError(f"Não foi possível buscar pedidos no TikTok Shop: {e}") from e

    ids: list[str] = []
    pedidos = []
    if isinstance(data, dict):
        pedidos = data.get("orders") or data.get("order_list") or []
    for ped in pedidos:
        if isinstance(ped, dict):
            oid = str(ped.get("id") or ped.get("order_id") or "").strip()
            if oid and oid not in ids:
                ids.append(oid)

    importados = 0
    cancelados = 0
    ignorados = 0
    erros: list[str] = []
    ids_pedidos: list[int] = []

    for id_tt in ids:
        try:
            res = _importar_um_pedido_tiktok(cur, id_tenant, id_tt)
            if res.get("importado"):
                importados += 1
                ids_pedidos.extend(int(x) for x in (res.get("ids_pedido") or []))
            elif res.get("cancelado"):
                cancelados += 1
                ids_pedidos.extend(int(x) for x in (res.get("ids_pedido") or []))
            else:
                ignorados += 1
                if res.get("motivo") == "erro_criar" and res.get("mensagem"):
                    erros.append(f"#{id_tt}: {res['mensagem']}")
        except Exception as e:
            erros.append(f"#{id_tt}: {str(e)[:120]}")
            ignorados += 1

    agora = agora_utc()
    cur.execute(
        """
        UPDATE tbl_integracao_tiktok
        SET ultima_sync_pedidos = %s, atualizado_em = %s
        WHERE id_tenant = %s
        """,
        (agora, agora, id_tenant),
    )

    msg = (
        f"{importados} pedido(s) do TikTok Shop criado(s) em Pedidos. "
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


def _tenant_por_shop(cur, shop_id: str | None = None, shop_cipher: str | None = None) -> int | None:
    if shop_id:
        cur.execute(
            """
            SELECT id_tenant FROM tbl_integracao_tiktok
            WHERE shop_id = %s AND status = 'conectado'
            LIMIT 1
            """,
            (str(shop_id),),
        )
        row = cur.fetchone()
        if row and row[0]:
            return int(row[0])
    if shop_cipher:
        cur.execute(
            """
            SELECT id_tenant FROM tbl_integracao_tiktok
            WHERE shop_cipher = %s AND status = 'conectado'
            LIMIT 1
            """,
            (str(shop_cipher),),
        )
        row = cur.fetchone()
        if row and row[0]:
            return int(row[0])
    return None


def processar_webhook_tiktok(cur, payload: dict) -> dict[str, Any]:
    """Processa webhook TikTok Shop: status de pedido, cancelamento e devolução."""
    if not isinstance(payload, dict):
        return {"ok": False, "motivo": "payload_invalido"}

    shop_id = payload.get("shop_id") or payload.get("shopId")
    shop_cipher = payload.get("shop_cipher") or payload.get("shopCipher")
    id_tenant = _tenant_por_shop(cur, shop_id, shop_cipher)
    if not id_tenant:
        return {"ok": False, "motivo": "tenant_nao_encontrado", "shop_id": shop_id}

    from api.tiktok.tiktok import carregar_config_tiktok

    cfg = carregar_config_tiktok(cur, int(id_tenant))
    if not cfg.get("conectado"):
        return {"ok": False, "motivo": "tiktok_desconectado"}

    tipo = (
        payload.get("type")
        or payload.get("event_type")
        or payload.get("notification_type")
        or ""
    )
    tipo_l = str(tipo).lower()

    data = payload.get("data") or payload.get("content") or payload
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except (TypeError, ValueError, json.JSONDecodeError):
            data = {}
    if not isinstance(data, dict):
        data = {}

    order_id = str(
        data.get("order_id")
        or data.get("orderId")
        or payload.get("order_id")
        or payload.get("orderId")
        or ""
    ).strip()

    status = str(data.get("order_status") or data.get("status") or "").lower()
    package_id = str(
        data.get("package_id") or data.get("packageId") or ""
    ).strip() or None

    if any(x in tipo_l for x in ("cancel", "return", "refund", "reverse")):
        if order_id:
            res = sincronizar_cancelamento_pedido_tiktok(
                cur,
                int(id_tenant),
                order_id,
                motivo=f"Evento TikTok Shop: {tipo}.",
            )
            return {"ok": True, "id_tenant": id_tenant, **res}
        return {"ok": True, "ignorado": True, "motivo": "cancel_sem_order_id"}

    if not order_id:
        return {"ok": True, "ignorado": True, "motivo": "sem_order_id", "type": tipo}

    # Pedido já existe → avança status (pago / expedição / entregue / cancelado)
    from core.pedidos.servico import listar_pedidos_por_id_tiktok

    if listar_pedidos_por_id_tiktok(cur, int(id_tenant), order_id):
        sync = sincronizar_status_pedido_tiktok_inbound(
            cur,
            int(id_tenant),
            order_id,
            status_tt=status or None,
            package_id=package_id,
        )
        return {"ok": True, "id_tenant": id_tenant, "type": tipo, "status_sync": sync}

    if status in _STATUS_CANCELADO:
        res = sincronizar_cancelamento_pedido_tiktok(
            cur, int(id_tenant), order_id, motivo="Pedido cancelado no TikTok Shop."
        )
        return {"ok": True, "id_tenant": id_tenant, **res}

    if not cfg.get("pedidos_importar_auto"):
        return {"ok": True, "ignorado": True, "motivo": "importacao_auto_desligada"}

    res = _importar_um_pedido_tiktok(cur, int(id_tenant), order_id)
    return {"ok": True, "id_tenant": id_tenant, "type": tipo, **res}


def exportar_status_pedido_tiktok(cur, id_pedido: int, *, evento: str) -> bool:
    """Empurra expedido/entregue do DropNexo para o TikTok Shop (best-effort)."""
    from api.tiktok.tiktok import api_request, carregar_config_tiktok, tiktok_conectado
    from core.pedidos.servico import _enriquecer_pedido_expedicao, obter_pedido, salvar_id_tiktok_package

    ped = obter_pedido(cur, int(id_pedido))
    if not ped or (ped.get("origem") or "") != "tiktok":
        return False

    id_tenant = int(ped["id_tenant_vendedor"])
    if not tiktok_conectado(cur, id_tenant):
        return False

    cfg = carregar_config_tiktok(cur, id_tenant)
    if not cfg.get("conectado"):
        return False

    evento_l = (evento or "").strip().lower()
    if evento_l not in ("expedido", "entregue"):
        return False

    _enriquecer_pedido_expedicao(cur, int(id_pedido), ped)

    package_id = ped.get("id_tiktok_package")
    order_id = ped.get("id_tiktok_pedido")
    tracking = (ped.get("codigo_rastreio") or "").strip()

    if not package_id and order_id:
        try:
            data = api_request(
                cur,
                id_tenant,
                "GET",
                "/order/202309/orders",
                params={"ids": str(order_id)},
            )
            orders = []
            if isinstance(data, dict):
                orders = data.get("orders") or []
            if orders and isinstance(orders[0], dict):
                parsed = parse_pedido_tiktok(orders[0])
                package_id = parsed.get("package_id")
                if package_id:
                    salvar_id_tiktok_package(cur, int(id_pedido), package_id)
        except RuntimeError as e:
            _log.info("TikTok package pedido %s: %s", id_pedido, e)

    if not package_id:
        _log.info("TikTok status: pedido %s sem package_id", id_pedido)
        return False

    try:
        if evento_l == "expedido":
            body: dict[str, Any] = {"package_id": str(package_id)}
            if tracking:
                body["tracking_number"] = tracking
            api_request(
                cur,
                id_tenant,
                "POST",
                "/fulfillment/202309/packages/ship",
                json_body=body,
            )
        else:
            api_request(
                cur,
                id_tenant,
                "POST",
                "/fulfillment/202309/packages/deliver",
                json_body={"package_id": str(package_id)},
            )
        _log.info(
            "TikTok status pedido %s → %s (package %s)",
            id_pedido,
            evento_l,
            package_id,
        )
        return True
    except RuntimeError as e:
        _log.warning(
            "TikTok export status pedido %s (evento=%s): %s",
            id_pedido,
            evento_l,
            e,
        )
        return False


def baixar_etiqueta_tiktok(
    cur,
    id_vendedor: int,
    id_pedido: int,
    pasta_destino,
    *,
    id_usuario: int | None = None,
) -> dict[str, Any]:
    """Baixa etiqueta TikTok Shop e grava como anexo do pedido."""
    from pathlib import Path

    from api.tiktok.tiktok import api_request_bytes, tiktok_conectado
    from core.pedidos.servico import (
        _enriquecer_pedido_expedicao,
        listar_anexos_pedido,
        obter_pedido,
        registrar_anexo_pedido,
    )

    ped = obter_pedido(cur, int(id_pedido), id_vendedor=int(id_vendedor))
    if not ped:
        raise ValueError("Pedido não encontrado.")
    if (ped.get("origem") or "") != "tiktok":
        raise ValueError("Pedido não é do TikTok Shop.")
    if not tiktok_conectado(cur, int(id_vendedor)):
        raise ValueError("TikTok Shop não conectado.")

    _enriquecer_pedido_expedicao(cur, int(id_pedido), ped)
    package_id = ped.get("id_tiktok_package")
    if not package_id:
        raise ValueError("Package TikTok não encontrado para este pedido.")

    nome_sugerido = f"etiqueta_tiktok_{package_id}.pdf"
    existentes = listar_anexos_pedido(cur, int(id_pedido), id_vendedor=int(id_vendedor))
    for a in existentes:
        if a.get("tipo") == "etiqueta" and (a.get("nome_original") or "") == nome_sugerido:
            return {
                "message": "Etiqueta TikTok já anexada.",
                "anexo": a,
                "id_tiktok_package": package_id,
                "ja_existia": True,
            }

    try:
        conteudo = api_request_bytes(
            cur,
            int(id_vendedor),
            "GET",
            "/fulfillment/202309/packages/documents",
            params={"package_id": str(package_id), "document_type": "SHIPPING_LABEL"},
        )
    except RuntimeError as e:
        _log.warning("Etiqueta TikTok pedido %s: %s", id_pedido, e)
        raise ValueError(str(e)[:300]) from e

    if not conteudo or len(conteudo) < 100:
        raise ValueError("Etiqueta TikTok indisponível no momento.")

    pasta = Path(pasta_destino)
    pasta.mkdir(parents=True, exist_ok=True)
    is_zip = conteudo[:2] == b"PK"
    ext = ".zip" if is_zip else ".pdf"
    nome_arquivo = f"etiqueta_tiktok_{package_id}{ext}"
    destino = pasta / f"{id_pedido}_etiqueta_{int(datetime.now(timezone.utc).timestamp())}{ext}"
    destino.write_bytes(conteudo)

    caminho_db = f"upload/tenant{id_vendedor}/pedidos/{destino.name}"
    anexo = registrar_anexo_pedido(
        cur,
        int(id_vendedor),
        int(id_pedido),
        "etiqueta",
        nome_arquivo if is_zip else nome_sugerido,
        caminho_db,
        len(conteudo),
        id_usuario=id_usuario,
    )
    return {
        "message": "Etiqueta TikTok baixada.",
        "anexo": anexo,
        "id_tiktok_package": package_id,
        "ja_existia": False,
    }


def baixar_nf_tiktok(
    cur,
    id_vendedor: int,
    id_pedido: int,
    pasta_destino,
    *,
    id_usuario: int | None = None,
) -> dict[str, Any]:
    """Tenta baixar documento fiscal TikTok (best-effort)."""
    from pathlib import Path

    from api.tiktok.tiktok import api_request_bytes, tiktok_conectado
    from core.pedidos.servico import (
        _enriquecer_pedido_expedicao,
        listar_anexos_pedido,
        obter_pedido,
        registrar_anexo_pedido,
    )

    ped = obter_pedido(cur, int(id_pedido), id_vendedor=int(id_vendedor))
    if not ped or (ped.get("origem") or "") != "tiktok":
        raise ValueError("Pedido não é do TikTok Shop.")
    if not tiktok_conectado(cur, int(id_vendedor)):
        raise ValueError("TikTok Shop não conectado.")

    _enriquecer_pedido_expedicao(cur, int(id_pedido), ped)
    package_id = ped.get("id_tiktok_package")
    if not package_id:
        raise ValueError("Package TikTok não encontrado.")

    nome_sugerido = f"nf_tiktok_{package_id}.pdf"
    for a in listar_anexos_pedido(cur, int(id_pedido), id_vendedor=int(id_vendedor)):
        if a.get("tipo") == "nf" and (a.get("nome_original") or "") == nome_sugerido:
            return {"message": "NF TikTok já anexada.", "anexo": a, "ja_existia": True}

    last_err = None
    conteudo = None
    for doc_type in ("INVOICE", "SHIPPING_LABEL"):  # INVOICE se existir; evita falso positivo de label
        if doc_type == "SHIPPING_LABEL":
            continue
        try:
            conteudo = api_request_bytes(
                cur,
                int(id_vendedor),
                "GET",
                "/fulfillment/202309/packages/documents",
                params={"package_id": str(package_id), "document_type": doc_type},
            )
            if conteudo and len(conteudo) >= 100:
                break
        except RuntimeError as e:
            last_err = e
            conteudo = None

    if not conteudo or len(conteudo) < 100:
        raise ValueError(
            str(last_err) if last_err else "Nota fiscal TikTok indisponível neste pedido."
        )

    pasta = Path(pasta_destino)
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / f"{id_pedido}_nf_{int(datetime.now(timezone.utc).timestamp())}.pdf"
    destino.write_bytes(conteudo)
    caminho_db = f"upload/tenant{id_vendedor}/pedidos/{destino.name}"
    anexo = registrar_anexo_pedido(
        cur,
        int(id_vendedor),
        int(id_pedido),
        "nf",
        nome_sugerido,
        caminho_db,
        len(conteudo),
        id_usuario=id_usuario,
    )
    return {"message": "Nota fiscal TikTok baixada.", "anexo": anexo, "ja_existia": False}


def puxar_documentos_integracao_tiktok(
    cur,
    id_vendedor: int,
    id_pedido: int,
    pasta_destino,
    *,
    id_usuario: int | None = None,
) -> dict[str, Any]:
    """Puxa etiqueta e, se existir, NF do TikTok Shop."""
    out: dict[str, Any] = {"origem": "tiktok", "etiqueta": None, "fiscal": None, "avisos": []}
    try:
        out["etiqueta"] = baixar_etiqueta_tiktok(
            cur, id_vendedor, id_pedido, pasta_destino, id_usuario=id_usuario
        )
    except ValueError as e:
        out["avisos"].append(str(e))
    try:
        out["fiscal"] = baixar_nf_tiktok(
            cur, id_vendedor, id_pedido, pasta_destino, id_usuario=id_usuario
        )
    except ValueError as e:
        out["avisos"].append(str(e))

    if not out["etiqueta"] and not out["fiscal"]:
        raise ValueError(out["avisos"][0] if out["avisos"] else "Nada disponível na integração.")

    msgs = []
    if out["etiqueta"]:
        msgs.append(out["etiqueta"].get("message") or "Etiqueta ok.")
    if out["fiscal"]:
        msgs.append(out["fiscal"].get("message") or "Documento fiscal ok.")
    out["message"] = " ".join(msgs)
    out["ok"] = True
    return out
