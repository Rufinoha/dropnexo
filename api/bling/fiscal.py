# api/bling/fiscal.py — DANFE (PDF) via Bling API v3
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import requests

from api.bling.cliente import api_request, obter_access_token_valido
from core.pedidos.servico import listar_anexos_pedido, obter_pedido, registrar_anexo_pedido

_log = logging.getLogger(__name__)


def _parece_pdf(content: bytes) -> bool:
    return bool(content) and content[:4] == b"%PDF"


def _baixar_url_pdf(url: str, *, bearer: str | None = None) -> bytes | None:
    headers = {"Accept": "application/pdf,*/*"}
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    try:
        r = requests.get(url, headers=headers, timeout=45, allow_redirects=True)
        if r.status_code >= 400:
            return None
        data = r.content or b""
        if _parece_pdf(data):
            return data
        # Alguns links retornam HTML de erro; rejeita.
        return None
    except Exception as e:
        _log.debug("Falha ao baixar DANFE %s: %s", url[:80], e)
        return None


def _extrair_links_danfe(nfe: dict) -> list[str]:
    links: list[str] = []
    for chave in ("linkDanfe", "linkPDF", "linkDanfeSimplificado", "urlDanfe", "urlPDF"):
        v = (nfe.get(chave) or "").strip()
        if v.startswith("http"):
            links.append(v)
    # aninhados comuns
    for bloco_key in ("transporte", "documento", "pdf"):
        bloco = nfe.get(bloco_key)
        if isinstance(bloco, dict):
            for chave in ("linkDanfe", "linkPDF", "url"):
                v = (bloco.get(chave) or "").strip()
                if v.startswith("http"):
                    links.append(v)
    # dedupe preservando ordem
    seen: set[str] = set()
    out: list[str] = []
    for u in links:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _listar_nfe_por_pedido_venda(id_tenant: int, id_bling_pedido: str) -> list[dict]:
    """Tenta localizar NFes ligadas ao pedido de venda no Bling."""
    candidatos: list[dict] = []
    # Filtro por número/id do pedido (quando a API aceitar)
    for params in (
        {"idPedido": id_bling_pedido, "limite": 50},
        {"numeroPedidoLoja": id_bling_pedido, "limite": 50},
        {"limite": 50},
    ):
        try:
            body = api_request(id_tenant, "GET", "/nfe", params=params)
        except Exception:
            continue
        data = body.get("data")
        if not isinstance(data, list):
            continue
        for item in data:
            if not isinstance(item, dict):
                continue
            # Preferir notas cujo pedido bate
            ped = item.get("pedido") if isinstance(item.get("pedido"), dict) else {}
            pid = str(ped.get("id") or item.get("idPedido") or "")
            if params.get("limite") == 50 and "idPedido" not in params and "numeroPedidoLoja" not in params:
                if pid and pid != str(id_bling_pedido):
                    continue
            candidatos.append(item)
        if candidatos:
            break
    return candidatos


def _resolver_id_bling_pedido(cur, ped: dict) -> tuple[int, str] | None:
    """Retorna (id_tenant_bling, id_bling_pedido) do vendedor importado ou fornecedor exportado."""
    origem = (ped.get("origem") or "").strip().lower()
    id_bling = str(ped.get("id_bling_pedido") or "").strip()
    if origem == "bling" and id_bling:
        return int(ped["id_tenant_vendedor"]), id_bling

    # Pedido exportado pelo fornecedor → mapa
    id_forn = int(ped["id_tenant_fornecedor"])
    cur.execute(
        """
        SELECT id_bling FROM tbl_integracao_map
        WHERE id_tenant = %s AND provedor = 'bling' AND contexto = 'fornecedor'
          AND entidade = 'pedido' AND id_dropnexo = %s
        LIMIT 1
        """,
        (id_forn, int(ped["id"])),
    )
    row = cur.fetchone()
    if row and row[0]:
        return id_forn, str(row[0])
    return None


