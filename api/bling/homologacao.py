# api/bling/homologacao.py — fluxo de homologação Bling API v3 (produtos)
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

import requests

BLING_HOMOLOG_BASE = "https://api.bling.com.br/Api/v3/homologacao/produtos"
HEADER_HOMOLOG = "x-bling-homologacao"
# Bling exige no mínimo 2 s entre requisições; margem evita falha por arredondamento do relógio.
INTERVALO_MIN_SEG = 2.05


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
            fields = err.get("fields")
            if isinstance(fields, list) and fields:
                for f in fields:
                    if isinstance(f, dict):
                        partes.append(f"{f.get('element', '?')}: {f.get('msg', f)}")
            if partes:
                return " — ".join(partes)
        if body.get("message"):
            return str(body["message"])
    return texto[:500] if texto else "Erro desconhecido"


def _eh_erro_timing(body: Any) -> bool:
    if not isinstance(body, dict):
        return False
    err = body.get("error")
    if not isinstance(err, dict):
        return False
    fields = err.get("fields")
    if not isinstance(fields, list):
        return False
    for f in fields:
        if isinstance(f, dict) and "tempo limite" in str(f.get("msg", "")).lower():
            return True
    return False


def _header_homolog(r: requests.Response) -> str | None:
    for key, value in r.headers.items():
        if key.lower() == HEADER_HOMOLOG.lower():
            return value
    return None


def _payload_homolog(dados: dict) -> dict[str, Any]:
    """Body do POST/PUT: conteúdo de `data` do GET (sem wrapper), conforme doc Bling."""
    payload = {k: v for k, v in dados.items() if k not in ("id",)}
    preco = payload.get("preco")
    if preco is not None:
        payload["preco"] = float(preco)
    return payload


def _aguardar_intervalo(desde: float | None, intervalo_min: float) -> None:
    """Aguarda até completar o intervalo mínimo desde a resposta HTTP anterior."""
    if desde is None or intervalo_min <= 0:
        return
    falta = intervalo_min - (time.monotonic() - desde)
    if falta > 0:
        time.sleep(falta)


def _request_homolog(
    *,
    metodo: str,
    url: str,
    access_token: str,
    homolog_hash: str | None,
    json_body: dict | None,
    refresh_token_fn: Callable[[], str] | None,
    token_holder: dict[str, str],
) -> tuple[requests.Response, str | None, float]:
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

    recebido_em = time.monotonic()
    novo_hash = _header_homolog(r)
    return r, novo_hash, recebido_em


def _atualizar_hash(atual: str | None, novo: str | None) -> str | None:
    """Mantém o hash anterior se a resposta não trouxer um novo."""
    return novo if novo else atual


