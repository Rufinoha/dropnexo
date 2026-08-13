"""Importação de pedidos Mercado Livre → DropNexo (pedido + estoque)."""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from global_utils import agora_utc

_log = logging.getLogger(__name__)


def _mensagem_erro_amigavel_ml(err: str | Exception) -> str:
    """Traduz erros técnicos de importação ML para linguagem de vendedor."""
    s = str(err or "").strip()
    low = s.lower()
    if "tbl_pedido_origem_check" in low or "origem_check" in low:
        return (
            "O banco ainda não aceitava pedidos do Mercado Livre. "
            "Atualize o sistema e tente novamente."
        )
    if "transaction is aborted" in low:
        return "Falha interna na sincronização. Tente buscar os pedidos novamente."
    if "sem vínculo" in low or "sem_match" in low or "não encontrado em meus produtos" in low:
        return s
    if "não encontrado em meus produtos" in low or "não encontrado em Meus produtos" in low:
        return (
            "Produto do pedido não está vinculado em Meus produtos. "
            "Publique ou vincule o anúncio e tente de novo."
        )
    if "sem vínculo ativo" in low:
        return "Há produto de fornecedor sem vínculo ativo. Reative o vínculo e tente de novo."
    if "capacidade" in low or "limite" in low:
        return s
    # Evita despejar DETAIL/Failing row do Postgres na tela
    if "violates check constraint" in low or "failing row contains" in low:
        return "Não foi possível criar o pedido por uma regra do banco. Tente novamente após atualizar o sistema."
    if len(s) > 220:
        return s[:217] + "…"
    return s


def _pedido_ml_ja_processado(cur, id_tenant: int, id_ml_pedido: str) -> bool:
    from core.pedidos.servico import _garantir_coluna_id_ml_pedido, _pedido_colunas

    # Nunca engolir erro SQL: no Postgres isso aborta a transação e o próximo
    # comando vira "current transaction is aborted...".
    _garantir_coluna_id_ml_pedido(cur)
    if "id_ml_pedido" in _pedido_colunas(cur):
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


def _fone_de_obj(phone: Any) -> str:
    if isinstance(phone, dict):
        area = str(phone.get("area_code") or "").strip()
        num = str(phone.get("number") or "").strip()
        if num:
            return f"{area}{num}".strip()
        return ""
    return str(phone or "").strip()


def _telefone_ml(buyer: dict, shipment: dict | None) -> str:
    fontes: list[Any] = []
    if isinstance(buyer, dict):
        fontes.extend(
            [
                buyer.get("phone"),
                buyer.get("alternative_phone"),
                buyer.get("receiver_phone"),
            ]
        )
    if isinstance(shipment, dict):
        dest = shipment.get("destination") if isinstance(shipment.get("destination"), dict) else {}
        addr = (
            shipment.get("receiver_address")
            or (dest.get("shipping_address") if dest else None)
            or {}
        )
        fontes.extend(
            [
                shipment.get("receiver_phone"),
                dest.get("receiver_phone") if isinstance(dest, dict) else None,
                addr.get("phone") if isinstance(addr, dict) else None,
                addr.get("receiver_phone") if isinstance(addr, dict) else None,
            ]
        )
    for phone in fontes:
        tel = _fone_de_obj(phone)
        if tel:
            return tel
    return ""


def _docs_de_bloco(bloco: Any) -> list[str]:
    """Extrai possíveis documentos de um dict de billing (v1/v2)."""
    out: list[str] = []
    if not isinstance(bloco, dict):
        return out
    out.append(str(bloco.get("doc_number") or ""))
    out.append(str(bloco.get("number") or ""))
    ident = bloco.get("identification") or {}
    if isinstance(ident, dict):
        out.append(str(ident.get("number") or ""))
    for key in ("additional_info", "attributes", "taxes"):
        lista = bloco.get(key)
        if not isinstance(lista, list):
            continue
        for item in lista:
            if not isinstance(item, dict):
                continue
            tipo = str(item.get("type") or item.get("key") or "").upper()
            if tipo in ("DOC_NUMBER", "DOCUMENT_NUMBER", "CPF", "CNPJ", "TAX_ID"):
                out.append(str(item.get("value") or item.get("number") or ""))
            elif item.get("number") and not tipo:
                out.append(str(item.get("number") or ""))
    return out


def _documento_ml(buyer: dict, order: dict, billing_info: dict | None = None) -> str:
    candidatos: list[str] = []
    if isinstance(billing_info, dict):
        candidatos.extend(_docs_de_bloco(billing_info))
        candidatos.extend(_docs_de_bloco(billing_info.get("billing_info")))
        buyer_b = billing_info.get("buyer") or {}
        if isinstance(buyer_b, dict):
            candidatos.extend(_docs_de_bloco(buyer_b))
            candidatos.extend(_docs_de_bloco(buyer_b.get("billing_info")))

    candidatos.extend(_docs_de_bloco(buyer.get("billing_info")))
    candidatos.extend(_docs_de_bloco(buyer.get("identification")))
    taxes = order.get("taxes") or {}
    if isinstance(taxes, dict):
        candidatos.append(str(taxes.get("id") or ""))

    melhor = ""
    for doc in candidatos:
        d = _digitos(doc)
        if len(d) in (11, 14):
            return d
        if len(d) > len(melhor):
            melhor = d
    # Aceita documento com 11+ dígitos mesmo fora do padrão estrito
    return melhor if len(melhor) >= 11 else ""


def _buscar_billing_info_ml(cur, id_tenant: int, id_ml_pedido: str) -> dict | None:
    """CPF/CNPJ e dados fiscais do comprador (endpoint dedicado do ML)."""
    from api.mercado_livre.mercado_livre import api_request

    oid = str(id_ml_pedido or "").strip()
    if not oid:
        return None
    for headers in ({"x-version": "2"}, None):
        try:
            data = api_request(
                cur,
                int(id_tenant),
                "GET",
                f"/orders/{oid}/billing_info",
                extra_headers=headers,
            )
            if isinstance(data, dict) and data:
                return data
        except RuntimeError as e:
            _log.info("billing_info ML %s: %s", oid, e)
    return None


def _nome_de_billing(billing_info: dict | None, buyer: dict) -> str:
    if isinstance(billing_info, dict):
        bi = None
        if isinstance(billing_info.get("buyer"), dict):
            bi = (billing_info.get("buyer") or {}).get("billing_info")
        if not isinstance(bi, dict):
            bi = billing_info.get("billing_info")
        if isinstance(bi, dict):
            first = (bi.get("name") or bi.get("first_name") or "").strip()
            last = (bi.get("last_name") or "").strip()
            nome = f"{first} {last}".strip()
            if nome:
                return nome
    return _nome_comprador_ml(buyer)


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


