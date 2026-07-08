# sistema/integracoes/srotas_integracoes.py — catálogo e rotas do hub de integrações
from __future__ import annotations

# ── catalogo ──────────────────────────────────────────

import json
from pathlib import Path

from flask import render_template, session, url_for

from sistema.plataforma.sessao import MODULO_FORNECEDOR, MODULO_VENDEDOR, garantir_modulo_sessao

_RAIZ_PROJETO = Path(__file__).resolve().parents[2]
_ICONES_API_DIR = _RAIZ_PROJETO / "static" / "imge" / "icone_api"

ICONES_API_ARQUIVOS: dict[str, str] = {
    "bling": "icone_bling.png",
    "olist": "icone_olist.png",
    "conta-azul": "icone_contaazul.png",
}

HUB_COPY_INTEGRACOES = {
    MODULO_FORNECEDOR: {
        "titulo": "Integrações",
        "descricao": "Receba pagamentos dos vendedores e sincronize seu catálogo com ERPs.",
    },
    MODULO_VENDEDOR: {
        "titulo": "Integrações",
        "descricao": "Importe pedidos das suas lojas, contrate fretes e acompanhe envios.",
    },
}

_MOD_VENDEDOR = [MODULO_VENDEDOR]
_MOD_FORNECEDOR = [MODULO_FORNECEDOR]