def baixar_danfe_bling(
    cur,
    id_tenant_sessao: int,
    id_pedido: int,
    pasta_destino,
    *,
    id_usuario: int | None = None,
) -> dict[str, Any]:
    """Baixa somente DANFE em PDF e anexa como tipo nf (no tenant vendedor)."""
    ped = obter_pedido(cur, int(id_pedido))
    if not ped:
        raise ValueError("Pedido não encontrado.")

    id_v = int(ped["id_tenant_vendedor"])
    id_f = int(ped["id_tenant_fornecedor"])
    if int(id_tenant_sessao) not in (id_v, id_f):
        raise ValueError("Pedido não pertence a este tenant.")

    existentes = listar_anexos_pedido(cur, int(id_pedido), id_vendedor=id_v)
    for a in existentes:
        if a.get("tipo") == "nf" and str(a.get("nome_original") or "").startswith("danfe_bling_"):
            return {
                "message": "DANFE Bling já anexada.",
                "anexo": a,
                "ja_existia": True,
                "tipo": "nf",
            }

    resolvido = _resolver_id_bling_pedido(cur, ped)
    if not resolvido:
        raise ValueError("Pedido sem vínculo Bling para buscar a nota.")
    id_tenant_bling, id_bling_ped = resolvido

    notas = _listar_nfe_por_pedido_venda(id_tenant_bling, id_bling_ped)
    if not notas:
        raise ValueError("Nenhuma NF-e encontrada no Bling para este pedido.")

    bearer = None
    try:
        bearer = obter_access_token_valido(id_tenant_bling)
    except Exception:
        bearer = None

    content: bytes | None = None
    id_nfe = None
    last_err = "DANFE PDF indisponível no Bling."

    for resumo in notas:
        nid = resumo.get("id")
        if not nid:
            continue
        id_nfe = nid
        try:
            det = api_request(id_tenant_bling, "GET", f"/nfe/{nid}")
        except Exception as e:
            last_err = str(e)[:200]
            continue
        nfe = det.get("data") if isinstance(det.get("data"), dict) else det
        if not isinstance(nfe, dict):
            continue
        for url in _extrair_links_danfe(nfe):
            content = _baixar_url_pdf(url, bearer=bearer) or _baixar_url_pdf(url)
            if content:
                break
        if content:
            break

    if not content or not _parece_pdf(content):
        raise ValueError(last_err)

    pasta = Path(pasta_destino)
    pasta.mkdir(parents=True, exist_ok=True)
    ts = int(datetime.now(timezone.utc).timestamp())
    nome_arquivo = f"danfe_bling_{id_nfe or id_bling_ped}.pdf"
    destino = pasta / f"{id_pedido}_nf_{ts}.pdf"
    destino.write_bytes(content)
    caminho_db = f"upload/tenant{id_v}/pedidos/{destino.name}"
    try:
        parts = destino.parts
        if "upload" in parts:
            idx = parts.index("upload")
            caminho_db = "/".join(parts[idx:])
    except Exception:
        pass

    anexo = registrar_anexo_pedido(
        cur,
        id_v,
        int(id_pedido),
        "nf",
        nome_arquivo,
        caminho_db,
        len(content),
        id_usuario=id_usuario,
    )
    return {
        "message": "DANFE Bling baixada.",
        "anexo": anexo,
        "tipo": "nf",
        "ja_existia": False,
        "id_nfe": id_nfe,
    }


def puxar_documentos_integracao_bling(
    cur,
    id_tenant: int,
    id_pedido: int,
    pasta_destino,
    *,
    id_usuario: int | None = None,
) -> dict[str, Any]:
    """Puxa DANFE PDF do Bling (sem XML)."""
    out: dict[str, Any] = {"origem": "bling", "etiqueta": None, "fiscal": None, "avisos": []}
    try:
        out["fiscal"] = baixar_danfe_bling(
            cur, id_tenant, id_pedido, pasta_destino, id_usuario=id_usuario
        )
    except ValueError as e:
        out["avisos"].append(str(e))

    if not out["fiscal"]:
        raise ValueError(out["avisos"][0] if out["avisos"] else "Nada disponível no Bling.")

    out["message"] = out["fiscal"].get("message") or "DANFE ok."
    out["ok"] = True
    return out
