# api/bling/homologacao.py — homologação Bling e conteúdo do manual público
from __future__ import annotations

# ── homologacao ───────────────────────────────────────

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


# ── manual_conteudo ───────────────────────────────────

MANUAL_BLING_PASSOS = [
    {
        "img": "image_bling1.jpg",
        "titulo": "Conta, plano e Integrações",
        "texto": (
            "O primeiro passo é ter uma <strong>conta ativa</strong> no DropNexo com um "
            "<strong>plano pago</strong> (Profissional ou superior). "
            "As integrações com ERP <strong>não estão disponíveis</strong> no plano gratuito (Starter). "
            "Se você ainda não tem conta, faça o cadastro como "
            "<a href=\"{url_cadastro_fornecedor}\">fornecedor</a> ou "
            "<a href=\"{url_cadastro_vendedor}\">vendedor</a>, conclua o cadastro e "
            "<strong>contrate um plano</strong> em <strong>Meu plano</strong> (menu do usuário, canto superior). "
            "Com o plano ativo, acesse o <a href=\"{url_login}\">login</a>, entre na sua empresa e, "
            "no menu lateral, abra <strong>Integrações</strong>. "
            "Na categoria <strong>ERP</strong>, clique no card <strong>Bling</strong>."
        ),
    },
    {
        "img": "image_bling2.jpg",
        "titulo": "Inicie a conexão",
        "texto": (
            "Na janela <strong>Conectar Bling</strong>, clique em "
            "<strong>Conectar conta</strong>. Você será redirecionado com segurança ao site do Bling."
        ),
    },
    {
        "img": "image_bling3.jpg",
        "titulo": "Faça login no Bling",
        "texto": (
            "Informe seu <strong>usuário ou e-mail</strong> e <strong>senha</strong> da conta Bling "
            "e clique em <strong>Entrar</strong>. Em seguida, autorize o acesso do DropNexo."
        ),
    },
    {
        "img": "image_bling4.jpg",
        "titulo": "Confirme que está conectado",
        "texto": (
            "De volta ao DropNexo, o card do Bling exibirá o status "
            "<strong>Conectado</strong>. Clique novamente no card para abrir a configuração."
        ),
    },
    {
        "img": "image_bling5.jpg",
        "titulo": "Configure e sincronize",
        "texto": (
            "Revise produtos, estoque e pedidos conforme seu perfil. "
            "Clique em <strong>Salvar</strong> e use <strong>Sincronizar produtos</strong> "
            "para importar ou atualizar o catálogo."
        ),
    },
]

MANUAL_IMAGENS_PERMITIDAS = frozenset(p["img"] for p in MANUAL_BLING_PASSOS)