def executar_homologacao(
    access_token: str,
    *,
    refresh_token_fn: Callable[[], str] | None = None,
    intervalo_min_seg: float = INTERVALO_MIN_SEG,
) -> ResultadoHomologacao:
    """
    Executa os 5 passos exigidos pelo Bling na aba Homologação → Execução.

    Cada resposta devolve o header x-bling-homologacao, repassado na requisição seguinte.
    Entre cada passo aguarda no mínimo 2 s desde a resposta anterior (regra Bling).
    """
    inicio = time.monotonic()
    passos: list[PassoHomologacao] = []
    homolog_hash: str | None = None
    ultima_resposta_em: float | None = None
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

    def chamar(
        ordem: int,
        metodo: str,
        url: str,
        json_body: dict | None = None,
        *,
        retentar_timing: bool = True,
    ) -> tuple[requests.Response, str | None, float, dict]:
        nonlocal homolog_hash, ultima_resposta_em
        _aguardar_intervalo(ultima_resposta_em, intervalo_min_seg)

        if ordem > 1 and not homolog_hash:
            raise RuntimeError(f"Passo {ordem}: header {HEADER_HOMOLOG} ausente antes da requisição.")

        for tentativa in (1, 2):
            hash_envio = homolog_hash
            r, novo_hash, recebido_em = _request_homolog(
                metodo=metodo,
                url=url,
                access_token=token_holder["access_token"],
                homolog_hash=hash_envio,
                json_body=json_body,
                refresh_token_fn=refresh_token_fn,
                token_holder=token_holder,
            )
            homolog_hash = _atualizar_hash(hash_envio, novo_hash)
            try:
                body = r.json()
            except Exception:
                body = {}

            if r.status_code < 400 or not (retentar_timing and tentativa == 1 and _eh_erro_timing(body)):
                ultima_resposta_em = recebido_em
                return r, homolog_hash, recebido_em, body

            _aguardar_intervalo(recebido_em, intervalo_min_seg)

        ultima_resposta_em = recebido_em
        return r, homolog_hash, recebido_em, body

    try:
        # 1 — GET dados
        r1, homolog_hash, _, body1 = chamar(1, "GET", BLING_HOMOLOG_BASE, retentar_timing=False)
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

        if not homolog_hash:
            registrar(
                1,
                "GET",
                BLING_HOMOLOG_BASE,
                r1,
                False,
                "Header de homologação ausente",
                f"Resposta GET sem {HEADER_HOMOLOG}",
            )
            return ResultadoHomologacao(
                False,
                passos,
                time.monotonic() - inicio,
                f"Passo 1: resposta sem header {HEADER_HOMOLOG}.",
            )

        produto = _payload_homolog(dados)
        registrar(
            1,
            "GET",
            BLING_HOMOLOG_BASE,
            r1,
            True,
            "Dados obtidos",
            f"codigo={produto.get('codigo')} hash={homolog_hash[:12]}...",
        )

        # 2 — POST criar produto
        r2, homolog_hash, _, body2 = chamar(2, "POST", BLING_HOMOLOG_BASE, produto)
        if r2.status_code >= 400:
            msg = _extrair_erro(body2, r2.text)
            detalhe = f"{msg} | body={str(body2)[:400]}" if body2 else msg
            registrar(2, "POST", BLING_HOMOLOG_BASE, r2, False, "Falha ao criar produto", detalhe)
            return ResultadoHomologacao(False, passos, time.monotonic() - inicio, f"Passo 2 falhou: {msg}")

        criado = body2.get("data") if isinstance(body2.get("data"), dict) else {}
        produto_id = criado.get("id")
        if not produto_id:
            registrar(2, "POST", BLING_HOMOLOG_BASE, r2, False, "Resposta sem id", str(body2)[:300])
            return ResultadoHomologacao(False, passos, time.monotonic() - inicio, "Passo 2: produto criado sem id.")

        registrar(2, "POST", BLING_HOMOLOG_BASE, r2, True, "Produto criado", f"id={produto_id}")

        # 3 — PUT alterar nome para "Copo"
        url_put = f"{BLING_HOMOLOG_BASE}/{produto_id}"
        payload_put = {**produto, "nome": "Copo"}
        if "descricao" in produto:
            payload_put["descricao"] = "Copo"
        r3, homolog_hash, _, body3 = chamar(3, "PUT", url_put, payload_put)
        if r3.status_code >= 400:
            msg = _extrair_erro(body3, r3.text)
            registrar(3, "PUT", url_put, r3, False, "Falha ao atualizar produto", msg)
            return ResultadoHomologacao(False, passos, time.monotonic() - inicio, f"Passo 3 falhou: {msg}")

        registrar(3, "PUT", url_put, r3, True, "Produto atualizado (nome=Copo)")

        # 4 — PATCH situação inativa
        url_patch = f"{BLING_HOMOLOG_BASE}/{produto_id}/situacoes"
        r4, homolog_hash, _, body4 = chamar(4, "PATCH", url_patch, {"situacao": "I"})
        if r4.status_code >= 400:
            msg = _extrair_erro(body4, r4.text)
            registrar(4, "PATCH", url_patch, r4, False, "Falha ao alterar situação", msg)
            return ResultadoHomologacao(False, passos, time.monotonic() - inicio, f"Passo 4 falhou: {msg}")

        registrar(4, "PATCH", url_patch, r4, True, "Situação alterada (I)")

        # 5 — DELETE
        url_del = f"{BLING_HOMOLOG_BASE}/{produto_id}"
        r5, _, _, body5 = chamar(5, "DELETE", url_del)
        if r5.status_code >= 400:
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

    except RuntimeError as e:
        return ResultadoHomologacao(
            False,
            passos,
            time.monotonic() - inicio,
            str(e),
        )
    except requests.RequestException as e:
        return ResultadoHomologacao(
            False,
            passos,
            time.monotonic() - inicio,
            f"Erro de rede: {e}",
        )
