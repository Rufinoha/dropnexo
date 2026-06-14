# api/bling/homologacao.py — fluxo de homologação Bling API v3 (produtos)
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

import requests

BLING_HOMOLOG_BASE = "https://api.bling.com.br/Api/v3/homologacao/produtos"
HEADER_HOMOLOG = "x-bling-homologacao"
INTERVALO_SEG = 2.0


@dataclass
class PassoHomologacao:
    ordem: int
    metodo: str
    url: str
    status: int
    ok: bool
    resumo: str
    detalhe: str = ""


@dataclass
class ResultadoHomologacao:
    sucesso: bool
    passos: list[PassoHomologacao] = field(default_factory=list)
    duracao_seg: float = 0.0
    mensagem: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "sucesso": self.sucesso,
            "duracao_seg": round(self.duracao_seg, 2),
            "mensagem": self.mensagem,
            "passos": [
                {
                    "ordem": p.ordem,
                    "metodo": p.metodo,
                    "url": p.url,
                    "status": p.status,
                    "ok": p.ok,
                    "resumo": p.resumo,
                    "detalhe": p.detalhe,
                }
                for p in self.passos
            ],
        }


def _extrair_erro(body: Any, texto: str) -> str:
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            partes = [str(err[k]) for k in ("message", "description", "type") if err.get(k)]
            if partes:
                return " — ".join(partes)
        if body.get("message"):
            return str(body["message"])
    return texto[:500] if texto else "Erro desconhecido"


def _header_homolog(r: requests.Response) -> str | None:
    for key, value in r.headers.items():
        if key.lower() == HEADER_HOMOLOG.lower():
            return value
    return None


def _campos_produto(dados: dict) -> dict[str, Any]:
    """Campos aceitos na homologação (nome, preco, codigo)."""
    preco = dados.get("preco")
    if preco is not None:
        preco = float(preco)
    return {
        "nome": dados.get("nome"),
        "preco": preco,
        "codigo": dados.get("codigo"),
    }


def _body_api(dados: dict) -> dict[str, Any]:
    """API v3 do Bling espera payload dentro de `data`."""
    return {"data": dados}