def parse_pedido_ml(
    order: dict,
    shipment: dict | None = None,
    *,
    billing_info: dict | None = None,
) -> dict[str, Any]:
    """Extrai cliente, entrega e itens de um order ML (+ shipment / billing_info)."""
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

    email = (buyer.get("email") or "").strip() or None
    # ML costuma omitir e-mail real por privacidade; mantém se vier.
    return {
        "numero_ml": str(order.get("id") or ""),
        "cliente": {
            "nome": _nome_de_billing(billing_info, buyer),
            "email": email,
            "telefone": _telefone_ml(buyer, shipment) or None,
            "documento": _documento_ml(buyer, order, billing_info) or None,
        },
        "entrega": _entrega_de_shipment(shipment),
        "itens": itens,
        "valor_frete": frete if frete > 0 else 0.0,
        "observacoes": "",
        "total_ml": float(order.get("total_amount") or 0),
    }


def _ids_pedido_local_ml(cur, id_tenant: int, id_ml_pedido: str) -> list[int]:
    """Resolve IDs locais por id_ml_pedido e, se preciso, pelo mapa de integração."""
    from core.pedidos.servico import listar_pedidos_por_id_ml

    ids = [int(x) for x in listar_pedidos_por_id_ml(cur, int(id_tenant), str(id_ml_pedido))]
    if ids:
        return ids
    cur.execute(
        """
        SELECT DISTINCT id_dropnexo FROM tbl_integracao_map
        WHERE id_tenant = %s AND provedor = 'mercado_livre'
          AND contexto = 'vendedor' AND entidade = 'pedido'
          AND (id_bling = %s OR id_bling LIKE %s)
          AND COALESCE(id_dropnexo, 0) > 0
        """,
        (int(id_tenant), str(id_ml_pedido), f"{id_ml_pedido}:%"),
    )
    for row in cur.fetchall() or []:
        try:
            pid = int(row[0] or 0)
        except (TypeError, ValueError):
            continue
        if pid > 0 and pid not in ids:
            ids.append(pid)
    return ids


