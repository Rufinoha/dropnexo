# Cliente HTTP da Focus NFe. O token é da plataforma; cada tenant envia o próprio certificado.
from __future__ import annotations

import os
from typing import Any

import requests


class FocusNfeError(Exception):
    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.status = status


def token_configurado(ambiente: str) -> bool:
    return bool(_token(ambiente))


def _token(ambiente: str) -> str:
    if (ambiente or "").strip().lower() == "producao":
        return (os.getenv("FOCUS_NFE_TOKEN") or "").strip()
    return (os.getenv("FOCUS_NFE_TOKEN_HOMOLOGACAO") or os.getenv("FOCUS_NFE_TOKEN") or "").strip()


def _base(ambiente: str) -> str:
    if (ambiente or "").strip().lower() == "producao":
        return "https://api.focusnfe.com.br"
    return "https://homologacao.focusnfe.com.br"


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
            headers={"Accept": "application/json"},
        )
    except requests.RequestException as e:
        raise FocusNfeError(f"Sem resposta da Focus NFe: {e}") from e
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
        raise FocusNfeError("A plataforma ainda não tem o token da Focus NFe.")
    url = _base(ambiente).rstrip("/") + "/" + path.lstrip("/")
    try:
        resp = requests.get(url, auth=(token, ""), timeout=60)
    except requests.RequestException as e:
        raise FocusNfeError(f"Sem resposta da Focus NFe: {e}") from e
    if resp.status_code >= 400:
        raise FocusNfeError(_mensagem(resp), resp.status_code)
    return resp.content or b""
