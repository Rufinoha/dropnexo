# api/bling/homologacao.py — fluxo de homologação Bling API v3 (produtos)
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

import requests

BLING_HOMOLOG_BASE = "https://api.bling.com.br/Api/v3/homologacao/produtos"
HEADER_HOMOLOG = "x-bling-homologacao"
# Doc Bling: "O limite entre cada requisição é de 2 segundos" — enviar a próxima
# requisição DENTRO dessa janela (não aguardar 2 s fixos).
JANELA_MAX_SEG = 2.0


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
                        partes.append(f"{f.get('element') or '?'}: {f.get('msg', f)}")
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
    return any(
        isinstance(f, dict) and "tempo limite" in str(f.get("msg", "")).lower()
        for f in fields
    )


def _extrair_hash_resposta(r: requests.Response, body: Any = None) -> str | None:
    """Hash devolvido pelo Bling para usar no passo seguinte."""
    for key, value in r.headers.items():
        if key.lower() == HEADER_HOMOLOG.lower() and value:
            return str(value).strip()

    if isinstance(body, dict):
        for chave in (HEADER_HOMOLOG, "homologacao", "hash"):
            val = body.get(chave)
            if val:
                return str(val).strip()
        meta = body.get("meta")
        if isinstance(meta, dict):
            for chave in (HEADER_HOMOLOG, "homologacao", "hash"):
                val = meta.get(chave)
                if val:
                    return str(val).strip()
    return None


def _headers_debug(r: requests.Response) -> str:
    pares = [f"{k}={v[:24]}..." if len(v) > 24 else f"{k}={v}" for k, v in r.headers.items()]
    return "; ".join(pares[:12])


def _payload_homolog(dados: dict) -> dict[str, Any]:
    payload = {k: v for k, v in dados.items() if k != "id"}
    preco = payload.get("preco")
    if preco is not None:
        payload["preco"] = float(preco)
    return payload


def _request_homolog(
    *,
    metodo: str,
    url: str,
    access_token: str,
    homolog_hash: str | None,
    json_body: dict | None,
    refresh_token_fn: Callable[[], str] | None,
    token_holder: dict[str, str],
) -> tuple[requests.Response, float]:
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
        timeout=10,
    )

    if r.status_code == 401 and refresh_token_fn:
        token_holder["access_token"] = refresh_token_fn()
        headers["Authorization"] = f"Bearer {token_holder['access_token']}"
        r = requests.request(
            metodo.upper(),
            url,
            headers=headers,
            json=json_body,
            timeout=10,
        )

    return r, time.perf_counter()