def _preencher_cliente_pedidos_ml(cur, ids_pedido: list[int], cliente: dict) -> dict[str, Any]:
    """
    Completa campos vazios do comprador.
    Retorna {atualizado, pedidos, campos} para o resumo da sync.
    """
    vazio = {"atualizado": False, "pedidos": 0, "campos": []}
    if not ids_pedido or not isinstance(cliente, dict):
        return vazio
    nome = (cliente.get("nome") or "").strip()
    email = (cliente.get("email") or "").strip()
    telefone = (cliente.get("telefone") or "").strip()
    documento = _digitos(cliente.get("documento"))
    if not any((nome, email, telefone, documento)):
        return vazio

    campos_ok: set[str] = set()
    pedidos_ok = 0
    for pid in ids_pedido:
        cur.execute(
            """
            SELECT
              COALESCE(NULLIF(TRIM(cliente_nome), ''), ''),
              COALESCE(NULLIF(TRIM(cliente_email), ''), ''),
              COALESCE(NULLIF(TRIM(cliente_telefone), ''), ''),
              COALESCE(NULLIF(TRIM(cliente_documento), ''), '')
            FROM tbl_pedido WHERE id = %s
            """,
            (int(pid),),
        )
        row = cur.fetchone()
        if not row:
            continue
        nome_atual, email_atual, tel_atual, doc_atual = [str(x or "") for x in row]
        sets: list[str] = []
        params: list[Any] = []
        if nome and (not nome_atual or nome_atual == "Cliente Mercado Livre"):
            sets.append("cliente_nome = %s")
            params.append(nome)
            campos_ok.add("nome")
        if email and not email_atual:
            sets.append("cliente_email = %s")
            params.append(email)
            campos_ok.add("e-mail")
        if telefone and not tel_atual:
            sets.append("cliente_telefone = %s")
            params.append(telefone)
            campos_ok.add("telefone")
        if documento and not _digitos(doc_atual):
            sets.append("cliente_documento = %s")
            params.append(documento)
            campos_ok.add("CPF/CNPJ")
        if not sets:
            continue
        # Se veio do mapa sem id_ml_pedido na linha, aproveita para gravar o vínculo.
        params.append(int(pid))
        cur.execute(
            f"UPDATE tbl_pedido SET {', '.join(sets)} WHERE id = %s",
            tuple(params),
        )
        pedidos_ok += 1

    return {
        "atualizado": pedidos_ok > 0,
        "pedidos": pedidos_ok,
        "campos": sorted(campos_ok),
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
    from core.pedidos.servico import _resolver_item_meus_produtos_por_sku

    resolvidos: list[dict] = []
    ignorados = 0
    for raw in dados.get("itens") or []:
        ml_item_id = str(raw.get("ml_item_id") or "").strip()
        sku = (raw.get("sku") or "").strip()
        id_variante = _variante_por_ml_item(cur, id_tenant, ml_item_id) if ml_item_id else None
        if not id_variante and sku:
            item = _resolver_item_meus_produtos_por_sku(cur, id_tenant, sku)
            if item:
                id_variante = int(item["id_variante"])
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

    shipment = _buscar_shipment_ml(cur, id_tenant, pedido)
    billing = _buscar_billing_info_ml(cur, id_tenant, id_ml)
    dados_cliente = parse_pedido_ml(pedido, shipment, billing_info=billing)

    if _pedido_ml_ja_processado(cur, id_tenant, id_ml):
        from core.pedidos.servico import salvar_id_ml_shipment

        ids_locais = _ids_pedido_local_ml(cur, int(id_tenant), id_ml)
        # Garante id_ml_pedido nas linhas encontradas só pelo mapa
        if ids_locais:
            from core.pedidos.servico import _garantir_coluna_id_ml_pedido, _pedido_colunas

            if _garantir_coluna_id_ml_pedido(cur) and "id_ml_pedido" in _pedido_colunas(cur):
                for pid in ids_locais:
                    cur.execute(
                        """
                        UPDATE tbl_pedido
                        SET id_ml_pedido = COALESCE(NULLIF(TRIM(id_ml_pedido), ''), %s)
                        WHERE id = %s AND id_tenant_vendedor = %s
                        """,
                        (str(id_ml), int(pid), int(id_tenant)),
                    )
        fill = _preencher_cliente_pedidos_ml(
            cur, ids_locais, dados_cliente.get("cliente") or {}
        )
        ship_id = (shipment or {}).get("id") if isinstance(shipment, dict) else None
        if not ship_id and isinstance(pedido.get("shipping"), dict):
            ship_id = (pedido.get("shipping") or {}).get("id")
        if ship_id:
            for pid in ids_locais:
                salvar_id_ml_shipment(cur, int(pid), ship_id)
        return {
            "importado": False,
            "atualizado": bool(fill.get("atualizado")),
            "motivo": "dados_atualizados" if fill.get("atualizado") else "ja_importado",
            "id_ml_pedido": id_ml,
            "id_ml_shipment": ship_id,
            "ids_pedido": ids_locais,
            "campos_atualizados": fill.get("campos") or [],
            "cliente_ml": dados_cliente.get("cliente") or {},
        }

    if status not in ("paid", "confirmed"):
        return {"importado": False, "motivo": "status_nao_pago", "status": status}

    dados = _resolver_itens_variante(cur, id_tenant, dados_cliente)
    if not dados.get("itens"):
        return {
            "importado": False,
            "motivo": "sem_match",
            "ignorados": dados.get("itens_ignorados") or 0,
        }

    try:
        ids = importar_pedido_ml(cur, id_tenant, id_ml, dados)
    except (ValueError, RuntimeError) as e:
        # Erros de negócio (sem item/vínculo/capacidade). Falhas SQL sobem
        # para o SAVEPOINT do loop — engolir abortaria a transação.
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
    from core.pedidos.servico import _garantir_check_origem_pedido, _garantir_coluna_id_ml_pedido

    cfg = carregar_config_ml(cur, id_tenant)
    ml_user_id = cfg.get("ml_user_id")
    if not ml_user_id:
        raise RuntimeError("Perfil Mercado Livre sem user_id. Reconecte a conta.")

    if not _garantir_coluna_id_ml_pedido(cur):
        raise RuntimeError(
            "Coluna id_ml_pedido ausente. Aplique __doc/sql/076_pedido_id_ml.sql."
        )
    _garantir_check_origem_pedido(cur)

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
    atualizados = 0
    cancelados = 0
    ignorados = 0
    erros: list[str] = []
    infos: list[str] = []
    ids_pedidos: list[int] = []

    for idx, id_ml in enumerate(ids):
        sp = f"ml_pedido_{idx}"
        try:
            cur.execute(f"SAVEPOINT {sp}")
            res = _importar_um_pedido_ml(cur, id_tenant, id_ml)
            try:
                cur.execute(f"RELEASE SAVEPOINT {sp}")
            except Exception:
                cur.execute(f"ROLLBACK TO SAVEPOINT {sp}")
                raise
            if res.get("importado"):
                importados += 1
                ids_pedidos.extend(int(x) for x in (res.get("ids_pedido") or []))
                # Tenta etiqueta/NF já na importação manual (best-effort).
                try:
                    cur.execute(f"SAVEPOINT {sp}_docs")
                    _tentar_puxar_documentos_auto_ml(
                        cur,
                        int(id_tenant),
                        id_ml_pedido=str(id_ml),
                        ids_pedido=[int(x) for x in (res.get("ids_pedido") or [])],
                    )
                    cur.execute(f"RELEASE SAVEPOINT {sp}_docs")
                except Exception:
                    try:
                        cur.execute(f"ROLLBACK TO SAVEPOINT {sp}_docs")
                    except Exception:
                        pass
            elif res.get("cancelado"):
                cancelados += 1
                ids_pedidos.extend(int(x) for x in (res.get("ids_pedido") or []))
            elif res.get("atualizado") or res.get("motivo") == "dados_atualizados":
                atualizados += 1
                ids_pedidos.extend(int(x) for x in (res.get("ids_pedido") or []))
                campos = res.get("campos_atualizados") or []
                infos.append(
                    f"#{id_ml}: pedido já existia — atualizei {', '.join(campos) or 'dados do comprador'}."
                )
                try:
                    cur.execute(f"SAVEPOINT {sp}_docs")
                    _tentar_puxar_documentos_auto_ml(
                        cur, int(id_tenant), id_ml_pedido=str(id_ml)
                    )
                    cur.execute(f"RELEASE SAVEPOINT {sp}_docs")
                except Exception:
                    try:
                        cur.execute(f"ROLLBACK TO SAVEPOINT {sp}_docs")
                    except Exception:
                        pass
            else:
                ignorados += 1
                motivo = res.get("motivo") or "ignorado"
                if motivo == "erro_criar" and res.get("mensagem"):
                    erros.append(
                        f"#{id_ml}: {_mensagem_erro_amigavel_ml(res['mensagem'])}"
                    )
                elif motivo == "sem_match":
                    erros.append(
                        f"#{id_ml}: itens do anúncio sem vínculo em Meus produtos "
                        f"(publique/vincule o produto ou confira o SKU)."
                    )
                elif motivo == "status_nao_pago":
                    erros.append(
                        f"#{id_ml}: pedido ainda não está pago no ML "
                        f"(status: {res.get('status') or '?'})."
                    )
                elif motivo == "erro_api" and res.get("mensagem"):
                    erros.append(
                        f"#{id_ml}: {_mensagem_erro_amigavel_ml(res['mensagem'])}"
                    )
                elif motivo == "ja_importado":
                    infos.append(
                        f"#{id_ml}: pedido já estava no DropNexo "
                        "(CPF/e-mail/telefone já preenchidos ou o ML não enviou esses dados)."
                    )
                    try:
                        cur.execute(f"SAVEPOINT {sp}_docs")
                        _tentar_puxar_documentos_auto_ml(
                            cur, int(id_tenant), id_ml_pedido=str(id_ml)
                        )
                        cur.execute(f"RELEASE SAVEPOINT {sp}_docs")
                    except Exception:
                        try:
                            cur.execute(f"ROLLBACK TO SAVEPOINT {sp}_docs")
                        except Exception:
                            pass
        except Exception as e:
            try:
                cur.execute(f"ROLLBACK TO SAVEPOINT {sp}")
            except Exception:
                pass
            erros.append(f"#{id_ml}: {_mensagem_erro_amigavel_ml(e)}")
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
        f"{importados} pedido(s) criado(s). "
        f"{atualizados} atualizado(s). "
        f"{cancelados} cancelamento(s). "
        f"{ignorados} já existente(s)/ignorado(s)."
    )
    detalhes = (infos + erros)[:8]
    if erros and importados == 0 and atualizados == 0:
        msg += f" Motivo: {erros[0]}"
    elif infos and importados == 0:
        msg += f" {infos[0]}"

    return {
        "message": msg,
        "total_encontrados": len(ids),
        "importados": importados,
        "atualizados": atualizados,
        "cancelados": cancelados,
        "ignorados": ignorados,
        "ids_pedido": ids_pedidos[:20],
        "detalhes_erros": detalhes,
        "resumo": {
            "encontrados": len(ids),
            "importados": importados,
            "atualizados": atualizados,
            "cancelados": cancelados,
            "ignorados": ignorados,
            "erros": len(erros),
        },
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


def _pasta_anexos_tenant_ml(id_tenant: int):
    from pathlib import Path

    pasta = Path(__file__).resolve().parents[2] / "upload" / f"tenant{int(id_tenant)}" / "pedidos"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def _tentar_puxar_documentos_auto_ml(
    cur,
    id_tenant: int,
    *,
    id_ml_pedido: str | None = None,
    ids_pedido: list[int] | None = None,
) -> dict[str, Any]:
    """
    Best-effort: baixa etiqueta de transporte e NF/DANFE do ML para pedidos locais.
    Não falha o webhook se o documento ainda não estiver liberado no ML.
    """
    from core.pedidos.servico import listar_pedidos_por_id_ml

    pids: list[int] = []
    if ids_pedido:
        pids.extend(int(x) for x in ids_pedido if x)
    if id_ml_pedido:
        for pid in listar_pedidos_por_id_ml(cur, int(id_tenant), str(id_ml_pedido)):
            if int(pid) not in pids:
                pids.append(int(pid))
    if not pids:
        return {"docs_tentados": 0, "etiqueta_ok": 0, "fiscal_ok": 0, "docs_avisos": []}

    pasta = _pasta_anexos_tenant_ml(id_tenant)
    etiqueta_ok = 0
    fiscal_ok = 0
    avisos: list[str] = []

    try:
        from api.melhor_envio.melhor_envio import definir_modo_frete_integracao
    except Exception:
        definir_modo_frete_integracao = None  # type: ignore

    for pid in pids:
        try:
            if definir_modo_frete_integracao:
                try:
                    definir_modo_frete_integracao(cur, int(id_tenant), int(pid))
                except ValueError:
                    pass
            res = puxar_documentos_integracao_ml(
                cur, int(id_tenant), int(pid), pasta, id_usuario=None
            )
            if res.get("etiqueta"):
                etiqueta_ok += 1
            if res.get("fiscal"):
                fiscal_ok += 1
            for a in res.get("avisos") or []:
                avisos.append(f"#{pid}: {a}")
        except ValueError as e:
            avisos.append(f"#{pid}: {e}")
        except Exception as e:
            avisos.append(f"#{pid}: {str(e)[:120]}")
            _log.info("Auto docs ML pedido %s: %s", pid, e)

    return {
        "docs_tentados": len(pids),
        "etiqueta_ok": etiqueta_ok,
        "fiscal_ok": fiscal_ok,
        "docs_avisos": avisos[:8],
    }


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
        # Mesmo sem auto-import, tenta etiqueta/NF se o pedido local já existir.
        docs = _tentar_puxar_documentos_auto_ml(
            cur, int(id_tenant), id_ml_pedido=str(id_ml)
        )
        return {
            "ok": True,
            "ignorado": True,
            "motivo": "importacao_auto_desligada",
            **docs,
        }

    from core.pedidos.servico import _garantir_coluna_id_ml_pedido

    if not _garantir_coluna_id_ml_pedido(cur):
        return {
            "ok": False,
            "motivo": "schema_id_ml_pedido",
            "mensagem": "Coluna id_ml_pedido ausente. Aplique SQL 076.",
        }

    try:
        cur.execute("SAVEPOINT sp_ml_webhook_pedido")
        res = _importar_um_pedido_ml(cur, int(id_tenant), str(id_ml))
        try:
            cur.execute("RELEASE SAVEPOINT sp_ml_webhook_pedido")
        except Exception:
            cur.execute("ROLLBACK TO SAVEPOINT sp_ml_webhook_pedido")
            raise
    except Exception as e:
        try:
            cur.execute("ROLLBACK TO SAVEPOINT sp_ml_webhook_pedido")
        except Exception:
            pass
        _log.exception("Webhook ML falhou ao importar pedido %s", id_ml)
        return {
            "ok": False,
            "motivo": "erro_importar",
            "mensagem": str(e)[:250],
            "id_ml_pedido": str(id_ml),
        }

    docs = _tentar_puxar_documentos_auto_ml(
        cur,
        int(id_tenant),
        id_ml_pedido=str(id_ml),
        ids_pedido=[int(x) for x in (res.get("ids_pedido") or [])],
    )
    return {"ok": True, "id_tenant": id_tenant, **res, **docs}


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

    avancados = 0
    ids_locais: list[int] = []
    if order_id:
        from core.pedidos.servico import listar_pedidos_por_id_ml, salvar_id_ml_shipment
        from core.pedidos.status_integracao import (
            aplicar_status_avancado,
            mapear_status_ml_para_dn,
        )

        novo = mapear_status_ml_para_dn(None, shipping_status=st)
        for pid in listar_pedidos_por_id_ml(cur, id_tenant, str(order_id)):
            ids_locais.append(int(pid))
            salvar_id_ml_shipment(cur, int(pid), ship_id)
            if novo and aplicar_status_avancado(
                cur,
                int(pid),
                novo,
                origem_evento="mercado_livre",
                detalhe=f"Status sincronizado do envio ML ({st}).",
            ):
                avancados += 1

    # Etiqueta costuma liberar em ready_to_ship / shipped; NF quando o ML emitir.
    docs: dict[str, Any] = {}
    if order_id and ids_locais and st not in ("cancelled", "canceled"):
        docs = _tentar_puxar_documentos_auto_ml(
            cur,
            int(id_tenant),
            id_ml_pedido=str(order_id),
            ids_pedido=ids_locais,
        )

    return {
        "ok": True,
        "topic": "shipments",
        "id_ml_shipment": ship_id,
        "status": st,
        "order_id": order_id,
        "status_avancados": avancados,
        **docs,
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
            _mensagem_doc_ml_amigavel(
                last_err or "Etiqueta indisponível.",
                tipo="etiqueta",
            )
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


def _eh_pdf_bytes(raw: bytes | None) -> bool:
    return bool(raw and len(raw) >= 80 and raw[:4] == b"%PDF")


def _eh_xml_bytes(raw: bytes | None) -> bool:
    if not raw or len(raw) < 20:
        return False
    head = raw[:80].lstrip()
    return head.startswith(b"<?xml") or head.startswith(b"<")


def _href_com_doctype(href: str, doctype: str) -> str:
    """Troca/insere doctype=pdf|xml no href do fiscal-info do ML."""
    from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

    href = (href or "").strip()
    if not href:
        return ""
    parsed = urlparse(href)
    q = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k.lower() != "doctype"]
    q.append(("doctype", doctype))
    return urlunparse(parsed._replace(query=urlencode(q)))


def _extrair_invoices_fiscal_info(info: Any) -> list[dict[str, Any]]:
    """Normaliza fiscal-info do ML em lista de invoices com metadados."""
    out: list[dict[str, Any]] = []
    if not isinstance(info, dict):
        return out
    fiscal_list = info.get("fiscal_data") or []
    if not isinstance(fiscal_list, list):
        fiscal_list = [fiscal_list]
    if isinstance(info.get("invoice"), dict):
        fiscal_list = [info] + list(fiscal_list)

    for bloco in fiscal_list:
        if not isinstance(bloco, dict):
            continue
        inv = bloco.get("invoice") if isinstance(bloco.get("invoice"), dict) else bloco
        if not isinstance(inv, dict):
            continue
        doc = inv.get("document") if isinstance(inv.get("document"), dict) else {}
        sender = (
            bloco.get("sender_identification")
            if isinstance(bloco.get("sender_identification"), dict)
            else {}
        )
        doc_type = str(doc.get("type") or inv.get("type") or "").lower()
        chave = str(inv.get("key") or "").strip()
        href = str(doc.get("href") or inv.get("href") or "").strip()
        if not chave and not href:
            continue
        is_dce = "dce" in doc_type or (chave.startswith("35") and len(chave) >= 44)
        out.append(
            {
                "key": chave,
                "number": inv.get("number"),
                "serie": inv.get("serie"),
                "amount": inv.get("amount"),
                "date": inv.get("date"),
                "cfop": inv.get("cfop"),
                "href": href,
                "doc_type": doc_type,
                "format": str(doc.get("format") or "").lower(),
                "tipo_anexo": "declaracao" if is_dce else "nf",
                "sender_cnpj": str(sender.get("number") or "").strip(),
                "sender_ie": str(sender.get("state_tax_id") or "").strip(),
            }
        )
    return out


def _pdf_comprovante_fiscal_ml(
    meta: dict[str, Any],
    *,
    id_pedido_dn: int | None = None,
    ship_id: str | None = None,
    order_id: str | None = None,
) -> bytes:
    """
    Gera PDF de expedição a partir dos dados liberados no fiscal-info.

    A API pública do ML entrega o XML da NF-e/DC-e; o DropNexo precisa de PDF
    para o fornecedor. Este comprovante traz chave, número e valor oficiais.
    """
    from io import BytesIO

    from fpdf import FPDF

    def _txt(s: str) -> str:
        # Helvetica core font: latin-1
        return (
            str(s or "")
            .replace("—", "-")
            .replace("–", "-")
            .replace("·", "-")
            .replace("…", "...")
            .encode("latin-1", "replace")
            .decode("latin-1")
        )

    is_dce = meta.get("tipo_anexo") == "declaracao"
    titulo = "Declaracao de conteudo (DC-e)" if is_dce else "Nota fiscal eletronica (NF-e)"
    chave = str(meta.get("key") or "").strip()
    chave_fmt = " ".join(chave[i : i + 4] for i in range(0, len(chave), 4)) if chave else "-"

    numero = meta.get("number")
    serie = meta.get("serie")
    amount = meta.get("amount")
    data = str(meta.get("date") or "").strip()
    if "T" in data:
        data = data.replace("T", " ")[:19]

    try:
        valor_txt = f"R$ {float(amount):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        valor_txt = "-" if amount in (None, "") else str(amount)

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    pdf.set_margins(16, 16, 16)
    usable = pdf.w - pdf.l_margin - pdf.r_margin

    pdf.set_fill_color(2, 31, 129)
    pdf.rect(0, 0, 210, 28, "F")
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_xy(16, 8)
    pdf.cell(usable, 8, _txt("DropNexo - Documento fiscal"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_x(16)
    pdf.cell(
        usable,
        6,
        _txt("Comprovante para expedicao (dados oficiais do Mercado Livre)"),
        new_x="LMARGIN",
        new_y="NEXT",
    )

    pdf.set_text_color(15, 23, 42)
    pdf.ln(10)
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(usable, 8, _txt(titulo), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(71, 85, 105)
    pdf.multi_cell(
        usable,
        5,
        _txt(
            "O Mercado Livre libera o XML da nota na API. Geramos este PDF com os "
            "dados fiscais oficiais para o fornecedor poder despachar no DropNexo."
        ),
    )
    pdf.ln(4)

    def _linha(rotulo: str, valor: str, *, largo: bool = False) -> None:
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(100, 116, 139)
        if largo:
            pdf.cell(usable, 6, _txt(rotulo), new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(15, 23, 42)
            pdf.multi_cell(usable, 6, _txt(valor or "-"))
            return
        pdf.cell(44, 7, _txt(rotulo))
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(15, 23, 42)
        pdf.cell(usable - 44, 7, _txt(valor or "-"), new_x="LMARGIN", new_y="NEXT")

    _linha("Chave de acesso", chave_fmt, largo=True)
    if numero not in (None, ""):
        _linha("Numero", str(numero))
    if serie not in (None, ""):
        _linha("Serie", str(serie))
    _linha("Valor", valor_txt)
    if data:
        _linha("Emissao", data)
    if meta.get("cfop") not in (None, ""):
        _linha("CFOP", str(meta.get("cfop")))
    if meta.get("sender_cnpj"):
        _linha("CNPJ emitente", str(meta.get("sender_cnpj")))
    if meta.get("sender_ie"):
        _linha("IE emitente", str(meta.get("sender_ie")))
    if order_id:
        _linha("Pedido ML", str(order_id))
    if ship_id:
        _linha("Envio ML", str(ship_id))
    if id_pedido_dn:
        _linha("Pedido DropNexo", str(id_pedido_dn))

    pdf.ln(6)
    pdf.set_draw_color(226, 232, 240)
    y = pdf.get_y()
    pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
    pdf.ln(4)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(100, 116, 139)
    pdf.multi_cell(
        usable,
        4.5,
        _txt(
            "Documento gerado automaticamente pelo DropNexo. A chave de acesso e os "
            "demais campos vem do fiscal-info do Mercado Envios. Conserve junto a etiqueta."
        ),
    )

    buf = BytesIO()
    pdf.output(buf)
    return buf.getvalue()


def _resolver_pack_id_ml(cur, id_vendedor: int, ped: dict, order_id: str | None) -> str | None:
    """pack_id do pedido ML; se nulo na order, a doc do ML manda usar o próprio order_id."""
    pack = ped.get("id_ml_pack") or ped.get("pack_id")
    if pack:
        return str(pack)
    if not order_id:
        return None
    from api.mercado_livre.mercado_livre import api_request

    try:
        order = api_request(cur, int(id_vendedor), "GET", f"/orders/{order_id}")
    except RuntimeError:
        return str(order_id)
    if not isinstance(order, dict):
        return str(order_id)
    pack = order.get("pack_id")
    return str(pack) if pack else str(order_id)


def _baixar_pdf_packs_fiscal_documents(
    cur, id_vendedor: int, pack_id: str
) -> tuple[bytes | None, Exception | None]:
    """Lista e baixa PDF anexado em /packs/{id}/fiscal_documents (API de vendedor)."""
    from api.mercado_livre.mercado_livre import api_request, api_request_bytes

    last_err: Exception | None = None
    try:
        listing = api_request(
            cur, int(id_vendedor), "GET", f"/packs/{pack_id}/fiscal_documents"
        )
    except RuntimeError as e:
        return None, e

    docs: list[Any] = []
    if isinstance(listing, dict):
        docs = (
            listing.get("fiscal_documents")
            or listing.get("documents")
            or listing.get("results")
            or []
        )
        if not docs and listing.get("id"):
            docs = [listing]
    elif isinstance(listing, list):
        docs = listing

    if not docs:
        return None, ValueError("Nenhum documento fiscal anexado no pack do ML.")

    for doc in docs:
        if not isinstance(doc, dict):
            continue
        file_id = (
            doc.get("id")
            or doc.get("filename")
            or doc.get("file_id")
            or doc.get("fiscal_document_id")
        )
        tipo = str(doc.get("type") or doc.get("file_type") or doc.get("mime_type") or "").lower()
        nome = str(doc.get("filename") or doc.get("name") or file_id or "").lower()
        # Prefere PDF; se só houver um item, tenta mesmo assim
        if tipo and "xml" in tipo and "pdf" not in tipo:
            continue
        if nome.endswith(".xml") and not nome.endswith(".pdf"):
            continue
        if not file_id:
            continue
        try:
            raw = api_request_bytes(
                cur,
                int(id_vendedor),
                "GET",
                f"/packs/{pack_id}/fiscal_documents/{file_id}",
            )
        except RuntimeError as e:
            last_err = e
            continue
        if _eh_pdf_bytes(raw):
            return raw, None
        if _eh_xml_bytes(raw):
            last_err = ValueError("ML liberou XML no pack (sem PDF).")
    return None, last_err or ValueError("Documentos do pack sem PDF utilizável.")


def _baixar_pdf_faturador_ml(
    cur, id_vendedor: int, order_id: str, pack_id: str | None
) -> tuple[bytes | None, dict[str, Any] | None, Exception | None]:
    """
    Tenta a NF emitida pelo Faturador do ML (users/.../invoices).
    Retorna (pdf, meta_para_comprovante, erro).
    """
    from api.mercado_livre.mercado_livre import (
        api_request,
        api_request_bytes,
        carregar_config_ml,
    )

    cfg = carregar_config_ml(cur, int(id_vendedor))
    user_id = cfg.get("ml_user_id")
    if not user_id:
        try:
            me = api_request(cur, int(id_vendedor), "GET", "/users/me")
            user_id = me.get("id") if isinstance(me, dict) else None
        except RuntimeError as e:
            return None, None, e
    if not user_id:
        return None, None, ValueError("Conta ML sem user_id.")

    last_err: Exception | None = None
    invoice: dict[str, Any] | None = None

    candidatos_json = [
        f"/users/{user_id}/invoices/orders/{order_id}",
        f"/users/{user_id}/invoices/order/{order_id}",
    ]
    if pack_id:
        candidatos_json.append(f"/users/{user_id}/invoices/packs/{pack_id}")
        candidatos_json.append(f"/users/{user_id}/invoices/pack/{pack_id}")

    for path in candidatos_json:
        try:
            data = api_request(cur, int(id_vendedor), "GET", path)
        except RuntimeError as e:
            last_err = e
            continue
        if isinstance(data, dict) and (data.get("id") or data.get("attributes")):
            invoice = data
            break
        if isinstance(data, dict):
            results = data.get("results") or data.get("invoices") or []
            if isinstance(results, list) and results and isinstance(results[0], dict):
                invoice = results[0]
                break
        if isinstance(data, list) and data and isinstance(data[0], dict):
            invoice = data[0]
            break

    if not invoice:
        # Busca recente e cruza por order/pack
        for path, params in (
            (f"/users/{user_id}/invoices/search", {"limit": 20, "offset": 0}),
            (f"/users/{user_id}/invoices", {"limit": 20, "offset": 0}),
        ):
            try:
                data = api_request(cur, int(id_vendedor), "GET", path, params=params)
            except RuntimeError as e:
                last_err = e
                continue
            results = []
            if isinstance(data, dict):
                results = data.get("results") or data.get("invoices") or []
            elif isinstance(data, list):
                results = data
            oid = str(order_id)
            pid = str(pack_id or "")
            for item in results:
                if not isinstance(item, dict):
                    continue
                items = item.get("items") or []
                ext_orders = {
                    str(it.get("external_order_id") or "")
                    for it in items
                    if isinstance(it, dict)
                }
                pack_item = str(item.get("pack_id") or "")
                if oid in ext_orders or (pid and pack_item == pid):
                    invoice = item
                    break
                # alguns retornos trazem orders: [id, ...]
                orders = item.get("orders") or []
                if oid in {str(x) for x in orders}:
                    invoice = item
                    break
            if invoice:
                break

    if not invoice:
        return None, None, last_err or ValueError("Nota do Faturador ML não encontrada para o pedido.")

    attrs = invoice.get("attributes") if isinstance(invoice.get("attributes"), dict) else {}
    inv_id = invoice.get("id")
    meta = {
        "key": str(attrs.get("invoice_key") or invoice.get("invoice_key") or "").strip(),
        "number": invoice.get("invoice_number") or attrs.get("invoice_number"),
        "serie": invoice.get("invoice_series") or attrs.get("invoice_series"),
        "amount": invoice.get("amount"),
        "date": invoice.get("issued_date") or attrs.get("authorization_date"),
        "tipo_anexo": "nf",
        "sender_cnpj": "",
        "sender_ie": "",
    }
    issuer = invoice.get("issuer") if isinstance(invoice.get("issuer"), dict) else {}
    idents = issuer.get("identifications") if isinstance(issuer.get("identifications"), dict) else {}
    meta["sender_cnpj"] = str(idents.get("cnpj") or "").strip()
    meta["sender_ie"] = str(idents.get("ie") or "").strip()

    # Caminhos possíveis do DANFE PDF
    locations = []
    for key in ("danfe_location", "document", "danfe"):
        val = attrs.get(key)
        if isinstance(val, str) and val.startswith("/"):
            locations.append(val)
    if inv_id:
        locations.extend(
            [
                f"/users/{user_id}/invoices/{inv_id}/documents/danfe",
                f"/users/{user_id}/invoices/{inv_id}/danfe",
                f"/users/{user_id}/invoices/{inv_id}/documents?type=danfe",
            ]
        )
        for loc in list(locations):
            if loc.startswith("/danfe") or loc.startswith("/xml"):
                locations.append(f"/users/{user_id}/invoices/{inv_id}{loc}")

    for loc in locations:
        if not loc or loc.startswith("/xml"):
            continue
        try:
            raw = api_request_bytes(cur, int(id_vendedor), "GET", loc)
        except RuntimeError as e:
            last_err = e
            continue
        if _eh_pdf_bytes(raw):
            return raw, meta, None

    # Sem PDF nativo, mas com chave/número → comprovante
    if meta.get("key") or meta.get("number") not in (None, ""):
        return None, meta, last_err

    return None, None, last_err or ValueError("Faturador ML sem DANFE PDF.")


def baixar_nf_ml(
    cur,
    id_vendedor: int,
    id_pedido: int,
    pasta_destino,
    *,
    id_usuario: int | None = None,
) -> dict[str, Any]:
    """Baixa NF/declaração do ML (PDF nativo ou comprovante gerado do fiscal-info)."""
    from pathlib import Path

    from api.mercado_livre.mercado_livre import api_request, api_request_bytes, ml_conectado
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
    order_id = ped.get("id_ml_pedido")
    if ship_id:
        salvar_id_ml_shipment(cur, int(id_pedido), ship_id)

    existentes = listar_anexos_pedido(cur, int(id_pedido), id_vendedor=int(id_vendedor))
    for a in existentes:
        if a.get("tipo") in ("nf", "declaracao") and str(a.get("nome_original") or "").startswith(
            ("nf_ml_", "declaracao_ml_")
        ):
            return {
                "message": "Documento fiscal ML já anexado.",
                "anexo": a,
                "ja_existia": True,
                "tipo": a.get("tipo"),
            }

    content = None
    tipo_anexo = "nf"
    nome_base = f"nf_ml_{ship_id or order_id or id_pedido}"
    last_err = None
    invoices: list[dict[str, Any]] = []
    gerado_local = False
    pack_id = _resolver_pack_id_ml(cur, int(id_vendedor), ped, str(order_id) if order_id else None)

    # 1) Pack fiscal_documents — caminho correto do vendedor (JSON + download por id)
    if pack_id and not content:
        raw, err = _baixar_pdf_packs_fiscal_documents(cur, int(id_vendedor), pack_id)
        if raw:
            content = raw
            nome_base = f"nf_ml_{pack_id}"
        elif err:
            last_err = err
            _log.info("ML packs fiscal_documents pedido %s: %s", id_pedido, err)

    # 2) Faturador ML (users/.../invoices) — DANFE ou metadados
    faturador_meta: dict[str, Any] | None = None
    if not content and order_id:
        raw, meta, err = _baixar_pdf_faturador_ml(
            cur, int(id_vendedor), str(order_id), pack_id
        )
        if raw:
            content = raw
            nome_base = f"nf_ml_{order_id}"
        elif meta:
            faturador_meta = meta
        if err:
            last_err = err
            _log.info("ML faturador pedido %s: %s", id_pedido, err)

    # 3) fiscal-info — API de transportadoras; às vezes o seller também lê
    if ship_id:
        try:
            info = api_request(cur, int(id_vendedor), "GET", f"/shipments/{ship_id}/fiscal-info")
            invoices = _extrair_invoices_fiscal_info(info)
            if not content:
                for inv in invoices:
                    tipo_anexo = inv["tipo_anexo"]
                    nome_base = (
                        f"declaracao_ml_{ship_id}"
                        if tipo_anexo == "declaracao"
                        else f"nf_ml_{ship_id}"
                    )
                    href = inv.get("href") or ""
                    for try_href in (
                        _href_com_doctype(href, "pdf") if href else "",
                        href,
                    ):
                        if not try_href:
                            continue
                        try:
                            raw = api_request_bytes(cur, int(id_vendedor), "GET", try_href)
                        except RuntimeError as e:
                            last_err = e
                            continue
                        if _eh_pdf_bytes(raw):
                            content = raw
                            break
                        if _eh_xml_bytes(raw):
                            last_err = ValueError("ML liberou XML fiscal (sem DANFE PDF nativo).")
                    if content:
                        break
        except RuntimeError as e:
            last_err = e
            _log.info("ML fiscal-info pedido %s: %s", id_pedido, e)

    # 4) endpoints legados de invoice (PDF quando existir)
    if not content:
        candidatos: list[tuple[str, dict | None]] = []
        if ship_id:
            candidatos.extend(
                [
                    (f"/shipments/{ship_id}/invoice", {"doctype": "pdf"}),
                    (f"/shipments/{ship_id}/invoice", None),
                    (f"/shipments/{ship_id}/documents/invoice", None),
                ]
            )
        if order_id:
            candidatos.append((f"/orders/{order_id}/invoice", {"doctype": "pdf"}))
            candidatos.append((f"/orders/{order_id}/invoice", None))

        for path, params in candidatos:
            try:
                raw = api_request_bytes(
                    cur, int(id_vendedor), "GET", path, params=params
                )
                if _eh_pdf_bytes(raw):
                    content = raw
                    break
                if _eh_xml_bytes(raw):
                    last_err = ValueError("ML liberou XML fiscal (sem DANFE PDF nativo).")
            except RuntimeError as e:
                last_err = e

    # 5) Gera PDF de expedição com chave oficial (fiscal-info ou faturador)
    if not content:
        meta = None
        if invoices:
            meta = invoices[0]
        elif faturador_meta:
            meta = faturador_meta
        if meta and (meta.get("key") or meta.get("number") not in (None, "")):
            tipo_anexo = meta.get("tipo_anexo") or "nf"
            nome_base = (
                f"declaracao_ml_{ship_id or order_id or id_pedido}"
                if tipo_anexo == "declaracao"
                else f"nf_ml_{ship_id or order_id or id_pedido}"
            )
            try:
                content = _pdf_comprovante_fiscal_ml(
                    meta,
                    id_pedido_dn=int(id_pedido),
                    ship_id=str(ship_id) if ship_id else None,
                    order_id=str(order_id) if order_id else None,
                )
                gerado_local = True
            except Exception as e:
                _log.warning("Falha ao gerar PDF fiscal ML pedido %s: %s", id_pedido, e)
                last_err = e

    if not _eh_pdf_bytes(content):
        # Mensagem mais precisa: emitida no painel ≠ liberada na API do vendedor
        detalhe = str(last_err or "")
        if "fiscal info not found" in detalhe.lower() or "not found" in detalhe.lower():
            raise ValueError(
                "A nota ainda não aparece na API do Mercado Livre para este envio. "
                "Se você emitiu no painel, aguarde alguns minutos ou anexe o PDF na aba Manual."
            )
        if "forbidden" in detalhe.lower() or "403" in detalhe:
            raise ValueError(
                "O Mercado Livre não liberou a nota pela API desta conta. "
                "Anexe o PDF da NF na aba Manual, ou tente de novo mais tarde."
            )
        raise ValueError(
            _mensagem_doc_ml_amigavel(
                last_err
                or (
                    "Nota fiscal ainda não liberada na API do Mercado Livre "
                    "(emitida no painel pode demorar a aparecer)."
                ),
                tipo="fiscal",
            )
        )

    pasta = Path(pasta_destino)
    pasta.mkdir(parents=True, exist_ok=True)
    nome_arquivo = f"{nome_base}.pdf"
    destino = pasta / f"{id_pedido}_{tipo_anexo}_{int(datetime.now(timezone.utc).timestamp())}.pdf"
    destino.write_bytes(content)
    caminho_db = f"upload/tenant{id_vendedor}/pedidos/{destino.name}"
    anexo = registrar_anexo_pedido(
        cur,
        int(id_vendedor),
        int(id_pedido),
        tipo_anexo,
        nome_arquivo,
        caminho_db,
        len(content),
        id_usuario=id_usuario,
    )
    if gerado_local:
        msg = (
            "Declaração gerada a partir dos dados fiscais do Mercado Livre."
            if tipo_anexo == "declaracao"
            else "Nota fiscal gerada a partir dos dados oficiais do Mercado Livre."
        )
    else:
        msg = "Declaração ML baixada." if tipo_anexo == "declaracao" else "DANFE ML baixada."
    return {
        "message": msg,
        "anexo": anexo,
        "tipo": tipo_anexo,
        "ja_existia": False,
        "gerado_local": gerado_local,
    }


def _mensagem_doc_ml_amigavel(err: str | Exception, *, tipo: str = "documento") -> str:
    """Traduz erros técnicos do ML (HTML/JSON) em frase curta para o vendedor."""
    s = str(err or "").strip()
    low = s.lower()
    # Remove lixo HTML de gateway (tengine / 400 Bad Request)
    for marker in ("<!doctype", "<html", "<head>", "<body>"):
        idx = low.find(marker)
        if idx >= 0:
            s = s[:idx].strip(" :.-")
            low = s.lower()
            break
    s = re.sub(r"\s+", " ", s).strip()

    if "invoice_pending" in low:
        return (
            "Etiqueta bloqueada no Mercado Livre: a nota fiscal ainda não foi emitida "
            "(status: aguardando NF). Emita a NF no ML e tente de novo."
        )
    if "ready_to_ship" in low or "not_ready" in low or "status is pending" in low:
        return (
            "Etiqueta ainda não liberada. No Mercado Livre ela costuma aparecer "
            "quando o envio está pronto para despacho."
        )
    if "shipment" in low and ("not found" in low or "404" in low):
        return "Envio do Mercado Livre ainda não encontrado para este pedido."
    if "danfe" in low or ("pdf" in low and "indispon" in low) or "xml" in low:
        return (
            "Nota fiscal ainda não disponível em PDF no Mercado Livre. "
            "Assim que for emitida e liberada, tente novamente."
        )
    if "etiqueta indispon" in low or (tipo == "etiqueta" and ("400" in low or "mercadolivre" in low.replace(" ", ""))):
        return (
            "Etiqueta ainda não disponível no Mercado Livre. "
            "Confira se a NF foi emitida e se o envio já está pronto."
        )
    if tipo == "fiscal" or "nota" in low or "invoice" in low or "fiscal" in low:
        return (
            "A nota ainda não está liberada na API do Mercado Livre para integração. "
            "Emitir no painel do ML não libera na hora — aguarde alguns minutos e tente de novo, "
            "ou anexe o PDF na aba Manual."
        )
    if not s or len(s) > 180 or "bad request" in low:
        return (
            f"{'Etiqueta' if tipo == 'etiqueta' else 'Nota' if tipo == 'fiscal' else 'Documento'} "
            "ainda não disponível no Mercado Livre. Tente novamente em instantes."
        )
    # Último recurso: frase curta sem códigos HTML
    limpo = re.sub(r"mercado livre( api)? \(\d+\):\s*", "", s, flags=re.I)
    limpo = re.sub(r"shipment id \d+:\s*", "", limpo, flags=re.I)
    return limpo[:160]


def puxar_documentos_integracao_ml(
    cur,
    id_vendedor: int,
    id_pedido: int,
    pasta_destino,
    *,
    id_usuario: int | None = None,
) -> dict[str, Any]:
    """Puxa etiqueta e, se existir, NF/declaração do Mercado Livre."""
    out: dict[str, Any] = {
        "origem": "mercado_livre",
        "etiqueta": None,
        "fiscal": None,
        "avisos": [],
        "etiqueta_status": "pendente",
        "fiscal_status": "pendente",
    }
    try:
        out["etiqueta"] = baixar_etiqueta_ml(
            cur, id_vendedor, id_pedido, pasta_destino, id_usuario=id_usuario
        )
        out["etiqueta_status"] = "ok"
    except (ValueError, RuntimeError) as e:
        msg = _mensagem_doc_ml_amigavel(e, tipo="etiqueta")
        out["avisos"].append(msg)
        out["etiqueta_status"] = "pendente"
        out["etiqueta_motivo"] = msg
    try:
        out["fiscal"] = baixar_nf_ml(
            cur, id_vendedor, id_pedido, pasta_destino, id_usuario=id_usuario
        )
        out["fiscal_status"] = "ok"
    except (ValueError, RuntimeError) as e:
        msg = _mensagem_doc_ml_amigavel(e, tipo="fiscal")
        out["avisos"].append(msg)
        out["fiscal_status"] = "pendente"
        out["fiscal_motivo"] = msg

    # Não levanta erro cru: o front monta um aviso amigável com os status.
    fiscal_obj = out.get("fiscal") if isinstance(out.get("fiscal"), dict) else {}
    if out["etiqueta"] and out["fiscal"]:
        if fiscal_obj.get("gerado_local"):
            out["message"] = (
                "Etiqueta baixada. Nota anexada com os dados fiscais oficiais do ML."
            )
        else:
            out["message"] = "Etiqueta e nota baixadas do Mercado Livre."
        out["ok"] = True
    elif out["etiqueta"]:
        out["message"] = "Etiqueta baixada. A nota ainda não está disponível no ML."
        out["ok"] = True
    elif out["fiscal"]:
        out["message"] = "Nota baixada. A etiqueta ainda não está disponível no ML."
        out["ok"] = True
    else:
        out["message"] = (
            "Ainda não há documentos liberados no Mercado Livre para este pedido."
        )
        out["ok"] = False
    return out
