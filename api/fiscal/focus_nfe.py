# Cliente do hub H74. Se HUB_NFE_URL estiver vazio, continua na Focus.
# O JSON e os caminhos /v2/empresas e /v2/nfe são os mesmos nos dois.
from __future__ import annotations

import os
from typing import Any

import requests


class FocusNfeError(Exception):
    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.status = status


def _hub() -> str:
    return (os.getenv("HUB_NFE_URL") or "").strip().rstrip("/")


def token_configurado(ambiente: str) -> bool:
    return bool(_token(ambiente))


def _token(ambiente: str) -> str:
    if _hub():
        return (os.getenv("HUB_NFE_TOKEN") or "").strip()
    if (ambiente or "").strip().lower() == "producao":
        return (os.getenv("FOCUS_NFE_TOKEN") or "").strip()
    return (os.getenv("FOCUS_NFE_TOKEN_HOMOLOGACAO") or os.getenv("FOCUS_NFE_TOKEN") or "").strip()


def _base(ambiente: str) -> str:
    hub = _hub()
    if hub:
        return hub
    if (ambiente or "").strip().lower() == "producao":
        return "https://api.focusnfe.com.br"
    return "https://homologacao.focusnfe.com.br"


def _cabecalhos(ambiente: str) -> dict:
    cab = {"Accept": "application/json"}
    if not _hub():
        return cab
    amb = "producao" if (ambiente or "").strip().lower() == "producao" else "homologacao"
    cab["X-Ambiente"] = amb
    cab["X-Sistema"] = "dropnexo"
    return cab


def _mensagem(resp: requests.Response) -> str:
    try:
        body = resp.json()
    except Exception:
        body = None
    if isinstance(body, dict):
        partes = [str(body.get("mensagem") or body.get("message") or "").strip()]
        erros = body.get("erros")
        if isinstance(erros, list):
            for item in erros:
                if isinstance(item, dict):
                    campo = (item.get("campo") or "").strip()
                    msg = (item.get("mensagem") or "").strip()
                    partes.append(f"{campo}: {msg}".strip(": "))
                elif item:
                    partes.append(str(item))
        texto = " ".join(p for p in partes if p)
        if texto:
            return texto[:800]
    texto = (resp.text or "").strip()
    return texto[:400] or f"Focus NFe respondeu {resp.status_code}."


def request_json(
    ambiente: str,
    method: str,
    path: str,
    *,
    params: dict | None = None,
    json_body: dict | None = None,
    timeout: int = 60,
) -> tuple[int, Any]:
    token = _token(ambiente)
    if not token:
        if _hub():
            raise FocusNfeError(
                "Falta o token do hub de NF-e no servidor. Defina HUB_NFE_TOKEN."
            )
        raise FocusNfeError(
            "A plataforma ainda não tem o token da Focus NFe. "
            "Defina FOCUS_NFE_TOKEN no ambiente do servidor."
        )
    url = _base(ambiente).rstrip("/") + "/" + path.lstrip("/")
    try:
        resp = requests.request(
            method.upper(),
            url,
            params=params,
            json=json_body,
            auth=(token, ""),
            timeout=timeout,
            headers=_cabecalhos(ambiente),
        )
    except requests.RequestException as e:
        origem = "o hub de NF-e" if _hub() else "a Focus NFe"
        raise FocusNfeError(f"Sem resposta de {origem}: {e}") from e
    if resp.status_code >= 400:
        raise FocusNfeError(_mensagem(resp), resp.status_code)
    if not resp.content:
        return resp.status_code, {}
    try:
        return resp.status_code, resp.json()
    except Exception:
        return resp.status_code, {"raw": (resp.text or "")[:500]}


def baixar(ambiente: str, path: str) -> bytes:
    token = _token(ambiente)
    if not token:
        if _hub():
            raise FocusNfeError("Falta o token do hub de NF-e no servidor. Defina HUB_NFE_TOKEN.")
        raise FocusNfeError("A plataforma ainda não tem o token da Focus NFe.")
    url = _base(ambiente).rstrip("/") + "/" + path.lstrip("/")
    try:
        resp = requests.get(url, auth=(token, ""), timeout=60, headers=_cabecalhos(ambiente))
    except requests.RequestException as e:
        origem = "o hub de NF-e" if _hub() else "a Focus NFe"
        raise FocusNfeError(f"Sem resposta de {origem}: {e}") from e
    if resp.status_code >= 400:
        raise FocusNfeError(_mensagem(resp), resp.status_code)
    return resp.content or b""
