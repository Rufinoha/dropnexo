# api/bling/campos_produto.py — extração de campos Bling → DropNexo
from __future__ import annotations

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
    origem = _s(trib.get("origem") or produto.get("origem"), 4)

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
    """Valores na ordem do UPDATE estendido em sync_produtos."""
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