# Referência da tela "Configuração — Fornecedor" (passo 5)
MANUAL_BLING_CONFIG_FORNECEDOR = [
    {
        "campo": "Modo das imagens",
        "descricao": (
            "Define como as fotos dos produtos vindos do Bling serão armazenadas no DropNexo "
            "durante a sincronização de catálogo."
        ),
        "padrao": "Manter como link",
        "opcoes": [
            {
                "nome": "Manter como link",
                "efeito": (
                    "O DropNexo grava a <strong>URL original</strong> da imagem hospedada no Bling. "
                    "As fotos continuam sendo servidas pelo Bling; a sincronização é mais rápida e ocupa menos espaço no servidor."
                ),
            },
            {
                "nome": "Baixar para o servidor",
                "efeito": (
                    "O DropNexo <strong>baixa cada imagem</strong> para a pasta da sua empresa "
                    "(<code>upload/tenant…/produtos/SKU/</code>). Limite de <strong>3 MB</strong> por arquivo. "
                    "Útil quando você quer independência do link externo ou controle local dos arquivos."
                ),
            },
        ],
    },
    {
        "campo": "Fonte principal",
        "descricao": (
            "Indica qual sistema é considerado a <strong>referência oficial</strong> quando os mesmos dados "
            "existem nos dois lados (Bling e DropNexo) e há divergência."
        ),
        "padrao": "Bling",
        "opcoes": [
            {
                "nome": "Bling",
                "efeito": (
                    "Em conflito de informação, prevalece o que está no <strong>Bling</strong>. "
                    "Recomendado para fornecedor que já opera o catálogo no ERP."
                ),
            },
            {
                "nome": "DropNexo",
                "efeito": (
                    "Em conflito, prevalece o que está no <strong>DropNexo</strong>. "
                    "Use se você mantém o cadastro mestre na plataforma e o Bling é secundário."
                ),
            },
        ],
    },
    {
        "campo": "Produtos",
        "descricao": (
            "Controla o <strong>fluxo de cadastro de produtos</strong> entre Bling e DropNexo. "
            "Afeta o botão <strong>Sincronizar produtos</strong>."
        ),
        "padrao": "Importar",
        "opcoes": [
            {
                "nome": "Importar",
                "efeito": (
                    "Traz produtos do <strong>Bling → DropNexo</strong>. Cria itens novos e atualiza os já mapeados. "
                    "Produtos <strong>sem SKU</strong> no Bling são ignorados."
                ),
            },
            {
                "nome": "Exportar",
                "efeito": (
                    "Envia produtos do <strong>DropNexo → Bling</strong>. "
                    "Nesta opção o botão <strong>Sincronizar produtos</strong> não executa importação "
                    "(modo pensado para quem cadastra no DropNexo e publica no ERP)."
                ),
            },
            {
                "nome": "Atualizar (ambos)",
                "efeito": (
                    "Permite <strong>importar e atualizar</strong> produtos do Bling no DropNexo, "
                    "mantendo o vínculo entre os cadastros. É o modo mais completo para quem edita nos dois lados."
                ),
            },
        ],
    },
    {
        "campo": "Estoque",
        "descricao": (
            "Define a direção da sincronização de <strong>quantidades em estoque</strong> "
            "entre depósitos do Bling e o DropNexo."
        ),
        "padrao": "Atualizar (ambos)",
        "opcoes": [
            {
                "nome": "Importar",
                "efeito": (
                    "O estoque do <strong>Bling alimenta</strong> o DropNexo. "
                    "Alterações feitas só no DropNexo podem ser sobrescritas na próxima sincronização."
                ),
            },
            {
                "nome": "Exportar",
                "efeito": (
                    "O estoque do <strong>DropNexo é enviado</strong> ao Bling. "
                    "Indicado quando o controle de saldo é feito na plataforma."
                ),
            },
            {
                "nome": "Atualizar (ambos)",
                "efeito": (
                    "Sincronização <strong>bidirecional</strong>: mudanças em qualquer lado podem refletir no outro "
                    "(na prática, prevalece a alteração mais recente conforme a regra do conector)."
                ),
            },
        ],
        "nota": (
            "A sincronização automática de estoque está em evolução. "
            "A configuração já fica salva para quando o módulo estiver ativo."
        ),
    },
    {
        "campo": "Pedidos",
        "descricao": (
            "Define como os <strong>pedidos de venda</strong> circulam entre DropNexo e Bling "
            "(pedidos B2B da rede, marketplace, etc.)."
        ),
        "padrao": "Exportar",
        "opcoes": [
            {
                "nome": "Importar",
                "efeito": (
                    "Pedidos criados no <strong>Bling</strong> são trazidos para o DropNexo. "
                    "Útil se você fatura ou processa pedidos primeiro no ERP."
                ),
            },
            {
                "nome": "Exportar",
                "efeito": (
                    "Pedidos gerados no <strong>DropNexo</strong> são enviados ao Bling para faturamento, "
                    "expedição e NF-e. Padrão recomendado para <strong>fornecedor</strong> que recebe pedidos da rede."
                ),
            },
            {
                "nome": "Atualizar (ambos)",
                "efeito": (
                    "Pedidos podem ser criados ou atualizados nos dois sistemas e refletidos no outro lado, "
                    "conforme status e regras do conector."
                ),
            },
        ],
        "nota": (
            "A sincronização de pedidos depende do módulo de pedidos B2B e será liberada em fase posterior. "
            "Salve a opção desejada já agora."
        ),
    },
]

MANUAL_BLING_BOTOES_FORNECEDOR = [
    {
        "nome": "Salvar",
        "efeito": "Grava todas as opções acima para o perfil ativo (<strong>fornecedor</strong> ou <strong>vendedor</strong>).",
    },
    {
        "nome": "Importar produtos (catálogo)",
        "efeito": (
            "A importação manual fica em <strong>Catálogos → Meu catálogo → Importar Bling</strong> "
            "(visível só com integração conectada e modo <em>Produtos</em> em Importar ou Atualizar). "
            "Lá você pode importar tudo ou escolher categorias do Bling."
        ),
    },
]
