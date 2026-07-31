# api/hubsupport/hubsupport_client.py — cliente HTTP HubSupport (server-to-server)
from __future__ import annotations

import logging
import os
import time
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://hubsupport.com.br/api/v1/integration"
MAX_RETRIES = 3
RETRY_STATUS = {429, 500, 502, 503, 504}


class HubSupportError(Exception):
    def __init__(self, message: str, status_code: int | None = None, payload: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class HubSupportClient:
    def __init__(self, token: str | None = None, base_url: str | None = None, conn=None):
        if conn is not None and (token is None or base_url is None):
            from api.hubsupport.hubsupport_config import obter_credenciais

            cred = obter_credenciais(conn)
            token = token if token is not None else cred.get("api_token")
            base_url = base_url if base_url is not None else cred.get("base_url")
        elif token is None or base_url is None:
            from api.hubsupport.hubsupport_config import obter_credenciais

            cred = obter_credenciais()
            token = token if token is not None else cred.get("api_token")
            base_url = base_url if base_url is not None else cred.get("base_url")

        self.token = (token or os.getenv("HUBSUPPORT_API_TOKEN") or "").strip()
        env_base = (
            os.getenv("HUBSUPPORT_API_BASE")
            or os.getenv("HUBSUPPORT_BASE_URL")
            or DEFAULT_BASE_URL
        )
        self.base_url = (base_url or env_base).rstrip("/")

    def configurado(self) -> bool:
        return bool(self.token)

    def _headers(self, idempotency_key: str | None = None) -> dict:
        h = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
        }
        if idempotency_key:
            h["Idempotency-Key"] = idempotency_key
        return h

    def _parse_response(self, resp: requests.Response) -> Any:
        try:
            data = resp.json()
        except ValueError:
            data = {"raw": resp.text}

        if resp.status_code >= 400:
            msg = ""
            if isinstance(data, dict):
                msg = str(data.get("message") or data.get("erro") or data.get("error") or "")
                if not msg and isinstance(data.get("detail"), str):
                    msg = data["detail"]
            if not msg:
                msg = f"Erro HTTP {resp.status_code} na API HubSupport."
            logger.warning("HubSupport HTTP %s: %s", resp.status_code, msg)
            raise HubSupportError(msg, status_code=resp.status_code, payload=data)

        if isinstance(data, dict) and data.get("success") is False:
            msg = str(data.get("message") or "Operação recusada pelo HubSupport.")
            raise HubSupportError(msg, status_code=resp.status_code, payload=data)

        return data

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict | None = None,
        params: dict | None = None,
        idempotency_key: str | None = None,
        timeout: int = 30,
        max_retries: int | None = None,
    ) -> Any:
        if not self.configurado():
            raise HubSupportError(
                "Integração HubSupport não configurada. "
                "Informe a chave em Configurações → HubSupport."
            )

        url = f"{self.base_url}/{path.lstrip('/')}"
        last_exc: Exception | None = None
        tentativas = MAX_RETRIES if max_retries is None else max(1, int(max_retries))

        for attempt in range(tentativas):
            try:
                resp = requests.request(
                    method.upper(),
                    url,
                    json=json_body,
                    params=params,
                    headers=self._headers(idempotency_key),
                    timeout=timeout,
                )
                if resp.status_code in RETRY_STATUS and attempt < tentativas - 1:
                    time.sleep(0.6 * (attempt + 1))
                    continue
                return self._parse_response(resp)
            except HubSupportError as e:
                if e.status_code in RETRY_STATUS and attempt < tentativas - 1:
                    last_exc = e
                    time.sleep(0.6 * (attempt + 1))
                    continue
                raise
            except requests.RequestException as e:
                last_exc = e
                if attempt < tentativas - 1:
                    time.sleep(0.6 * (attempt + 1))
                    continue
                raise HubSupportError(f"Falha de rede com HubSupport: {e}") from e

        if last_exc:
            raise last_exc
        raise HubSupportError("Falha desconhecida ao chamar HubSupport.")

    def upsert_cliente(self, payload: dict) -> Any:
        return self.request("PUT", "clientes", json_body=payload)

    def upsert_usuario(self, payload: dict) -> Any:
        return self.request("PUT", "usuarios", json_body=payload)

    def criar_chamado(self, payload: dict, *, idempotency_key: str) -> Any:
        return self.request("POST", "chamados", json_body=payload, idempotency_key=idempotency_key)

    def listar_chamados(self, usuario_external_id: str, *, page: int = 1, per_page: int = 20) -> Any:
        return self.request(
            "GET",
            "chamados",
            params={
                "usuario_external_id": usuario_external_id,
                "page": page,
                "per_page": per_page,
            },
        )

    def detalhar_chamado(self, chamado_external_id: str) -> Any:
        from urllib.parse import quote

        ref = quote(chamado_external_id, safe="")
        return self.request("GET", f"chamados/{ref}", timeout=20, max_retries=2)

    def criar_interacao(self, chamado_external_id: str, corpo: str) -> Any:
        from urllib.parse import quote

        ref = quote(chamado_external_id, safe="")
        return self.request(
            "POST",
            f"chamados/{ref}/interacoes",
            json_body={"corpo": corpo},
        )

    def enviar_anexo(
        self,
        chamado_external_id: str,
        nome_arquivo: str,
        conteudo: bytes,
        content_type: str | None = None,
    ) -> Any:
        if not self.configurado():
            raise HubSupportError("Integração HubSupport não configurada.")

        from urllib.parse import quote

        ref = quote(chamado_external_id, safe="")
        url = f"{self.base_url}/chamados/{ref}/anexos"
        ct = content_type or "application/octet-stream"
        nome = (nome_arquivo or "anexo").strip() or "anexo"

        try:
            resp = requests.post(
                url,
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {self.token}",
                },
                files={"arquivo": (nome, conteudo, ct)},
                timeout=60,
            )
            return self._parse_response(resp)
        except requests.RequestException as e:
            raise HubSupportError(f"Falha ao enviar anexo: {e}") from e
