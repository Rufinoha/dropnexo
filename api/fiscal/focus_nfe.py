# Cliente do hub H74 de NF-e modelo 55. Este sistema não fala com a SEFAZ.
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


def token_configurado(ambiente: str = "") -> bool:
    return bool(_hub() and _token())


def _token() -> str:
    return (os.getenv("HUB_NFE_TOKEN") or "").strip()


def _ambiente(ambiente: str) -> str:
    return "producao" if (ambiente or "").strip().lower() == "producao" else "homologacao"


def _exigir_config() -> str:
    if not _hub():
        raise FocusNfeError("Defina HUB_NFE_URL no .env do servidor.")
    if not _token():
        raise FocusNfeError("Defina HUB_NFE_TOKEN no .env do servidor.")
    return _token()


def _cabecalhos(ambiente: str) -> dict:
    return {
        "Accept": "application/json",
        "X-Ambiente": _ambiente(ambiente),
        "X-Sistema": "dropnexo",
    }


def _mensagem(resp: requests.Response) -> str:
    if resp.status_code == 401:
        return (
            "O hub recusou o acesso. Confira o token no .env e se o sistema dropnexo "
            "está ligado nesse token."
        )
    try:
        body = resp.json()
    except Exception:
        body = None
    if isinstance(body, dict):
        partes = [
            str(body.get("mensagem_sefaz") or body.get("mensagem") or body.get("message") or "").strip()
        ]
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
    return texto[:400] or f"O hub de NF-e respondeu {resp.status_code}."


def request_json(
    ambiente: str,
    method: str,
    path: str,
    *,
    params: dict | None = None,
    json_body: dict | None = None,
    timeout: int = 60,
) -> tuple[int, Any]:
    token = _exigir_config()
    url = _hub() + "/" + path.lstrip("/")
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
        raise FocusNfeError(f"Sem resposta do hub de NF-e: {e}") from e
    if resp.status_code >= 400:
        raise FocusNfeError(_mensagem(resp), resp.status_code)
    if not resp.content:
        return resp.status_code, {}
    try:
        return resp.status_code, resp.json()
    except Exception:
        return resp.status_code, {"raw": (resp.text or "")[:500]}


def baixar(ambiente: str, path: str) -> bytes:
    token = _exigir_config()
    url = _hub() + "/" + path.lstrip("/")
    try:
        resp = requests.get(url, auth=(token, ""), timeout=60, headers=_cabecalhos(ambiente))
    except requests.RequestException as e:
        raise FocusNfeError(f"Sem resposta do hub de NF-e: {e}") from e
    if resp.status_code >= 400:
        raise FocusNfeError(_mensagem(resp), resp.status_code)
    return resp.content or b""
