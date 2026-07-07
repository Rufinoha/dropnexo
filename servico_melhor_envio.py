# servico_melhor_envio.py — cotação e escolha de frete no pedido (vendedor)
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from api.melhor_envio.cliente import (
    adicionar_ao_carrinho,
    baixar_url_me,
    calcular_frete,
    checkout_etiquetas,
    gerar_etiquetas,
    imprimir_etiquetas,
    me_conectado,
    obter_access_token_valido,
    obter_pedido_me,
    opcoes_cotacao_me,
)
from global_utils import agora_utc
from servico_pedido import STATUS_RASCUNHO, _frete_editavel_status, obter_pedido, registrar_anexo_pedido, registrar_historico, status_vendedor_pedido

_log = logging.getLogger(__name__)
_RAIZ_UPLOAD = Path(__file__).resolve().parent

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


def _extrair_erros_me(resposta: list[Any]) -> list[str]:
    erros: list[str] = []
    for item in resposta:
        if not isinstance(item, dict):
            continue
        err = item.get("error")
        if err:
            if isinstance(err, dict):
                txt = err.get("message") or err.get("description") or str(err)
            else:
                txt = str(err)
            nome = item.get("name") or item.get("company", {}).get("name") if isinstance(item.get("company"), dict) else ""
            erros.append(f"{nome}: {txt}".strip(": ") if nome else txt)
        elif not item.get("id") and item.get("message"):
            erros.append(str(item["message"]))
    return list(dict.fromkeys(erros))[:6]


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


def _cotar_me_com_fallback_receipt(
    token: str,
    payload: dict[str, Any],
    *,
    receipt_ativo: bool,
) -> tuple[list[dict[str, Any]], list[Any], str | None]:
    """Cota no ME; se receipt ligado bloquear tudo, tenta sem aviso de recebimento."""
    resposta = calcular_frete(token, payload)
    opcoes = _normalizar_opcoes_me(resposta)
    if opcoes or not receipt_ativo:
        return opcoes, resposta, None

    opts = dict(payload.get("options") or {})
    if not opts.get("receipt"):
        return opcoes, resposta, None

    payload_sem_receipt = {**payload, "options": {**opts, "receipt": False}}
    resposta2 = calcular_frete(token, payload_sem_receipt)
    opcoes2 = _normalizar_opcoes_me(resposta2)
    if opcoes2:
        return (
            opcoes2,
            resposta2,
            "Nenhuma transportadora ofereceu aviso de recebimento nesta rota; exibindo cotações sem esse serviço.",
        )
    return opcoes, resposta2 or resposta, None


def _mensagem_sem_opcoes_me(resposta: list[Any], *, receipt_ativo: bool) -> str:
    erros = _extrair_erros_me(resposta)
    msg = "Nenhuma transportadora retornou preço para este pedido."
    if erros:
        msg += " " + " · ".join(erros)
    else:
        msg += (
            " Confira no painel Melhor Envio se há transportadoras habilitadas para a rota "
            "(Integrações → Transportadoras) e se peso/dimensões dos produtos estão em kg e cm."
        )
    if receipt_ativo:
        msg += " O aviso de recebimento estava ligado nas preferências; tente desativá-lo em Integrações → Melhor Envio."
    return msg


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
    if not _frete_editavel_status(status_vendedor_pedido(ped)):
        raise ValueError("Só é possível cotar frete em pedidos em rascunho, importados ou aguardando pagamento.")

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
    receipt_ativo = bool(me_opts["receipt"])
    opcoes, resposta, aviso = _cotar_me_com_fallback_receipt(
        token, payload, receipt_ativo=receipt_ativo
    )
    if not opcoes:
        raise ValueError(_mensagem_sem_opcoes_me(resposta, receipt_ativo=receipt_ativo))

    out = {
        "id_pedido": id_pedido,
        "cep_origem": cep_orig,
        "cep_destino": cep_dest,
        "opcoes": opcoes,
    }
    if aviso:
        out["aviso"] = aviso
    return out


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
    if not _frete_editavel_status(status_vendedor_pedido(ped)):
        raise ValueError("Só é possível escolher frete em pedidos em rascunho, importados ou aguardando pagamento.")

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