def _request_homolog(
    *,
    metodo: str,
    url: str,
    access_token: str,
    homolog_hash: str | None,
    json_body: dict | None,
    refresh_token_fn: Callable[[], str] | None,
    token_holder: dict[str, str],
) -> tuple[requests.Response, str | None]:
    headers = {
        "Authorization": f"Bearer {token_holder['access_token']}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if homolog_hash:
        headers[HEADER_HOMOLOG] = homolog_hash

    r = requests.request(
        metodo.upper(),
        url,
        headers=headers,
        json=json_body,
        timeout=15,
    )

    if r.status_code == 401 and refresh_token_fn:
        token_holder["access_token"] = refresh_token_fn()
        headers["Authorization"] = f"Bearer {token_holder['access_token']}"
        r = requests.request(
            metodo.upper(),
            url,
            headers=headers,
            json=json_body,
            timeout=15,
        )

    novo_hash = _header_homolog(r)
    return r, novo_hash


def executar_homologacao(
    access_token: str,
    *,
    refresh_token_fn: Callable[[], str] | None = None,
    intervalo_seg: float = INTERVALO_SEG,
) -> ResultadoHomologacao:
    """
    Executa os 5 passos exigidos pelo Bling na aba Homologação → Execução.

    Cada resposta devolve o header x-bling-homologacao, repassado na requisição seguinte.
    """
    inicio = time.monotonic()
    passos: list[PassoHomologacao] = []
    homolog_hash: str | None = None
    token_holder = {"access_token": access_token}
    produto_id: int | str | None = None

    def registrar(ordem: int, metodo: str, url: str, r: requests.Response, ok: bool, resumo: str, detalhe: str = "") -> None:
        passos.append(
            PassoHomologacao(
                ordem=ordem,
                metodo=metodo,
                url=url,
                status=r.status_code,
                ok=ok,
                resumo=resumo,
                detalhe=detalhe,
            )
        )

    def aguardar() -> None:
        if intervalo_seg > 0:
            time.sleep(intervalo_seg)

    try:
        # 1 — GET dados
        r1, homolog_hash = _request_homolog(
            metodo="GET",
            url=BLING_HOMOLOG_BASE,
            access_token=token_holder["access_token"],
            homolog_hash=homolog_hash,
            json_body=None,
            refresh_token_fn=refresh_token_fn,
            token_holder=token_holder,
        )
        try:
            body1 = r1.json()
        except Exception:
            body1 = {}
        if r1.status_code >= 400:
            msg = _extrair_erro(body1, r1.text)
            registrar(1, "GET", BLING_HOMOLOG_BASE, r1, False, "Falha ao obter dados", msg)
            return ResultadoHomologacao(
                False,
                passos,
                time.monotonic() - inicio,
                f"Passo 1 falhou: {msg}",
            )

        dados = body1.get("data") if isinstance(body1.get("data"), dict) else body1
        if not isinstance(dados, dict) or not dados:
            registrar(1, "GET", BLING_HOMOLOG_BASE, r1, False, "Resposta sem data", str(body1)[:300])
            return ResultadoHomologacao(False, passos, time.monotonic() - inicio, "Passo 1: JSON sem campo data.")

        produto = _campos_produto(dados)
        registrar(1, "GET", BLING_HOMOLOG_BASE, r1, True, "Dados obtidos", f"codigo={produto.get('codigo')}")
        aguardar()

        # 2 — POST criar produto
        r2, homolog_hash = _request_homolog(
            metodo="POST",
            url=BLING_HOMOLOG_BASE,
            access_token=token_holder["access_token"],
            homolog_hash=homolog_hash,
            json_body=_body_api(produto),
            refresh_token_fn=refresh_token_fn,
            token_holder=token_holder,
        )
        try:
            body2 = r2.json()
        except Exception:
            body2 = {}
        if r2.status_code >= 400:
            msg = _extrair_erro(body2, r2.text)
            registrar(2, "POST", BLING_HOMOLOG_BASE, r2, False, "Falha ao criar produto", msg)
            return ResultadoHomologacao(False, passos, time.monotonic() - inicio, f"Passo 2 falhou: {msg}")

        criado = body2.get("data") if isinstance(body2.get("data"), dict) else {}
        produto_id = criado.get("id")
        if not produto_id:
            registrar(2, "POST", BLING_HOMOLOG_BASE, r2, False, "Resposta sem id", str(body2)[:300])
            return ResultadoHomologacao(False, passos, time.monotonic() - inicio, "Passo 2: produto criado sem id.")

        registrar(2, "POST", BLING_HOMOLOG_BASE, r2, True, "Produto criado", f"id={produto_id}")
        aguardar()

        # 3 — PUT alterar nome para "Copo"
        url_put = f"{BLING_HOMOLOG_BASE}/{produto_id}"
        payload_put = {**produto, "nome": "Copo"}
        r3, homolog_hash = _request_homolog(
            metodo="PUT",
            url=url_put,
            access_token=token_holder["access_token"],
            homolog_hash=homolog_hash,
            json_body=_body_api(payload_put),
            refresh_token_fn=refresh_token_fn,
            token_holder=token_holder,
        )
        if r3.status_code >= 400:
            try:
                body3 = r3.json()
            except Exception:
                body3 = {}
            msg = _extrair_erro(body3, r3.text)
            registrar(3, "PUT", url_put, r3, False, "Falha ao atualizar produto", msg)
            return ResultadoHomologacao(False, passos, time.monotonic() - inicio, f"Passo 3 falhou: {msg}")

        registrar(3, "PUT", url_put, r3, True, "Produto atualizado (nome=Copo)")
        aguardar()

        # 4 — PATCH situação inativa
        url_patch = f"{BLING_HOMOLOG_BASE}/{produto_id}/situacoes"
        r4, homolog_hash = _request_homolog(
            metodo="PATCH",
            url=url_patch,
            access_token=token_holder["access_token"],
            homolog_hash=homolog_hash,
            json_body=_body_api({"situacao": "I"}),
            refresh_token_fn=refresh_token_fn,
            token_holder=token_holder,
        )
        if r4.status_code >= 400:
            try:
                body4 = r4.json()
            except Exception:
                body4 = {}
            msg = _extrair_erro(body4, r4.text)
            registrar(4, "PATCH", url_patch, r4, False, "Falha ao alterar situação", msg)
            return ResultadoHomologacao(False, passos, time.monotonic() - inicio, f"Passo 4 falhou: {msg}")

        registrar(4, "PATCH", url_patch, r4, True, "Situação alterada (I)")
        aguardar()

        # 5 — DELETE
        url_del = f"{BLING_HOMOLOG_BASE}/{produto_id}"
        r5, _ = _request_homolog(
            metodo="DELETE",
            url=url_del,
            access_token=token_holder["access_token"],
            homolog_hash=homolog_hash,
            json_body=None,
            refresh_token_fn=refresh_token_fn,
            token_holder=token_holder,
        )
        if r5.status_code >= 400:
            try:
                body5 = r5.json()
            except Exception:
                body5 = {}
            msg = _extrair_erro(body5, r5.text)
            registrar(5, "DELETE", url_del, r5, False, "Falha ao excluir produto", msg)
            return ResultadoHomologacao(False, passos, time.monotonic() - inicio, f"Passo 5 falhou: {msg}")

        registrar(5, "DELETE", url_del, r5, True, "Produto excluído")

        duracao = time.monotonic() - inicio
        return ResultadoHomologacao(
            True,
            passos,
            duracao,
            f"Homologação concluída em {duracao:.1f}s. Valide no painel Bling.",
        )

    except requests.RequestException as e:
        return ResultadoHomologacao(
            False,
            passos,
            time.monotonic() - inicio,
            f"Erro de rede: {e}",
        )
