# Cliente do hub H74 (NF-e modelo 55 e NFS-e nacional). Este sistema não fala com a SEFAZ/Sefin.
from __future__ import annotations

from typing import Any

import requests


class FocusNfeError(Exception):
    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.status = status


def _credenciais() -> dict:
    from api.fiscal.hub_nfe_config import obter_credenciais

    return obter_credenciais()


def _hub() -> str:
    return (_credenciais().get("base_url") or "").strip().rstrip("/")


def _token_nfe() -> str:
    return (_credenciais().get("token") or "").strip()


def _token_nfse() -> str:
    return (_credenciais().get("token_nfse") or "").strip()


def _token(escopo: str = "nfe") -> str:
    escopo = (escopo or "nfe").strip().lower()
    if escopo in {"nfse", "nfs-e", "nfs_e"}:
        return _token_nfse()
    return _token_nfe()


def token_configurado(ambiente: str = "", *, escopo: str = "nfe") -> bool:
    return bool(_hub() and _token(escopo))


def _ambiente(ambiente: str) -> str:
    amb = (ambiente or "").strip().lower()
    if not amb:
        amb = (_credenciais().get("ambiente") or "homologacao").strip().lower()
    return "producao" if amb == "producao" else "homologacao"


def _exigir_config(escopo: str = "nfe") -> str:
    if not _hub():
        raise FocusNfeError(
            "Defina a URL do Hub H74 em Configurações → Hub H74 (ou HUB_NFE_URL no .env)."
        )
    token = _token(escopo)
    if not token:
        if (escopo or "").lower() in {"nfse", "nfs-e", "nfs_e"}:
            raise FocusNfeError(
                "Defina o token NFS-e do Hub H74 em Configurações → Hub H74 "
                "(ou HUB_NFSE_TOKEN no .env)."
            )
        raise FocusNfeError(
            "Defina o token NF-e do Hub H74 em Configurações → Hub H74 "
            "(ou HUB_NFE_TOKEN no .env)."
        )
    return token


def _cabecalhos(ambiente: str) -> dict:
    cred = _credenciais()
    return {
        "Accept": "application/json",
        "X-Ambiente": _ambiente(ambiente),
        "X-Sistema": (cred.get("x_sistema") or "dropnexo").strip() or "dropnexo",
    }


def _mensagem(resp: requests.Response) -> str:
    if resp.status_code == 401:
        return (
            "O hub recusou o acesso. Confira o token em Configurações → Hub H74 "
            "(NF-e vs NFS-e), o X-Sistema=dropnexo e o escopo do token."
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
    return texto[:400] or f"O hub respondeu {resp.status_code}."


def request_json(
    ambiente: str,
    method: str,
    path: str,
    *,
    params: dict | None = None,
    json_body: dict | None = None,
    timeout: int = 60,
    escopo: str = "nfe",
) -> tuple[int, Any]:
    token = _exigir_config(escopo)
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
        raise FocusNfeError(f"Sem resposta do hub fiscal: {e}") from e
    if resp.status_code >= 400:
        raise FocusNfeError(_mensagem(resp), resp.status_code)
    if not resp.content:
        return resp.status_code, {}
    try:
        return resp.status_code, resp.json()
    except Exception:
        return resp.status_code, {"raw": (resp.text or "")[:500]}


def baixar(ambiente: str, path: str, *, escopo: str = "nfe") -> bytes:
    token = _exigir_config(escopo)
    url = _hub() + "/" + path.lstrip("/")
    try:
        resp = requests.get(url, auth=(token, ""), timeout=60, headers=_cabecalhos(ambiente))
    except requests.RequestException as e:
        raise FocusNfeError(f"Sem resposta do hub fiscal: {e}") from e
    if resp.status_code >= 400:
        raise FocusNfeError(_mensagem(resp), resp.status_code)
    return resp.content or b""