def definir_modo_frete_manual(
    cur,
    id_vendedor: int,
    id_pedido: int,
    *,
    valor_frete: float | None = None,
    codigo_rastreio: str | None = None,
    transportadora: str | None = None,
) -> dict:
    """Etiqueta própria (PDF) — não usa integração Melhor Envio."""
    if not _pedido_tem_colunas_me(cur):
        raise ValueError("Execute a migração SQL 066_pedido_melhor_envio no banco.")
    ped = obter_pedido(cur, id_pedido, id_vendedor=id_vendedor)
    if not ped:
        raise ValueError("Pedido não encontrado.")
    if not _frete_editavel_status(status_vendedor_pedido(ped)):
        raise ValueError("Só é possível alterar o frete em pedidos em rascunho, importados ou aguardando pagamento.")

    vf = round(_float(valor_frete), 2) if valor_frete is not None else _float(ped.get("valor_frete"))
    rastreio = (codigo_rastreio or "").strip() or None
    transp = (transportadora or "").strip() or None

    cur.execute(
        """
        UPDATE tbl_pedido SET
            valor_frete = %s,
            me_service_id = NULL,
            me_preco_cotado = NULL,
            me_prazo_dias = NULL,
            me_cotacao_json = NULL,
            me_order_id = NULL,
            me_protocol = NULL,
            me_etiqueta_status = 'manual',
            codigo_rastreio = COALESCE(%s, codigo_rastreio),
            transportadora = COALESCE(%s, transportadora),
            atualizado_em = %s
        WHERE id = %s AND id_tenant_vendedor = %s
        """,
        (vf, rastreio, transp, agora_utc(), id_pedido, id_vendedor),
    )
    return {
        "id_pedido": id_pedido,
        "frete_modo": "manual",
        "valor_frete": vf,
        "codigo_rastreio": rastreio or "",
        "transportadora": transp or "",
    }


def definir_modo_frete_melhor_envio(cur, id_vendedor: int, id_pedido: int) -> dict:
    """Volta ao fluxo Melhor Envio (cotação integrada)."""
    if not _pedido_tem_colunas_me(cur):
        raise ValueError("Execute a migração SQL 066_pedido_melhor_envio no banco.")
    ped = obter_pedido(cur, id_pedido, id_vendedor=id_vendedor)
    if not ped:
        raise ValueError("Pedido não encontrado.")
    if not _frete_editavel_status(status_vendedor_pedido(ped)):
        raise ValueError("Só é possível alterar o frete em pedidos em rascunho, importados ou aguardando pagamento.")

    cur.execute(
        """
        UPDATE tbl_pedido SET
            valor_frete = 0,
            me_service_id = NULL,
            me_preco_cotado = NULL,
            me_prazo_dias = NULL,
            me_cotacao_json = NULL,
            me_order_id = NULL,
            me_protocol = NULL,
            me_etiqueta_status = NULL,
            atualizado_em = %s
        WHERE id = %s AND id_tenant_vendedor = %s
        """,
        (agora_utc(), id_pedido, id_vendedor),
    )
    return {"id_pedido": id_pedido, "frete_modo": "melhor_envio"}


def salvar_frete_manual(
    cur,
    id_vendedor: int,
    id_pedido: int,
    *,
    valor_frete: float | None = None,
    codigo_rastreio: str | None = None,
    transportadora: str | None = None,
) -> dict:
    """Atualiza campos opcionais do frete manual (referência / rastreio)."""
    return definir_modo_frete_manual(
        cur,
        id_vendedor,
        id_pedido,
        valor_frete=valor_frete,
        codigo_rastreio=codigo_rastreio,
        transportadora=transportadora,
    )