CATEGORIAS_INTEGRACOES = [
    {
        "id": "financeiro",
        "rotulo": "Recebimentos",
        "titulo": "Recebimentos",
        "subtitulo": "Formas de pagamento dos pedidos B2B (PIX e cartão).",
        "modulos": _MOD_FORNECEDOR,
        "itens": [
            {
                "slug": "mercado-pago",
                "nome": "Mercado Pago",
                "descricao": "PIX e cartão de crédito nos pedidos B2B.",
                "cor": "#009EE3",
                "iniciais": "MP",
                "modulos": _MOD_FORNECEDOR,
            },
            {
                "slug": "pix-manual",
                "nome": "PIX Manual",
                "descricao": "Sua chave PIX — o vendedor paga e envia o comprovante.",
                "cor": "#32BCAD",
                "iniciais": "PX",
                "modulos": _MOD_FORNECEDOR,
            },
            {"slug": "pagbank", "nome": "PagBank", "descricao": "Recebimentos PagBank.", "cor": "#1BB99A", "iniciais": "PB", "modulos": _MOD_FORNECEDOR},
            {"slug": "stripe", "nome": "Stripe", "descricao": "Pagamentos internacionais Stripe.", "cor": "#635BFF", "iniciais": "ST", "modulos": _MOD_FORNECEDOR},
            {"slug": "asaas", "nome": "Asaas", "descricao": "Cobranças e recebimentos Asaas.", "cor": "#0030B9", "iniciais": "AS", "modulos": _MOD_FORNECEDOR},
            {"slug": "pagar-me", "nome": "Pagar.me", "descricao": "Gateway Pagar.me.", "cor": "#65A300", "iniciais": "PM", "modulos": _MOD_FORNECEDOR},
            {"slug": "paypal", "nome": "PayPal", "descricao": "Pagamentos PayPal.", "cor": "#003087", "iniciais": "PP", "modulos": _MOD_FORNECEDOR},
        ],
    },
    {
        "id": "catalogo",
        "rotulo": "Catálogo e ERP",
        "titulo": "Catálogo e ERP",
        "subtitulo": "Sincronize produtos, estoque, categorias e NF-e.",
        "modulos": _MOD_FORNECEDOR,
        "itens": [
            {
                "slug": "bling",
                "nome": "Bling",
                "descricao": "Importe produtos, estoque e categorias do seu Bling.",
                "cor": "#28A745",
                "iniciais": "BL",
                "modulos": _MOD_FORNECEDOR,
                "papel": "catalogo",
            },
            {"slug": "olist", "nome": "Olist", "descricao": "Hub Olist para marketplaces e lojas.", "cor": "#6C2EB9", "iniciais": "OL", "modulos": _MOD_FORNECEDOR},
            {"slug": "conta-azul", "nome": "Conta Azul", "descricao": "Gestão financeira e emissão de notas.", "cor": "#0080FF", "iniciais": "CA", "modulos": _MOD_FORNECEDOR},
        ],
    },
    {
        "id": "pedidos",
        "rotulo": "Pedidos",
        "titulo": "Pedidos e lojas",
        "subtitulo": "Importe pedidos de marketplaces, e-commerce e ERP.",
        "modulos": _MOD_VENDEDOR,
        "itens": [
            {
                "slug": "bling",
                "nome": "Bling",
                "descricao": "Importe pedidos de venda pagos do seu Bling.",
                "cor": "#28A745",
                "iniciais": "BL",
                "modulos": _MOD_VENDEDOR,
                "papel": "pedidos",
            },
            {"slug": "mercado-livre", "nome": "Mercado Livre", "descricao": "Pedidos e anúncios do Mercado Livre.", "cor": "#FFE600", "iniciais": "ML", "modulos": _MOD_VENDEDOR},
            {"slug": "amazon", "nome": "Amazon", "descricao": "Pedidos da Amazon no seu painel.", "cor": "#FF9900", "iniciais": "AZ", "modulos": _MOD_VENDEDOR},
            {"slug": "magazine-luiza", "nome": "Magazine Luiza", "descricao": "Pedidos do marketplace Magalu.", "cor": "#0086FF", "iniciais": "MG", "modulos": _MOD_VENDEDOR},
            {"slug": "shopee", "nome": "Shopee", "descricao": "Pedidos da Shopee em um só lugar.", "cor": "#EE4D2D", "iniciais": "SH", "modulos": _MOD_VENDEDOR},
            {"slug": "americanas", "nome": "Americanas", "descricao": "Pedidos Americanas / B2W.", "cor": "#E60014", "iniciais": "AM", "modulos": _MOD_VENDEDOR},
            {"slug": "casas-bahia", "nome": "Casas Bahia", "descricao": "Pedidos Casas Bahia / Via.", "cor": "#0033A0", "iniciais": "CB", "modulos": _MOD_VENDEDOR},
            {"slug": "tray", "nome": "Tray", "descricao": "Pedidos da sua loja Tray.", "cor": "#7B2CFF", "iniciais": "TR", "modulos": _MOD_VENDEDOR},
            {"slug": "loja-integrada", "nome": "Loja Integrada", "descricao": "Pedidos da Loja Integrada.", "cor": "#00AEEF", "iniciais": "LI", "modulos": _MOD_VENDEDOR},
            {"slug": "nuvemshop", "nome": "Nuvemshop", "descricao": "Pedidos da sua Nuvemshop.", "cor": "#2C3E50", "iniciais": "NV", "modulos": _MOD_VENDEDOR},
            {"slug": "beezoo", "nome": "Beezoo", "descricao": "Pedidos de lojas Beezoo.", "cor": "#F5A623", "iniciais": "BZ", "modulos": _MOD_VENDEDOR},
            {"slug": "bagy", "nome": "Bagy", "descricao": "Pedidos da plataforma Bagy.", "cor": "#111827", "iniciais": "BG", "modulos": _MOD_VENDEDOR},
        ],
    },
    {
        "id": "frete",
        "rotulo": "Frete",
        "titulo": "Frete e logística",
        "subtitulo": "Cote fretes, contrate etiquetas e acompanhe rastreios.",
        "modulos": _MOD_VENDEDOR,
        "itens": [
            {
                "slug": "melhor-envio",
                "nome": "Melhor Envio",
                "descricao": "Cote e contrate fretes; o fornecedor só imprime a etiqueta.",
                "cor": "#00B2A9",
                "iniciais": "ME",
                "modulos": _MOD_VENDEDOR,
            },
            {"slug": "correios", "nome": "Correios", "descricao": "PAC, SEDEX e serviços dos Correios.", "cor": "#FFD100", "iniciais": "CR", "modulos": _MOD_VENDEDOR},
            {"slug": "frenet", "nome": "Frenet", "descricao": "Gateway de fretes para e-commerce.", "cor": "#0057A8", "iniciais": "FR", "modulos": _MOD_VENDEDOR},
        ],
    },
]


def _visivel_integracao_modulo(entidade: dict, modulo: str) -> bool:
    mods = entidade.get("modulos")
    if mods:
        return modulo in mods
    if entidade.get("somente_fornecedor"):
        return modulo == MODULO_FORNECEDOR
    return True