def executar_homologacao(
    access_token: str,
    *,
    refresh_token_fn: Callable[[], str] | None = None,
    janela_max_seg: float = JANELA_MAX_SEG,
    verbose: bool = False,
) -> ResultadoHomologacao:
    """
    Executa os 5 passos da aba Homologação → Execução (developer.bling.com.br/homologacao).

    Regras (doc oficial):
    - Cada resposta traz header x-bling-homologacao → enviar no passo seguinte.
    - Próxima requisição dentro de 2 s após a resposta anterior.
    - Teste completo em no máximo 10 s.
    - Body POST/PUT: conteúdo plano de `data` do GET (sem wrapper).
    """
    inicio = time.perf_counter()
    passos: list[PassoHomologacao] = []
    homolog_hash: str | None = None
    momento_resposta: float | None = None
    token_holder = {"access_token": access_token}

    def registrar(
        ordem: int,
        metodo: str,
        url: str,
        r: requests.Response,
        ok: bool,
        resumo: str,
        detalhe: str = "",
    ) -> None:
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

    def passo(
        ordem: int,
        metodo: str,
        url: str,
        json_body: dict | None = None,
        *,
        exige_hash_entrada: bool = True,
    ) -> tuple[requests.Response, dict]:
        nonlocal homolog_hash, momento_resposta

        elapsed_antes = None
        if momento_resposta is not None:
            elapsed_antes = time.perf_counter() - momento_resposta
            if elapsed_antes > janela_max_seg:
                raise RuntimeError(
                    f"Passo {ordem}: janela de {janela_max_seg:.0f}s expirou "
                    f"({elapsed_antes:.2f}s desde a resposta anterior). Execute o script de novo."
                )

        if exige_hash_entrada and ordem > 1 and not homolog_hash:
            raise RuntimeError(f"Passo {ordem}: {HEADER_HOMOLOG} ausente.")

        hash_envio = homolog_hash
        r, recebido_em = _request_homolog(
            metodo=metodo,
            url=url,
            access_token=token_holder["access_token"],
            homolog_hash=hash_envio,
            json_body=json_body,
            refresh_token_fn=refresh_token_fn,
            token_holder=token_holder,
        )
        try:
            body = r.json()
        except Exception:
            body = {}

        novo_hash = _extrair_hash_resposta(r, body)
        if r.status_code < 400:
            if novo_hash:
                homolog_hash = novo_hash
            elif ordem == 1:
                raise RuntimeError(f"Passo {ordem}: resposta OK sem {HEADER_HOMOLOG}.")

        momento_resposta = recebido_em

        if verbose and elapsed_antes is not None:
            pass  # registrado no detalhe de cada passo abaixo

        return r, body if isinstance(body, dict) else {}

    try:
        # 1 — GET
        r1, body1 = passo(1, "GET", BLING_HOMOLOG_BASE, exige_hash_entrada=False)
        if r1.status_code >= 400:
            msg = _extrair_erro(body1, r1.text)
            registrar(1, "GET", BLING_HOMOLOG_BASE, r1, False, "Falha ao obter dados", msg)
            return ResultadoHomologacao(False, passos, time.perf_counter() - inicio, f"Passo 1 falhou: {msg}")

        dados = body1.get("data") if isinstance(body1.get("data"), dict) else body1
        if not isinstance(dados, dict) or not dados:
            registrar(1, "GET", BLING_HOMOLOG_BASE, r1, False, "Sem data", str(body1)[:300])
            return ResultadoHomologacao(False, passos, time.perf_counter() - inicio, "Passo 1: JSON sem data.")

        produto = _payload_homolog(dados)
        registrar(
            1,
            "GET",
            BLING_HOMOLOG_BASE,
            r1,
            True,
            "Dados obtidos",
            f"codigo={produto.get('codigo')}",
        )

        # 2 — POST (body plano = conteúdo de data)
        r2, body2 = passo(2, "POST", BLING_HOMOLOG_BASE, produto)
        if r2.status_code >= 400:
            msg = _extrair_erro(body2, r2.text)
            registrar(2, "POST", BLING_HOMOLOG_BASE, r2, False, "Falha ao criar", msg)
            return ResultadoHomologacao(False, passos, time.perf_counter() - inicio, f"Passo 2 falhou: {msg}")

        criado = body2.get("data") if isinstance(body2.get("data"), dict) else {}
        produto_id = criado.get("id")
        if not produto_id:
            registrar(2, "POST", BLING_HOMOLOG_BASE, r2, False, "Sem id", str(body2)[:300])
            return ResultadoHomologacao(False, passos, time.perf_counter() - inicio, "Passo 2: sem id.")

        registrar(
            2,
            "POST",
            BLING_HOMOLOG_BASE,
            r2,
            True,
            "Produto criado",
            f"id={produto_id} hash_resposta={'ok' if _extrair_hash_resposta(r2, body2) else 'ausente'}",
        )

        # 3 — PUT (doc: alterar descricao/nome para "Copo")
        url_put = f"{BLING_HOMOLOG_BASE}/{produto_id}"
        payload_put = {
            "nome": "Copo",
            "preco": produto.get("preco"),
            "codigo": produto.get("codigo"),
        }
        r3, body3 = passo(3, "PUT", url_put, payload_put)
        if r3.status_code >= 400:
            msg = _extrair_erro(body3, r3.text)
            extra = ""
            if _eh_erro_timing(body3):
                extra = f" | hash_enviado={'sim' if homolog_hash else 'nao'} headers={_headers_debug(r2)}"
            registrar(3, "PUT", url_put, r3, False, "Falha ao atualizar", msg + extra)
            return ResultadoHomologacao(False, passos, time.perf_counter() - inicio, f"Passo 3 falhou: {msg}")

        registrar(3, "PUT", url_put, r3, True, "Produto atualizado (nome=Copo)")

        # 4 — PATCH situação
        url_patch = f"{BLING_HOMOLOG_BASE}/{produto_id}/situacoes"
        r4, body4 = passo(4, "PATCH", url_patch, {"situacao": "I"})
        if r4.status_code >= 400:
            msg = _extrair_erro(body4, r4.text)
            registrar(4, "PATCH", url_patch, r4, False, "Falha situação", msg)
            return ResultadoHomologacao(False, passos, time.perf_counter() - inicio, f"Passo 4 falhou: {msg}")

        registrar(4, "PATCH", url_patch, r4, True, "Situação I")

        # 5 — DELETE
        url_del = f"{BLING_HOMOLOG_BASE}/{produto_id}"
        r5, body5 = passo(5, "DELETE", url_del)
        if r5.status_code >= 400:
            msg = _extrair_erro(body5, r5.text)
            registrar(5, "DELETE", url_del, r5, False, "Falha ao excluir", msg)
            return ResultadoHomologacao(False, passos, time.perf_counter() - inicio, f"Passo 5 falhou: {msg}")

        registrar(5, "DELETE", url_del, r5, True, "Produto excluído")

        duracao = time.perf_counter() - inicio
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
            time.perf_counter() - inicio,
            str(e),
        )
    except requests.RequestException as e:
        return ResultadoHomologacao(
            False,
            passos,
            time.perf_counter() - inicio,
            f"Erro de rede: {e}",
        )
