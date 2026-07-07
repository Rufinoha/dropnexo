# api/bling/sync_pedido_status.py — DropNexo → Bling: atualização de situação do pedido
from __future__ import annotations

import json
import logging
import re
from typing import Any

from api.bling.cliente import api_request

_log = logging.getLogger(__name__)

_EVENTO_SITUACAO_NOMES: dict[str, tuple[str, ...]] = {
    "pago": ("pago", "aprovado", "confirmado", "em aberto"),
    "expedido": ("enviado", "em transporte", "despachado", "expedido", "postado"),
    "entregue": ("entregue", "atendido", "concluído", "concluido", "finalizado"),
    "cancelado": ("cancelado", "cancelada"),
}

_MODULO_PEDIDOS_ID: int | None = None
_SITUACOES_CACHE: dict[int, list[dict[str, Any]]] = {}


def _normalizar(txt: str) -> str:
    return re.sub(r"\s+", " ", (txt or "").strip().lower())


def _carregar_config_vendedor(cur, id_tenant: int) -> dict:
    cur.execute(
        """
        SELECT pedidos_modo, opcoes
        FROM tbl_integracao_bling_config
        WHERE id_tenant = %s AND contexto = 'vendedor'
        """,
        (id_tenant,),
    )
    row = cur.fetchone()
    if not row:
        return {"pedidos_modo": "importar", "opcoes": {}}
    opcoes = row[1]
    if isinstance(opcoes, str) and opcoes.strip():
        try:
            opcoes = json.loads(opcoes)
        except json.JSONDecodeError:
            opcoes = {}
    if not isinstance(opcoes, dict):
        opcoes = {}
    return {"pedidos_modo": row[0] or "importar", "opcoes": opcoes}


def _bling_conectado(cur, id_tenant: int) -> bool:
    cur.execute(
        "SELECT status FROM tbl_integracao_bling WHERE id_tenant = %s",
        (id_tenant,),
    )
    row = cur.fetchone()
    return bool(row and row[0] == "conectado")


def _id_modulo_pedidos_venda(id_tenant: int) -> int | None:
    global _MODULO_PEDIDOS_ID
    if _MODULO_PEDIDOS_ID:
        return _MODULO_PEDIDOS_ID
    try:
        body = api_request(id_tenant, "GET", "/situacoes/modulos")
        modulos = body.get("data") if isinstance(body, dict) else body
        if not isinstance(modulos, list):
            return None
        for mod in modulos:
            nome = _normalizar(str(mod.get("nome") or mod.get("descricao") or ""))
            if "pedido" in nome and "venda" in nome:
                _MODULO_PEDIDOS_ID = int(mod["id"])
                return _MODULO_PEDIDOS_ID
        for mod in modulos:
            nome = _normalizar(str(mod.get("nome") or ""))
            if nome == "vendas" or "pedidos de venda" in nome:
                _MODULO_PEDIDOS_ID = int(mod["id"])
                return _MODULO_PEDIDOS_ID
    except Exception as e:
        _log.warning("Bling módulo situações pedidos: %s", e)
    return None


def _listar_situacoes_venda(id_tenant: int) -> list[dict[str, Any]]:
    id_mod = _id_modulo_pedidos_venda(id_tenant)
    if not id_mod:
        return []
    if id_mod in _SITUACOES_CACHE:
        return _SITUACOES_CACHE[id_mod]
    try:
        body = api_request(id_tenant, "GET", f"/situacoes/modulos/{id_mod}")
        dados = body.get("data") if isinstance(body, dict) else body
        if not isinstance(dados, list):
            return []
        _SITUACOES_CACHE[id_mod] = dados
        return dados
    except Exception as e:
        _log.warning("Bling listar situações: %s", e)
        return []


def _resolver_situacao_id(id_tenant: int, evento: str, opcoes: dict) -> int | None:
    chave = f"bling_situacao_{evento}"
    manual = opcoes.get(chave)
    if manual not in (None, ""):
        try:
            return int(manual)
        except (TypeError, ValueError):
            pass
    nomes = _EVENTO_SITUACAO_NOMES.get(evento, ())
    for sit in _listar_situacoes_venda(id_tenant):
        sid = sit.get("id")
        nome = _normalizar(str(sit.get("nome") or sit.get("descricao") or ""))
        if sid is None:
            continue
        if any(n in nome for n in nomes):
            return int(sid)
    return None


def exportar_status_pedido_bling(
    cur,
    id_pedido: int,
    *,
    evento: str,
) -> bool:
    """
    Atualiza situação no Bling para pedidos importados (origem bling).
    Retorna True se enviou com sucesso.
    """
    cur.execute(
        """
        SELECT p.id, p.id_tenant_vendedor, p.origem, p.id_bling_pedido
        FROM tbl_pedido p WHERE p.id = %s
        """,
        (id_pedido,),
    )
    row = cur.fetchone()
    if not row:
        return False
    _, id_vendedor, origem, id_bling = row
    if (origem or "") != "bling" or not id_bling:
        return False
    id_vendedor = int(id_vendedor)
    if not _bling_conectado(cur, id_vendedor):
        return False

    cfg = _carregar_config_vendedor(cur, id_vendedor)
    opcoes = cfg.get("opcoes") or {}
    if opcoes.get("pedidos_exportar_status") is False:
        return False
    modo = (cfg.get("pedidos_modo") or "importar").strip()
    if modo not in ("exportar", "atualizar"):
        return False

    id_situacao = _resolver_situacao_id(id_vendedor, evento, opcoes)
    if not id_situacao:
        _log.info("Bling: situação não mapeada para evento %s (pedido %s)", evento, id_pedido)
        return False

    try:
        api_request(
            id_vendedor,
            "PATCH",
            f"/pedidos/vendas/{id_bling}/situacoes/{id_situacao}",
        )
        return True
    except Exception as e:
        _log.warning("Bling PATCH situação pedido %s: %s", id_bling, e)
        return False