def frete_resumo_pedido(cur, id_pedido: int) -> dict:
    if not _pedido_tem_colunas_me(cur):
        return {}
    cur.execute(
        """
        SELECT valor_frete, me_service_id, me_preco_cotado, me_prazo_dias, me_cotacao_json,
               me_etiqueta_status, me_order_id, me_protocol, codigo_rastreio, transportadora
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
        "me_order_id": row[6] or "",
        "me_protocol": row[7] or "",
        "codigo_rastreio": row[8] or "",
        "transportadora": row[9] or "",
        "frete_nome": (cotacao.get("name") if cotacao else "") or "",
        "frete_transportadora": (
            cotacao.get("company", {}).get("name") if isinstance(cotacao.get("company"), dict) else ""
        ),
        "frete_modo": "manual" if (row[5] or "") == "manual" else ("melhor_envio" if row[1] else ""),
    }


def _so_digitos(val: str | None) -> str:
    return re.sub(r"\D", "", val or "")


def _telefone_me(val: str | None) -> str:
    d = _so_digitos(val)
    return d[:11] if d else "11999999999"


def _doc_pf_pj(documento: str | None) -> tuple[str, str]:
    d = _so_digitos(documento)
    if len(d) == 14:
        return "", d
    if len(d) == 11:
        return d, ""
    return d, ""


def _deposito_origem_pedido(cur, id_pedido: int, id_fornecedor: int) -> dict[str, Any]:
    cur.execute(
        """
        SELECT d.id, d.cep, d.logradouro, d.numero, d.complemento, d.bairro, d.cidade, d.uf,
               d.remetente_nome, d.remetente_documento,
               t.documento, t.razao_social, t.nome_fantasia, t.nome,
               t.email_comercial, t.telefone_comercial, t.celular_comercial,
               t.inscricao_estadual, t.ie_isento
        FROM tbl_pedido_item pi
        JOIN tbl_deposito_expedicao d ON d.id = pi.id_deposito_fornecedor
        JOIN tbl_tenant t ON t.id = d.id_tenant
        WHERE pi.id_pedido = %s AND d.ativo = TRUE
        LIMIT 1
        """,
        (id_pedido,),
    )
    row = cur.fetchone()
    if not row:
        cur.execute(
            """
            SELECT d.id, d.cep, d.logradouro, d.numero, d.complemento, d.bairro, d.cidade, d.uf,
                   d.remetente_nome, d.remetente_documento,
                   t.documento, t.razao_social, t.nome_fantasia, t.nome,
                   t.email_comercial, t.telefone_comercial, t.celular_comercial,
                   t.inscricao_estadual, t.ie_isento
            FROM tbl_deposito_expedicao d
            JOIN tbl_tenant t ON t.id = d.id_tenant
            WHERE d.id_tenant = %s AND d.ativo = TRUE
            ORDER BY d.principal DESC, d.id
            LIMIT 1
            """,
            (id_fornecedor,),
        )
        row = cur.fetchone()
    if not row:
        raise ValueError("Depósito de expedição do fornecedor não encontrado.")
    doc_pf, doc_pj = _doc_pf_pj(row[9] or row[10])
    ie = (row[17] or "").strip()
    if row[18]:
        ie = "ISENTO"
    nome = (row[8] or row[12] or row[13] or row[11] or "Remetente").strip()
    return {
        "name": nome[:255],
        "email": (row[14] or "contato@dropnexo.com.br").strip(),
        "phone": _telefone_me(row[15] or row[16]),
        "document": doc_pf,
        "company_document": doc_pj,
        "state_register": ie or "ISENTO",
        "address": (row[2] or "").strip(),
        "complement": (row[4] or "").strip(),
        "number": (row[3] or "S/N").strip()[:20],
        "district": (row[5] or "").strip(),
        "city": (row[6] or "").strip(),
        "postal_code": _cep_digitos(row[1]),
        "state_abbr": (row[7] or "").strip()[:2].upper(),
        "country_id": "BR",
    }


def _destinatario_pedido(ped: dict) -> dict[str, Any]:
    doc_pf, doc_pj = _doc_pf_pj(ped.get("cliente_documento"))
    if not doc_pf and not doc_pj:
        doc_pf = "00000000000"
    return {
        "name": (ped.get("cliente_nome") or "Destinatário").strip()[:255],
        "email": (ped.get("cliente_email") or "cliente@email.com").strip(),
        "phone": _telefone_me(ped.get("cliente_telefone")),
        "document": doc_pf,
        "company_document": doc_pj,
        "state_register": "ISENTO",
        "address": (ped.get("entrega_logradouro") or "").strip(),
        "complement": (ped.get("entrega_complemento") or "").strip(),
        "number": (ped.get("entrega_numero") or "S/N").strip()[:20],
        "district": (ped.get("entrega_bairro") or "").strip(),
        "city": (ped.get("entrega_cidade") or "").strip(),
        "postal_code": _cep_digitos(ped.get("entrega_cep")),
        "state_abbr": (ped.get("entrega_uf") or "").strip()[:2].upper(),
        "country_id": "BR",
    }


def _montar_payload_carrinho(
    cur,
    id_pedido: int,
    ped: dict,
    *,
    service_id: int,
) -> dict[str, Any]:
    id_forn = int(ped["id_tenant_fornecedor"])
    produtos = _produtos_me_pedido(cur, id_pedido)
    me_opts = opcoes_cotacao_me(cur, int(ped["id_tenant_vendedor"]))
    insurance = round(sum(_float(p.get("insurance_value", 0)) * int(p.get("quantity", 1)) for p in produtos), 2)
    volumes = [
        {
            "height": p["height"],
            "width": p["width"],
            "length": p["length"],
            "weight": round(_float(p["weight"]) * int(p["quantity"]), 3),
        }
        for p in produtos
    ]
    if len(volumes) > 1:
        volumes = [
            {
                "height": max(v["height"] for v in volumes),
                "width": max(v["width"] for v in volumes),
                "length": max(v["length"] for v in volumes),
                "weight": round(sum(v["weight"] for v in volumes), 3),
            }
        ]
    decl_produtos = [
        {
            "name": (p.get("nome") or p.get("id") or "Produto")[:255],
            "quantity": str(int(p["quantity"])),
            "unitary_value": str(round(_float(p.get("insurance_value", 0.01)), 2)),
        }
        for p in produtos
    ]
    return {
        "service": int(service_id),
        "from": _deposito_origem_pedido(cur, id_pedido, id_forn),
        "to": _destinatario_pedido(ped),
        "products": decl_produtos,
        "volumes": volumes,
        "options": {
            "platform": "DropNexo",
            "reminder": f"Pedido {ped.get('numero') or id_pedido}",
            "insurance_value": max(insurance, 0.01),
            "receipt": me_opts["receipt"],
            "own_hand": me_opts["own_hand"],
            "reverse": False,
            "non_commercial": True,
            "tags": [{"tag": f"dropnexo-pedido-{id_pedido}", "url": ""}],
        },
    }


def _atualizar_status_etiqueta(
    cur,
    id_pedido: int,
    *,
    status: str,
    me_order_id: str | None = None,
    me_protocol: str | None = None,
    codigo_rastreio: str | None = None,
    transportadora: str | None = None,
) -> None:
    cur.execute(
        """
        UPDATE tbl_pedido SET
            me_etiqueta_status = %s,
            me_order_id = COALESCE(NULLIF(%s, ''), me_order_id),
            me_protocol = COALESCE(NULLIF(%s, ''), me_protocol),
            codigo_rastreio = COALESCE(NULLIF(%s, ''), codigo_rastreio),
            transportadora = COALESCE(NULLIF(%s, ''), transportadora),
            atualizado_em = %s
        WHERE id = %s
        """,
        (
            status,
            me_order_id or "",
            me_protocol or "",
            codigo_rastreio or "",
            transportadora or "",
            agora_utc(),
            id_pedido,
        ),
    )


def _salvar_pdf_etiqueta_anexo(
    cur,
    id_vendedor: int,
    id_pedido: int,
    pdf_bytes: bytes,
    *,
    id_usuario: int | None = None,
) -> dict | None:
    if not pdf_bytes or len(pdf_bytes) < 100:
        return None
    pasta = _RAIZ_UPLOAD / "upload" / f"tenant{id_vendedor}" / "pedidos"
    pasta.mkdir(parents=True, exist_ok=True)
    nome_arquivo = f"{id_pedido}_etiqueta_me_{int(time.time())}.pdf"
    destino = pasta / nome_arquivo
    destino.write_bytes(pdf_bytes)
    caminho_db = f"upload/tenant{id_vendedor}/pedidos/{nome_arquivo}"
    try:
        return registrar_anexo_pedido(
            cur,
            id_vendedor,
            id_pedido,
            "etiqueta",
            f"etiqueta_melhor_envio_{id_pedido}.pdf",
            caminho_db,
            len(pdf_bytes),
            id_usuario=id_usuario,
        )
    except ValueError as e:
        _log.warning("Anexo etiqueta ME pedido %s: %s", id_pedido, e)
        return None


def _extrair_url_impressao(resposta_print: dict) -> str:
    if not resposta_print:
        return ""
    if isinstance(resposta_print.get("url"), str):
        return resposta_print["url"].strip()
    link = resposta_print.get("link")
    if isinstance(link, str):
        return link.strip()
    for val in resposta_print.values():
        if isinstance(val, dict) and isinstance(val.get("url"), str):
            return val["url"].strip()
    return ""


def contratar_etiqueta_pedido(
    cur,
    id_vendedor: int,
    id_pedido: int,
    *,
    id_usuario: int | None = None,
    forcar: bool = False,
) -> dict[str, Any]:
    """Compra, gera e anexa etiqueta ME após pagamento do pedido."""
    if not _pedido_tem_colunas_me(cur):
        raise ValueError("Execute a migração SQL 066_pedido_melhor_envio no banco.")
    if not me_conectado(cur, id_vendedor):
        raise ValueError("Conecte sua conta Melhor Envio em Integrações → Frete.")

    cur.execute(
        """
        SELECT me_service_id, me_etiqueta_status, me_order_id, numero
        FROM tbl_pedido
        WHERE id = %s AND id_tenant_vendedor = %s
        """,
        (id_pedido, id_vendedor),
    )
    row = cur.fetchone()
    if not row:
        raise ValueError("Pedido não encontrado.")
    service_id, etiq_status, me_order_existente, numero = row
    if not service_id:
        return {"ignorado": True, "message": "Pedido sem frete Melhor Envio selecionado."}
    if etiq_status == "gerada" and me_order_existente and not forcar:
        return {"ignorado": True, "message": "Etiqueta já gerada.", "me_order_id": me_order_existente}
    if etiq_status not in ("pendente", "erro", None, "") and not forcar:
        return {"ignorado": True, "message": f"Status de etiqueta: {etiq_status}."}

    ped = obter_pedido(cur, id_pedido, id_vendedor=id_vendedor)
    if not ped:
        raise ValueError("Pedido não encontrado.")

    token = obter_access_token_valido(cur, id_vendedor)
    order_id = str(me_order_existente or "").strip()

    try:
        if not order_id:
            payload = _montar_payload_carrinho(cur, id_pedido, ped, service_id=int(service_id))
            cart = adicionar_ao_carrinho(token, payload)
            order_id = str(cart.get("id") or "").strip()
            protocolo = str(cart.get("protocol") or "").strip()
            if not order_id:
                raise RuntimeError("Melhor Envio não retornou ID da etiqueta.")
            _atualizar_status_etiqueta(
                cur, id_pedido, status="pendente", me_order_id=order_id, me_protocol=protocolo
            )

        try:
            checkout_etiquetas(token, [order_id])
        except RuntimeError as e:
            msg_l = str(e).lower()
            if "pago" not in msg_l and "paid" not in msg_l and "checkout" not in msg_l:
                raise

        gerar_etiquetas(token, [order_id])
        detalhe = obter_pedido_me(token, order_id)
        tracking = (
            (detalhe.get("tracking") or detalhe.get("self_tracking") or "").strip()
            if detalhe
            else ""
        )
        protocolo = (detalhe.get("protocol") or "").strip() if detalhe else ""
        transportadora = ""
        if isinstance(detalhe.get("service"), dict):
            comp = detalhe["service"].get("company")
            if isinstance(comp, dict):
                transportadora = (comp.get("name") or "").strip()

        print_resp = imprimir_etiquetas(token, [order_id], mode="public")
        url_pdf = _extrair_url_impressao(print_resp)
        anexo = None
        if url_pdf:
            pdf = baixar_url_me(token, url_pdf)
            anexo = _salvar_pdf_etiqueta_anexo(cur, id_vendedor, id_pedido, pdf, id_usuario=id_usuario)

        _atualizar_status_etiqueta(
            cur,
            id_pedido,
            status="gerada",
            me_order_id=order_id,
            me_protocol=protocolo,
            codigo_rastreio=tracking,
            transportadora=transportadora or "Melhor Envio",
        )
        msg = f"Etiqueta Melhor Envio gerada para o pedido {numero or id_pedido}."
        if tracking:
            msg += f" Rastreio: {tracking}."
        registrar_historico(cur, id_pedido, "etiqueta_me", msg, id_usuario)
        return {
            "ok": True,
            "me_order_id": order_id,
            "me_protocol": protocolo,
            "codigo_rastreio": tracking,
            "anexo": anexo,
            "message": msg,
        }
    except Exception as e:
        _log.exception("Falha etiqueta ME pedido %s", id_pedido)
        _atualizar_status_etiqueta(cur, id_pedido, status="erro")
        registrar_historico(
            cur,
            id_pedido,
            "etiqueta_me_erro",
            f"Falha ao gerar etiqueta ME: {str(e)[:400]}",
            id_usuario,
        )
        raise


def tentar_contratar_etiqueta_apos_pagamento(
    cur,
    id_pedido: int,
    *,
    id_usuario: int | None = None,
) -> dict[str, Any] | None:
    """Chamado após pagamento confirmado — não interrompe o fluxo em caso de erro."""
    if not _pedido_tem_colunas_me(cur):
        return None
    cur.execute(
        """
        SELECT id_tenant_vendedor, me_service_id, me_etiqueta_status
        FROM tbl_pedido WHERE id = %s
        """,
        (id_pedido,),
    )
    row = cur.fetchone()
    if not row:
        return None
    id_vendedor, service_id, etiq_status = int(row[0]), row[1], row[2] or ""
    if not service_id or etiq_status in ("manual",):
        return None
    if etiq_status not in ("pendente", "erro", ""):
        return None
    if not me_conectado(cur, id_vendedor):
        _log.info("ME etiqueta: vendedor %s não conectado (pedido %s).", id_vendedor, id_pedido)
        return None
    try:
        return contratar_etiqueta_pedido(cur, id_vendedor, id_pedido, id_usuario=id_usuario)
    except Exception as e:
        _log.warning("ME etiqueta automática pedido %s: %s", id_pedido, e)
        return {"ok": False, "message": str(e)}