def hub_copy_integracoes(modulo: str | None = None) -> dict[str, str]:
    mod = modulo or garantir_modulo_sessao()
    return dict(HUB_COPY_INTEGRACOES.get(mod, HUB_COPY_INTEGRACOES[MODULO_VENDEDOR]))


def _arquivo_icone_api(slug: str) -> str | None:
    nome = ICONES_API_ARQUIVOS.get(slug)
    if nome and (_ICONES_API_DIR / nome).is_file():
        return nome
    conv = f"icone_{slug.replace('-', '')}.png"
    if (_ICONES_API_DIR / conv).is_file():
        return conv
    return None


def url_icone_integracao(slug: str, *, icones_base_url: str = "") -> str:
    if slug == "mercado-pago":
        return url_for("mercadopago.static", filename="imge/icone_mercadopago.png")
    if slug == "melhor-envio":
        return url_for("melhor_envio.static", filename="imge/icone_melhorenvio.png")
    if slug == "mercado-livre":
        return url_for("mercado_livre.static", filename="imge/icone_mercadolivre.png")
    arquivo = _arquivo_icone_api(slug)
    if arquivo:
        return url_for("static", filename=f"imge/icone_api/{arquivo}")
    base = icones_base_url if icones_base_url.endswith("/") else f"{icones_base_url}/"
    return f"{base}{slug}.png"


def catalogo_com_urls(icones_base_url: str) -> list[dict]:
    base = icones_base_url if icones_base_url.endswith("/") else icones_base_url + "/"
    out = []
    for cat in CATEGORIAS_INTEGRACOES:
        c = dict(cat)
        itens = []
        for item in cat["itens"]:
            i = dict(item)
            slug = item["slug"]
            i["icone_png"] = url_icone_integracao(slug, icones_base_url=base)
            i["icone_svg"] = f"{base}{slug}.svg"
            if _arquivo_icone_api(slug) or slug in ("mercado-pago", "melhor-envio"):
                i["icone_custom"] = True
            if item.get("papel"):
                i["bling_papel"] = item["papel"]
            itens.append(i)
        c["itens"] = itens
        out.append(c)
    return out


def catalogo_integracoes_modulo(icones_base_url: str, modulo: str | None = None) -> list[dict]:
    mod = modulo or garantir_modulo_sessao()
    cats_out: list[dict] = []
    for cat in catalogo_com_urls(icones_base_url):
        if not _visivel_integracao_modulo(cat, mod):
            continue
        itens = [i for i in cat.get("itens", []) if _visivel_integracao_modulo(i, mod)]
        if not itens:
            continue
        c = dict(cat)
        c["itens"] = itens
        cats_out.append(c)
    return cats_out


def render_pagina_integracoes(*, nav_codigo: str, icones_base_url: str):
    mod = garantir_modulo_sessao()
    copy = hub_copy_integracoes(mod)
    return render_template(
        "frm_integracoes_hub.html",
        nav_codigo=nav_codigo,
        hub_titulo=copy["titulo"],
        hub_descricao=copy["descricao"],
        modulo_ativo=mod,
        categorias_json=json.dumps(
            catalogo_integracoes_modulo(icones_base_url, mod),
            ensure_ascii=False,
        ),
    )


# ── srotas_integracoes ────────────────────────────────

from pathlib import Path

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from global_utils import Var_ConectarBanco, login_obrigatorio, usuario_tem_permissao
from sistema.plataforma.sessao import MODULO_FORNECEDOR, MODULO_VENDEDOR, garantir_modulo_sessao

_MOD_DIR = Path(__file__).resolve().parent

integracoes_bp = Blueprint(
    "integracoes",
    __name__,
    root_path=str(_MOD_DIR),
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/sistema/integracoes",
)


def init_app(app):
    app.register_blueprint(integracoes_bp)


def _icones_base_url() -> str:
    return url_for("integracoes.static", filename="imge/integracoes/")


def _pode_ver_integracoes() -> bool:
    return bool(
        session.get("eh_desenvolvedor")
        or usuario_tem_permissao("integracoes.ver")
        or usuario_tem_permissao("fn_integracoes.ver")
    )


def _redir_hub(erro: str):
    return redirect(url_for("integracoes.pagina", erro=erro))


