# servico_melhor_envio.py — cotação e escolha de frete no pedido (vendedor)
from __future__ import annotations

import json
import re
from typing import Any

from api.melhor_envio.cliente import (
    calcular_frete,
    me_conectado,
    obter_access_token_valido,
    opcoes_cotacao_me,
)
from global_utils import agora_utc
from servico_pedido import STATUS_RASCUNHO, obter_pedido

_COLUNAS_ME_OK: bool | None = None


def _float(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _cep_digitos(cep: str | None) -> str:
    return re.sub(r"\D", "", cep or "")


def _pedido_tem_colunas_me(cur) -> bool:
    global _COLUNAS_ME_OK
    if _COLUNAS_ME_OK is not None:
        return _COLUNAS_ME_OK
    cur.execute(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'tbl_pedido'
          AND column_name = 'me_service_id'
        LIMIT 1
        """
    )
    _COLUNAS_ME_OK = cur.fetchone() is not None
    return _COLUNAS_ME_OK


def _dimensoes_efetivas(variante: dict, produto: dict) -> dict[str, float]:
    out = {
        "peso_bruto_kg": variante.get("peso_bruto_kg"),
        "altura_cm": variante.get("altura_cm"),
        "largura_cm": variante.get("largura_cm"),
        "profundidade_cm": variante.get("profundidade_cm"),
    }
    if variante.get("herda_pai", True):
        for k in out:
            if out[k] in (None, "", 0) and produto.get(k) not in (None, "", 0):
                out[k] = produto.get(k)
    return {k: _float(v) for k, v in out.items()}


def _cep_origem_pedido(cur, id_pedido: int, id_fornecedor: int) -> str:
    cur.execute(
        """
        SELECT DISTINCT d.cep
        FROM tbl_pedido_item pi
        JOIN tbl_deposito_expedicao d ON d.id = pi.id_deposito_fornecedor
        WHERE pi.id_pedido = %s AND d.ativo = TRUE AND d.cep IS NOT NULL
        """,
        (id_pedido,),
    )
    ceps = {_cep_digitos(r[0]) for r in cur.fetchall() if _cep_digitos(r[0])}
    if len(ceps) > 1:
        raise ValueError("Itens do pedido usam depósitos com CEPs diferentes. Unifique a origem.")
    if len(ceps) == 1:
        return next(iter(ceps))

    cur.execute(
        """
        SELECT cep FROM tbl_deposito_expedicao
        WHERE id_tenant = %s AND ativo = TRUE AND principal = TRUE
        ORDER BY id LIMIT 1
        """,
        (id_fornecedor,),
    )
    row = cur.fetchone()
    cep = _cep_digitos(row[0]) if row else ""
    if cep:
        return cep

    cur.execute(
        """
        SELECT cep FROM tbl_deposito_expedicao
        WHERE id_tenant = %s AND ativo = TRUE
        ORDER BY principal DESC, id LIMIT 1
        """,
        (id_fornecedor,),
    )
    row = cur.fetchone()
    cep = _cep_digitos(row[0]) if row else ""
    if not cep:
        raise ValueError("Fornecedor sem depósito de expedição com CEP cadastrado.")
    return cep


def _produtos_me_pedido(cur, id_pedido: int) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT pi.sku, pi.nome_produto, pi.quantidade, pi.preco_venda, pi.valor_drop,
               v.herda_pai, v.peso_bruto_kg, v.altura_cm, v.largura_cm, v.profundidade_cm,
               p.peso_bruto_kg, p.altura_cm, p.largura_cm, p.profundidade_cm
        FROM tbl_pedido_item pi
        JOIN tbl_produto_variante v ON v.id = pi.id_variante
        JOIN tbl_produto p ON p.id = pi.id_produto
        WHERE pi.id_pedido = %s
        ORDER BY pi.id
        """,
        (id_pedido,),
    )
    produtos: list[dict[str, Any]] = []
    faltando: list[str] = []
    for row in cur.fetchall():
        variante = {
            "herda_pai": bool(row[5]),
            "peso_bruto_kg": row[6],
            "altura_cm": row[7],
            "largura_cm": row[8],
            "profundidade_cm": row[9],
        }
        produto = {
            "peso_bruto_kg": row[10],
            "altura_cm": row[11],
            "largura_cm": row[12],
            "profundidade_cm": row[13],
        }
        dims = _dimensoes_efetivas(variante, produto)
        sku = (row[0] or "").strip() or "item"
        nome = (row[1] or sku).strip()
        qtd = int(row[2] or 0)
        seguro = _float(row[3]) or _float(row[4])
        peso = dims["peso_bruto_kg"]
        alt = dims["altura_cm"]
        larg = dims["largura_cm"]
        comp = dims["profundidade_cm"]
        if qtd <= 0 or peso <= 0 or alt <= 0 or larg <= 0 or comp <= 0:
            faltando.append(sku)
            continue
        produtos.append(
            {
                "id": sku,
                "width": max(1, int(round(larg))),
                "height": max(1, int(round(alt))),
                "length": max(1, int(round(comp))),
                "weight": round(peso, 3),
                "insurance_value": round(max(seguro, 0.01), 2),
                "quantity": qtd,
                "nome": nome,
            }
        )
    if faltando:
        lista = ", ".join(faltando[:5])
        sufixo = "…" if len(faltando) > 5 else ""
        raise ValueError(
            f"Peso e dimensões obrigatórios para cotar frete. Revise: {lista}{sufixo}"
        )
    if not produtos:
        raise ValueError("Pedido sem itens para cotação de frete.")
    return produtos


def _normalizar_opcoes_me(resposta: list[Any]) -> list[dict[str, Any]]:
    opcoes: list[dict[str, Any]] = []
    for item in resposta:
        if not isinstance(item, dict) or item.get("error"):
            continue
        sid = item.get("id")
        preco = item.get("custom_price") or item.get("price")
        if sid is None or preco in (None, ""):
            continue
        prazo = item.get("custom_delivery_time")
        if prazo is None:
            prazo = item.get("delivery_time")
        empresa = item.get("company") if isinstance(item.get("company"), dict) else {}
        opcoes.append(
            {
                "id": int(sid),
                "nome": item.get("name") or "",
                "preco": round(_float(preco), 2),
                "prazo_dias": int(prazo) if prazo is not None else None,
                "transportadora": empresa.get("name") or "",
                "logo": empresa.get("picture") or "",
                "raw": item,
            }
        )
    opcoes.sort(key=lambda o: o["preco"])
    return opcoes


def status_melhor_envio_vendedor(cur, id_vendedor: int) -> dict:
    return {
        "conectado": me_conectado(cur, id_vendedor),
        "colunas_ok": _pedido_tem_colunas_me(cur),
    }


def cotar_frete_pedido(cur, id_vendedor: int, id_pedido: int) -> dict:
    if not _pedido_tem_colunas_me(cur):
        raise ValueError("Execute a migração SQL 066_pedido_melhor_envio no banco.")
    if not me_conectado(cur, id_vendedor):
        raise ValueError("Conecte sua conta Melhor Envio em Integrações → Frete.")

    ped = obter_pedido(cur, id_pedido, id_vendedor=id_vendedor)
    if not ped:
        raise ValueError("Pedido não encontrado.")
    if ped["status"] != STATUS_RASCUNHO:
        raise ValueError("Só é possível cotar frete em pedidos em rascunho.")

    cep_dest = _cep_digitos(ped.get("entrega_cep"))
    if len(cep_dest) != 8:
        raise ValueError("Informe o CEP de entrega no passo Endereço.")

    id_forn = int(ped["id_tenant_fornecedor"])
    cep_orig = _cep_origem_pedido(cur, id_pedido, id_forn)
    produtos = _produtos_me_pedido(cur, id_pedido)
    me_opts = opcoes_cotacao_me(cur, id_vendedor)
    payload = {
        "from": {"postal_code": cep_orig},
        "to": {"postal_code": cep_dest},
        "products": [
            {
                "id": p["id"],
                "width": p["width"],
                "height": p["height"],
                "length": p["length"],
                "weight": p["weight"],
                "insurance_value": p["insurance_value"],
                "quantity": p["quantity"],
            }
            for p in produtos
        ],
        "options": {"receipt": me_opts["receipt"], "own_hand": me_opts["own_hand"]},
    }

    token = obter_access_token_valido(cur, id_vendedor)
    resposta = calcular_frete(token, payload)
    opcoes = _normalizar_opcoes_me(resposta)
    if not opcoes:
        raise ValueError("Nenhuma opção de frete retornada para este pedido.")

    return {
        "id_pedido": id_pedido,
        "cep_origem": cep_orig,
        "cep_destino": cep_dest,
        "opcoes": opcoes,
    }


def escolher_frete_pedido(
    cur,
    id_vendedor: int,
    id_pedido: int,
    service_id: int,
    *,
    opcao_raw: dict | None = None,
) -> dict:
    if not _pedido_tem_colunas_me(cur):
        raise ValueError("Execute a migração SQL 066_pedido_melhor_envio no banco.")

    ped = obter_pedido(cur, id_pedido, id_vendedor=id_vendedor)
    if not ped:
        raise ValueError("Pedido não encontrado.")
    if ped["status"] != STATUS_RASCUNHO:
        raise ValueError("Só é possível escolher frete em pedidos em rascunho.")

    if opcao_raw:
        opcao = opcao_raw
    else:
        cot = cotar_frete_pedido(cur, id_vendedor, id_pedido)
        opcao = next((o["raw"] for o in cot["opcoes"] if int(o["id"]) == int(service_id)), None)
        if not opcao:
            raise ValueError("Opção de frete não encontrada. Cote novamente.")

    preco = round(_float(opcao.get("custom_price") or opcao.get("price")), 2)
    prazo = opcao.get("custom_delivery_time")
    if prazo is None:
        prazo = opcao.get("delivery_time")

    cur.execute(
        """
        UPDATE tbl_pedido SET
            valor_frete = %s,
            me_service_id = %s,
            me_preco_cotado = %s,
            me_prazo_dias = %s,
            me_cotacao_json = %s::jsonb,
            me_etiqueta_status = 'pendente',
            atualizado_em = %s
        WHERE id = %s AND id_tenant_vendedor = %s
        """,
        (
            preco,
            int(service_id),
            preco,
            int(prazo) if prazo is not None else None,
            json.dumps(opcao, ensure_ascii=False),
            agora_utc(),
            id_pedido,
            id_vendedor,
        ),
    )
    return {
        "id_pedido": id_pedido,
        "valor_frete": preco,
        "me_service_id": int(service_id),
        "me_prazo_dias": int(prazo) if prazo is not None else None,
        "nome": opcao.get("name") or "",
    }


def limpar_frete_pedido(cur, id_pedido: int) -> None:
    if not _pedido_tem_colunas_me(cur):
        return
    cur.execute(
        """
        UPDATE tbl_pedido SET
            valor_frete = 0,
            me_service_id = NULL,
            me_preco_cotado = NULL,
            me_prazo_dias = NULL,
            me_cotacao_json = NULL,
            me_etiqueta_status = NULL,
            atualizado_em = %s
        WHERE id = %s
        """,
        (agora_utc(), id_pedido),
    )


def frete_resumo_pedido(cur, id_pedido: int) -> dict:
    if not _pedido_tem_colunas_me(cur):
        return {}
    cur.execute(
        """
        SELECT valor_frete, me_service_id, me_preco_cotado, me_prazo_dias, me_cotacao_json, me_etiqueta_status
        FROM tbl_pedido WHERE id = %s
        """,
        (id_pedido,),
    )
    row = cur.fetchone()
    if not row:
        return {}
    cotacao = row[4]
    if isinstance(cotacao, str) and cotacao.strip():
        try:
            cotacao = json.loads(cotacao)
        except json.JSONDecodeError:
            cotacao = {}
    elif not isinstance(cotacao, dict):
        cotacao = {}
    return {
        "valor_frete": _float(row[0]),
        "me_service_id": row[1],
        "me_preco_cotado": _float(row[2]) if row[2] is not None else None,
        "me_prazo_dias": row[3],
        "me_etiqueta_status": row[5] or "",
        "frete_nome": (cotacao.get("name") if cotacao else "") or "",
        "transportadora": (
            cotacao.get("company", {}).get("name") if isinstance(cotacao.get("company"), dict) else ""
        ),
    }
