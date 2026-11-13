"""Cliente HTTP para a API do parceiro (pull)."""
from __future__ import annotations

from typing import Any

import requests

from api.api_externa import servico


class ApiExternaErro(RuntimeError):
    def __init__(self, message: str, *, http_status: int | None = None, body: Any = None):
        super().__init__(message)
        self.http_status = http_status
        self.body = body


def _headers(conn, id_tenant: int) -> dict[str, str]:
    cfg = servico.carregar(conn, id_tenant)
    token = servico.token_parceiro_plain(conn, id_tenant)
    h = {"Accept": "application/json", "User-Agent": "DropNexo-ApiExterna/1.0"}
    if not token:
        return h
    if (cfg.get("auth_tipo") or "bearer") == "api_key":
        h["X-Api-Key"] = token
    else:
        h["Authorization"] = f"Bearer {token}"
    return h


def _base(conn, id_tenant: int) -> str:
    cfg = servico.carregar(conn, id_tenant)
    url = (cfg.get("base_url") or "").strip().rstrip("/")
    if not url:
        raise ApiExternaErro("Informe a URL base da API do parceiro.")
    return url


def _get(conn, id_tenant: int, path: str, params: dict | None = None) -> Any:
    url = _base(conn, id_tenant) + path
    try:
        r = requests.get(url, headers=_headers(conn, id_tenant), params=params or {}, timeout=40)
    except requests.RequestException as exc:
        raise ApiExternaErro(f"Falha de conexão: {exc}") from exc
    if r.status_code >= 400:
        raise ApiExternaErro(
            f"HTTP {r.status_code} em {path}",
            http_status=r.status_code,
            body=(r.text or "")[:500],
        )
    if not r.content:
        return {}
    try:
        return r.json()
    except Exception as exc:
        raise ApiExternaErro("Resposta não é JSON válido.", http_status=r.status_code) from exc


def testar_conexao(conn, id_tenant: int) -> dict:
    """Tenta /v1/warehouses e, se falhar, /v1/products?limit=1."""
    erros = []
    for path, params in (("/v1/warehouses", None), ("/v1/products", {"limit": 1})):
        try:
            body = _get(conn, id_tenant, path, params)
            return {
                "ok": True,
                "message": f"Conexão OK ({path}).",
                "endpoint": path,
                "amostra": body if isinstance(body, dict) else {"data": body},
            }
        except ApiExternaErro as exc:
            erros.append(f"{path}: {exc}")
    return {
        "ok": False,
        "message": "Não foi possível validar a API. " + " | ".join(erros[:2]),
    }


def _amostra_lista(body: Any) -> list:
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        for key in ("data", "products", "stock", "itens", "warehouses"):
            v = body.get(key)
            if isinstance(v, list):
                return v
    return []


def checklist_homologacao(conn, id_tenant: int) -> dict:
    """Roda sinais mínimos: warehouses, products e stock. Usado na solicitação de produção."""
    checks = []

    def _check(nome: str, path: str, params: dict | None = None, *, exigir_sku: bool = False):
        try:
            body = _get(conn, id_tenant, path, params)
            itens = _amostra_lista(body)
            ok = True
            detalhe = f"{len(itens)} item(ns)"
            if exigir_sku:
                com_sku = [i for i in itens if isinstance(i, dict) and (i.get("sku") or "").strip()]
                if not com_sku:
                    ok = False
                    detalhe = "resposta sem SKU"
                else:
                    detalhe = f"{len(com_sku)} SKU(s)"
            checks.append(
                {
                    "nome": nome,
                    "endpoint": path,
                    "ok": ok,
                    "detalhe": detalhe,
                    "http_status": 200,
                }
            )
        except ApiExternaErro as exc:
            checks.append(
                {
                    "nome": nome,
                    "endpoint": path,
                    "ok": False,
                    "detalhe": str(exc),
                    "http_status": exc.http_status,
                }
            )

    _check("Depósitos", "/v1/warehouses")
    _check("Produtos", "/v1/products", {"limit": 5}, exigir_sku=True)

    # Estoque: aceita /v1/stock ou fallback via produtos (mesmo comportamento do sync).
    try:
        body = listar_estoque(conn, id_tenant)
        itens = body.get("data") or []
        com_sku = [i for i in itens if isinstance(i, dict) and (i.get("sku") or "").strip()]
        checks.append(
            {
                "nome": "Estoque",
                "endpoint": "/v1/stock",
                "ok": bool(com_sku),
                "detalhe": f"{len(com_sku)} SKU(s)" if com_sku else "sem SKU/estoque",
                "http_status": 200,
            }
        )
    except ApiExternaErro as exc:
        checks.append(
            {
                "nome": "Estoque",
                "endpoint": "/v1/stock",
                "ok": False,
                "detalhe": str(exc),
                "http_status": exc.http_status,
            }
        )

    ok = all(c["ok"] for c in checks)
    return {
        "ok": ok,
        "checks": checks,
        "message": "Checklist OK — pronto para solicitar produção." if ok else "Checklist com falhas — corrija e teste de novo.",
    }


def listar_produtos(conn, id_tenant: int, *, cursor: str | None = None, updated_since: str | None = None) -> dict:
    params: dict[str, Any] = {"limit": 100}
    if cursor:
        params["cursor"] = cursor
    if updated_since:
        params["updated_since"] = updated_since
    body = _get(conn, id_tenant, "/v1/products", params)
    if isinstance(body, list):
        return {"data": body, "next_cursor": None}
    if not isinstance(body, dict):
        return {"data": [], "next_cursor": None}
    data = body.get("data") or body.get("products") or body.get("itens") or []
    if not isinstance(data, list):
        data = []
    return {
        "data": data,
        "next_cursor": body.get("next_cursor") or body.get("cursor") or None,
    }


def listar_estoque(conn, id_tenant: int, *, cursor: str | None = None, updated_since: str | None = None) -> dict:
    params: dict[str, Any] = {"limit": 200}
    if cursor:
        params["cursor"] = cursor
    if updated_since:
        params["updated_since"] = updated_since
    try:
        body = _get(conn, id_tenant, "/v1/stock", params)
    except ApiExternaErro:
        # Fallback: alguns parceiros só expõem estoque dentro de /v1/products
        body = listar_produtos(conn, id_tenant, cursor=cursor, updated_since=updated_since)
        itens = []
        for p in body.get("data") or []:
            if not isinstance(p, dict):
                continue
            itens.append(
                {
                    "sku": p.get("sku"),
                    "quantidade": p.get("quantidade"),
                    "warehouses": p.get("warehouses") or [],
                    "updated_at": p.get("updated_at"),
                }
            )
        return {"data": itens, "next_cursor": body.get("next_cursor")}
    if isinstance(body, list):
        return {"data": body, "next_cursor": None}
    if not isinstance(body, dict):
        return {"data": [], "next_cursor": None}
    data = body.get("data") or body.get("stock") or body.get("itens") or []
    if not isinstance(data, list):
        data = []
    return {
        "data": data,
        "next_cursor": body.get("next_cursor") or body.get("cursor") or None,
    }