def _exigir_modulo(*modulos: str):
    if session.get("eh_desenvolvedor"):
        return None
    if garantir_modulo_sessao() in modulos:
        return None
    labels = {"fornecedor": "fornecedores", "vendedor": "vendedores"}
    esperado = " ou ".join(labels.get(m, m) for m in modulos)
    return _redir_hub(f"Esta integração está disponível apenas para {esperado}.")


@integracoes_bp.get("/integracoes")
@login_obrigatorio()
def pagina():
    if not _pode_ver_integracoes():
        return redirect(url_for("dashboard.index"))
    return render_pagina_integracoes(nav_codigo="integracoes", icones_base_url=_icones_base_url())


def _bling_conectado(id_tenant: int | None) -> bool:
    if not id_tenant:
        return False
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT status FROM tbl_integracao_bling WHERE id_tenant = %s",
            (id_tenant,),
        )
        row = cur.fetchone()
        return bool(row and row[0] == "conectado")
    finally:
        conn.close()


def _bling_papel_padrao() -> str:
    return "pedidos" if garantir_modulo_sessao() == MODULO_VENDEDOR else "catalogo"


@integracoes_bp.get("/integracoes/bling")
@login_obrigatorio()
def pagina_bling():
    if not _pode_ver_integracoes():
        return redirect(url_for("dashboard.index"))
    papel = (request.args.get("papel") or _bling_papel_padrao()).strip().lower()
    if papel not in ("catalogo", "pedidos"):
        papel = _bling_papel_padrao()
    if papel == "catalogo" and (r := _exigir_modulo(MODULO_FORNECEDOR)) is not None:
        return r
    if papel == "pedidos" and (r := _exigir_modulo(MODULO_VENDEDOR)) is not None:
        return r
    bling_conectado = _bling_conectado(session.get("id_tenant"))
    subtitulo = (
        "Importe pedidos de venda pagos do seu Bling."
        if papel == "pedidos"
        else "Sincronize produtos, estoque e categorias do seu Bling."
    )
    return render_template(
        "frm_bling_integracao.html",
        nav_codigo="integracoes",
        icone_bling=url_icone_integracao("bling", icones_base_url=_icones_base_url()),
        bling_conectado=bling_conectado,
        bling_papel=papel,
        bling_subtitulo=subtitulo,
    )


@integracoes_bp.get("/integracoes/mercadopago")
@login_obrigatorio()
def pagina_mercadopago():
    if not _pode_ver_integracoes():
        return redirect(url_for("dashboard.index"))
    if (r := _exigir_modulo(MODULO_FORNECEDOR)) is not None:
        return r
    from api.mercadopago.mercadopago import mp_conectado

    id_tenant = session.get("id_tenant")
    conectado = False
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        if id_tenant:
            try:
                conectado = mp_conectado(cur, int(id_tenant))
            except Exception:
                conectado = False
    finally:
        conn.close()
    return render_template(
        "frm_mercadopago_integracao.html",
        nav_codigo="integracoes",
        mp_conectado=conectado,
    )


@integracoes_bp.get("/integracoes/pix-manual")
@login_obrigatorio()
def pagina_pix_manual():
    if not _pode_ver_integracoes():
        return redirect(url_for("dashboard.index"))
    if (r := _exigir_modulo(MODULO_FORNECEDOR)) is not None:
        return r
    from api.pix_manual.pix_manual import pix_manual_ativo

    id_tenant = session.get("id_tenant")
    ativo = False
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        if id_tenant:
            try:
                ativo = pix_manual_ativo(cur, int(id_tenant))
            except Exception:
                ativo = False
    finally:
        conn.close()
    return render_template(
        "frm_pix_manual_integracao.html",
        nav_codigo="integracoes",
        pix_manual_ativo=ativo,
    )


@integracoes_bp.get("/integracoes/melhor-envio")
@login_obrigatorio()
def pagina_melhor_envio():
    if not _pode_ver_integracoes():
        return redirect(url_for("dashboard.index"))
    if (r := _exigir_modulo(MODULO_VENDEDOR)) is not None:
        return r
    from api.melhor_envio.melhor_envio import me_conectado

    id_tenant = session.get("id_tenant")
    conectado = False
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        if id_tenant:
            try:
                conectado = me_conectado(cur, int(id_tenant))
            except Exception:
                conectado = False
    finally:
        conn.close()
    return render_template(
        "frm_melhor_envio_integracao.html",
        nav_codigo="integracoes",
        me_conectado=conectado,
        icone_melhor_envio=url_icone_integracao("melhor-envio", icones_base_url=_icones_base_url()),
    )


