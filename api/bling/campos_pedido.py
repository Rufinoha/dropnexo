# api/bling/campos_pedido.py — parse de pedidos de venda Bling API v3
from __future__ import annotations

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
        from api.bling.sync_pedido_status import _listar_situacoes_venda

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


def _endereco_entrega(pedido: dict) -> dict[str, str | None]:
    transporte = pedido.get("transporte") or {}
    end = transporte.get("enderecoEntrega") or transporte.get("endereco") or {}
    if not end and isinstance(transporte.get("contato"), dict):
        end = transporte["contato"].get("endereco") or {}
    return {
        "cep": (end.get("cep") or "").strip() or None,
        "logradouro": (end.get("endereco") or end.get("logradouro") or "").strip() or None,
        "numero": (end.get("numero") or "").strip() or None,
        "complemento": (end.get("complemento") or "").strip() or None,
        "bairro": (end.get("bairro") or "").strip() or None,
        "cidade": (end.get("municipio") or end.get("cidade") or "").strip() or None,
        "uf": ((end.get("uf") or end.get("estado") or "")[:2] or None),
    }


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
