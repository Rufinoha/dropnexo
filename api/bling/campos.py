# api/bling/campos.py — normalização de payloads Bling (produto e pedido)
from __future__ import annotations

# ── campos_produto ────────────────────────────────────

from typing import Any


def _f(val: Any) -> float | None:
    if val in (None, ""):
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _s(val: Any, max_len: int = 0) -> str | None:
    t = str(val or "").strip()
    if not t or t.upper() in ("SEM GTIN", "SEM EAN", "N/A"):
        return None
    return t[:max_len] if max_len else t


def _primeiro_definido(*vals: Any) -> Any:
    """Retorna o primeiro valor não-None (aceita 0)."""
    for v in vals:
        if v is not None:
            return v
    return None


def _origem_fiscal_bling(produto: dict, trib: dict) -> str | None:
    """Origem ICMS 0–8; Bling envia 0 como inteiro — não usar `or`."""
    raw = _primeiro_definido(trib.get("origem"), produto.get("origem"))
    if raw in (None, ""):
        return None
    try:
        n = int(raw)
    except (TypeError, ValueError):
        t = str(raw).strip()
        return t if t in "012345678" else None
    if 0 <= n <= 8:
        return str(n)
    return None


def _condicao_bling(produto: dict) -> str | None:
    raw = produto.get("condicao")
    if raw in (None, "", 0, "0"):
        return None
    if isinstance(raw, str):
        u = raw.strip().upper()
        if u in ("NOVO", "N", "1"):
            return "NOVO"
        if u in ("USADO", "U", "2"):
            return "USADO"
        if u in ("RECONDICIONADO", "R", "3"):
            return "RECONDICIONADO"
        return u[:32] if u else None
    try:
        n = int(raw)
        return {1: "NOVO", 2: "USADO", 3: "RECONDICIONADO"}.get(n)
    except (TypeError, ValueError):
        return None


def _dimensao(produto: dict, campo: str) -> float | None:
    dims = produto.get("dimensoes") or produto.get("dimensao") or {}
    if isinstance(dims, dict):
        v = _f(dims.get(campo) or dims.get(campo.capitalize()))
        if v is not None:
            return v
    return _f(produto.get(campo))


def extrair_campos_produto_bling(produto: dict) -> dict[str, Any]:
    """Normaliza payload Bling para colunas tbl_produto / variante."""
    trib = produto.get("tributacao") or {}
    if not isinstance(trib, dict):
        trib = {}

    preco = _f(produto.get("preco")) or 0.0
    preco_custo = _f(produto.get("precoCusto") or produto.get("preco_custo"))

    gtin = _s(produto.get("gtin") or produto.get("ean"), 20)
    ncm = _s(produto.get("ncm") or trib.get("ncm"), 10)
    cest = _s(produto.get("cest") or trib.get("cest"), 10)
    origem = _origem_fiscal_bling(produto, trib)

    condicao = _condicao_bling(produto)
    referencia = condicao  # UI DropNexo usa referencia como condição

    peso_liq = _f(produto.get("pesoLiquido") or produto.get("peso_liquido"))
    peso_bruto = _f(produto.get("pesoBruto") or produto.get("peso_bruto"))

    moq = produto.get("itensPorCaixa") or produto.get("itens_por_caixa")
    try:
        moq = max(1, int(moq)) if moq not in (None, "") else 1
    except (TypeError, ValueError):
        moq = 1

    volumes = produto.get("volumes")
    try:
        volumes = int(volumes) if volumes not in (None, "") else None
    except (TypeError, ValueError):
        volumes = None

    frete = produto.get("freteGratis") or produto.get("frete_gratis")
    if isinstance(frete, str):
        frete = frete.strip().upper() in ("S", "SIM", "TRUE", "1")
    elif frete in (None, ""):
        frete = False
    else:
        frete = bool(frete)

    desc_parts = [
        (produto.get("descricaoCurta") or "").strip(),
        (produto.get("descricaoComplementar") or "").strip(),
    ]
    descricao = "\n\n".join(p for p in desc_parts if p)

    return {
        "nome": (produto.get("nome") or "").strip(),
        "sku": (produto.get("codigo") or "").strip(),
        "preco": preco,
        "preco_custo": preco_custo,
        "descricao": descricao or None,
        "unidade": ((produto.get("unidade") or "UN").strip()[:20] or "UN"),
        "marca": _s(produto.get("marca"), 120),
        "grupo": _s(produto.get("grupo"), 64),
        "gtin": gtin,
        "ncm": ncm,
        "cest": cest,
        "origem_fiscal": origem,
        "condicao": condicao,
        "referencia": referencia,
        "peso_liquido_kg": peso_liq,
        "peso_bruto_kg": peso_bruto,
        "altura_cm": _dimensao(produto, "altura"),
        "largura_cm": _dimensao(produto, "largura"),
        "profundidade_cm": _dimensao(produto, "profundidade"),
        "moq": moq,
        "volumes": volumes,
        "frete_gratis": frete,
        "producao": _s(produto.get("producao"), 20),
        "ativo": str(produto.get("situacao") or "A").upper() in ("A", "ATIVO", "1", "TRUE"),
    }