@integracoes_bp.get("/integracoes/mercado-livre")
@login_obrigatorio()
def pagina_mercado_livre():
    if not _pode_ver_integracoes():
        return redirect(url_for("dashboard.index"))
    if (r := _exigir_modulo(MODULO_VENDEDOR)) is not None:
        return r
    from api.mercado_livre.mercado_livre import ml_conectado

    id_tenant = session.get("id_tenant")
    conectado = False
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        if id_tenant:
            try:
                conectado = ml_conectado(cur, int(id_tenant))
            except Exception:
                conectado = False
    finally:
        conn.close()
    return render_template(
        "frm_mercado_livre_integracao.html",
        nav_codigo="integracoes",
        ml_conectado=conectado,
        icone_mercado_livre=url_icone_integracao("mercado-livre", icones_base_url=_icones_base_url()),
    )


@integracoes_bp.get("/api/integracoes/hub/status")
@login_obrigatorio()
def hub_status():
    if not _pode_ver_integracoes():
        return jsonify(success=False, message="Sem permissão."), 403

    id_tenant = session.get("id_tenant")
    modulo = garantir_modulo_sessao()
    bling_conectado = _bling_conectado(id_tenant)
    integracoes: dict = {}

    if modulo == MODULO_FORNECEDOR:
        mp_ok = False
        pix_ok = False
        conn = Var_ConectarBanco()
        try:
            cur = conn.cursor()
            if id_tenant:
                from api.mercadopago.mercadopago import mp_conectado
                from api.pix_manual.pix_manual import pix_manual_ativo

                try:
                    mp_ok = mp_conectado(cur, int(id_tenant))
                except Exception:
                    mp_ok = False
                try:
                    pix_ok = pix_manual_ativo(cur, int(id_tenant))
                except Exception:
                    pix_ok = False
        finally:
            conn.close()
        integracoes["bling"] = {
            "conectado": bling_conectado,
            "config_url": url_for("integracoes.pagina_bling", papel="catalogo"),
            "oauth_url": url_for("bling.oauth_iniciar"),
        }
        integracoes["mercado-pago"] = {
            "conectado": mp_ok,
            "config_url": url_for("integracoes.pagina_mercadopago"),
            "oauth_url": url_for("mercadopago.oauth_iniciar"),
        }
        integracoes["pix-manual"] = {
            "conectado": pix_ok,
            "config_url": url_for("integracoes.pagina_pix_manual"),
            "oauth_url": "",
        }

    if modulo == MODULO_VENDEDOR:
        me_ok = False
        ml_ok = False
        conn = Var_ConectarBanco()
        try:
            cur = conn.cursor()
            if id_tenant:
                from api.melhor_envio.melhor_envio import me_conectado
                from api.mercado_livre.mercado_livre import ml_conectado

                try:
                    me_ok = me_conectado(cur, int(id_tenant))
                except Exception:
                    me_ok = False
                try:
                    ml_ok = ml_conectado(cur, int(id_tenant))
                except Exception:
                    ml_ok = False
        finally:
            conn.close()
        integracoes["bling"] = {
            "conectado": bling_conectado,
            "config_url": url_for("integracoes.pagina_bling", papel="pedidos"),
            "oauth_url": url_for("bling.oauth_iniciar"),
        }
        integracoes["melhor-envio"] = {
            "conectado": me_ok,
            "config_url": url_for("integracoes.pagina_melhor_envio"),
            "oauth_url": url_for("melhor_envio.oauth_iniciar"),
        }
        integracoes["mercado-livre"] = {
            "conectado": ml_ok,
            "config_url": url_for("integracoes.pagina_mercado_livre"),
            "oauth_url": url_for("mercado_livre.oauth_iniciar"),
        }

    return jsonify(
        success=True,
        contexto_modulo=modulo,
        integracoes=integracoes,
    )


@integracoes_bp.get("/integracoes/catalogo")
@login_obrigatorio()
def catalogo():
    if not _pode_ver_integracoes():
        return jsonify(success=False, message="Sem permissão."), 403
    return jsonify(
        success=True,
        contexto_modulo=garantir_modulo_sessao(),
        categorias=catalogo_integracoes_modulo(_icones_base_url()),
    )