def tupla_campos_produto_sql(campos: dict) -> tuple:
    """Valores na ordem do UPDATE estendido em produtos."""
    return (
        campos.get("nome"),
        campos.get("descricao"),
        campos.get("sku"),
        campos.get("preco"),
        campos.get("preco_custo"),
        campos.get("unidade"),
        campos.get("gtin"),
        campos.get("ncm"),
        campos.get("marca"),
        campos.get("referencia"),
        campos.get("condicao"),
        campos.get("peso_liquido_kg"),
        campos.get("peso_bruto_kg"),
        campos.get("altura_cm"),
        campos.get("largura_cm"),
        campos.get("profundidade_cm"),
        campos.get("moq"),
        campos.get("volumes"),
        campos.get("frete_gratis"),
        campos.get("origem_fiscal"),
        campos.get("cest"),
        campos.get("producao"),
        campos.get("ativo"),
    )


def preco_referencia_grupo(pai: dict, variacoes: list[dict]) -> float:
    """Preço do pai: maior preço entre variações ou preço do pai."""
    precos = [_f(pai.get("preco")) or 0.0]
    for v in variacoes:
        precos.append(_f(v.get("preco")) or 0.0)
    return max(precos) if precos else 0.0


# ── campos_pedido ─────────────────────────────────────

from typing import Any

_SITUACOES_BLOQUEADAS = frozenset(
    s.lower()
    for s in (
        "cancelado",
        "em aberto",
        "em digitação",
        "em digitacao",
        "orçamento",
        "orcamento",
        "cancelada",
    )
)


def _situacao_id(raw: Any) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def extrair_situacao_pedido(pedido: dict, *, id_tenant: int | None = None) -> tuple[str, int | None]:
    """Retorna (rótulo em minúsculas, id da situação ou None)."""
    raw = pedido.get("situacao")
    if isinstance(raw, str):
        return raw.strip().lower(), None
    if not isinstance(raw, dict):
        return "", None

    sid = _situacao_id(raw.get("id"))
    nome = (raw.get("valor") or raw.get("nome") or raw.get("descricao") or "").strip()
    if not nome and sid is not None and id_tenant is not None:
        from api.bling.pedidos import _listar_situacoes_venda

        for sit in _listar_situacoes_venda(id_tenant):
            if _situacao_id(sit.get("id")) == sid:
                nome = (sit.get("nome") or sit.get("descricao") or sit.get("valor") or "").strip()
                break
    return nome.lower(), sid


def descricao_situacao_pedido(pedido: dict, *, id_tenant: int | None = None) -> str:
    """Texto legível da situação para logs e mensagens."""
    nome, sid = extrair_situacao_pedido(pedido, id_tenant=id_tenant)
    partes: list[str] = []
    if nome:
        partes.append(nome)
    if sid is not None:
        partes.append(f"id={sid}")
    if not partes:
        raw = pedido.get("situacao")
        if raw not in (None, "", {}):
            partes.append(str(raw)[:160])
    return " · ".join(partes) if partes else "(sem situação)"


def _situacao_bloqueada(nome: str) -> bool:
    if not nome:
        return False
    if nome in _SITUACOES_BLOQUEADAS:
        return True
    return "cancel" in nome


def pedido_bling_importavel(pedido: dict, *, id_tenant: int | None = None) -> bool:
    """True se o pedido no Bling está pago/confirmado o suficiente para importar."""
    if not pedido:
        return False
    nome, sid = extrair_situacao_pedido(pedido, id_tenant=id_tenant)
    if nome:
        if _situacao_bloqueada(nome):
            return False
    elif sid is None:
        return False
    itens = pedido.get("itens") or []
    return bool(itens)


def _endereco_dict_tem_dados(end: dict) -> bool:
    if not isinstance(end, dict):
        return False
    return bool(
        str(end.get("cep") or "").strip()
        or str(end.get("endereco") or end.get("logradouro") or "").strip()
    )


def _mapear_endereco_bling(end: dict) -> dict[str, str | None]:
    if not isinstance(end, dict):
        end = {}
    uf = str(end.get("uf") or end.get("estado") or "").strip()[:2] or None
    return {
        "cep": str(end.get("cep") or "").strip() or None,
        "logradouro": (str(end.get("endereco") or end.get("logradouro") or "").strip() or None),
        "numero": str(end.get("numero") or "").strip() or None,
        "complemento": str(end.get("complemento") or "").strip() or None,
        "bairro": str(end.get("bairro") or "").strip() or None,
        "cidade": (str(end.get("municipio") or end.get("cidade") or "").strip() or None),
        "uf": uf,
    }


def _endereco_entrega(pedido: dict) -> dict[str, str | None]:
    """Endereço de entrega: transporte.enderecoEntrega, etiqueta ou contato do pedido."""
    transporte = pedido.get("transporte") or {}
    candidatos: list[dict] = []
    for key in ("enderecoEntrega", "endereco", "etiqueta"):
        raw = transporte.get(key)
        if isinstance(raw, dict):
            candidatos.append(raw)
    if isinstance(transporte.get("contato"), dict):
        ce = transporte["contato"].get("endereco")
        if isinstance(ce, dict):
            candidatos.append(ce)
    contato = pedido.get("contato") or {}
    if isinstance(contato.get("endereco"), dict):
        candidatos.append(contato["endereco"])
    if _endereco_dict_tem_dados(contato):
        candidatos.append(contato)
    for cand in candidatos:
        mapped = _mapear_endereco_bling(cand)
        if _endereco_dict_tem_dados(mapped):
            return mapped
    return _mapear_endereco_bling({})


def _cliente(pedido: dict) -> dict[str, str | None]:
    contato = pedido.get("contato") or {}
    return {
        "nome": (contato.get("nome") or pedido.get("contatoNome") or "Cliente Bling").strip(),
        "email": (contato.get("email") or "").strip() or None,
        "telefone": (contato.get("telefone") or contato.get("celular") or "").strip() or None,
        "documento": (contato.get("numeroDocumento") or contato.get("cpf") or contato.get("cnpj") or "").strip()
        or None,
    }


def _parse_item(raw: dict) -> dict[str, Any] | None:
    sku = (raw.get("codigo") or raw.get("sku") or "").strip()
    if not sku:
        prod = raw.get("produto") or {}
        sku = (prod.get("codigo") or prod.get("sku") or "").strip()
    try:
        qtd = int(float(raw.get("quantidade") or 0))
    except (TypeError, ValueError):
        qtd = 0
    if qtd <= 0 or not sku:
        return None
    try:
        valor = float(raw.get("valor") or raw.get("preco") or 0)
    except (TypeError, ValueError):
        valor = 0.0
    nome = (raw.get("descricao") or raw.get("nome") or sku).strip()
    return {"sku": sku, "quantidade": qtd, "valor_bling": valor, "nome": nome}


def parse_pedido_bling(pedido: dict) -> dict[str, Any]:
    """Normaliza cabeçalho + itens de um pedido Bling."""
    cliente = _cliente(pedido)
    entrega = _endereco_entrega(pedido)
    itens: list[dict] = []
    for raw in pedido.get("itens") or []:
        item = _parse_item(raw)
        if item:
            itens.append(item)
    try:
        total = float(pedido.get("total") or pedido.get("totalProdutos") or 0)
    except (TypeError, ValueError):
        total = 0.0
    try:
        frete = float((pedido.get("transporte") or {}).get("frete") or pedido.get("valorFrete") or 0)
    except (TypeError, ValueError):
        frete = 0.0
    numero = str(pedido.get("numero") or pedido.get("id") or "").strip()
    obs = (pedido.get("observacoes") or pedido.get("observacaoInterna") or "").strip() or None
    return {
        "numero_bling": numero,
        "cliente": cliente,
        "entrega": entrega,
        "itens": itens,
        "valor_total_bling": total,
        "valor_frete": frete,
        "observacoes": obs,
        "situacao": extrair_situacao_pedido(pedido, id_tenant=None)[0],
    }
