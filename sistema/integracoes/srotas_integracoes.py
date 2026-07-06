from pathlib import Path

from flask import Blueprint, jsonify, redirect, render_template, session, url_for

from global_utils import Var_ConectarBanco, login_obrigatorio, usuario_tem_permissao
from srotas_plataforma import garantir_modulo_sessao
from srotas_negocio import catalogo_com_urls, catalogo_integracoes_modulo, render_pagina_integracoes, url_icone_integracao

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


@integracoes_bp.get("/integracoes/bling")
@login_obrigatorio()
def pagina_bling():
    if not _pode_ver_integracoes():
        return redirect(url_for("dashboard.index"))
    bling_conectado = _bling_conectado(session.get("id_tenant"))
    return render_template(
        "frm_bling_integracao.html",
        nav_codigo="integracoes",
        icone_bling=url_icone_integracao("bling", icones_base_url=_icones_base_url()),
        bling_conectado=bling_conectado,
    )


@integracoes_bp.get("/integracoes/mercadopago")
@login_obrigatorio()
def pagina_mercadopago():
    if not _pode_ver_integracoes():
        return redirect(url_for("dashboard.index"))
    if session.get("tenant_tipo_negocio") not in ("fornecedor", "hibrido") and not session.get("eh_desenvolvedor"):
        return redirect(url_for("integracoes.pagina", erro="Opções financeiras são apenas para fornecedores."))
    from api.mercadopago.cliente import mp_conectado

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


@integracoes_bp.get("/api/integracoes/hub/status")
@login_obrigatorio()
def hub_status():
    if not _pode_ver_integracoes():
        return jsonify(success=False, message="Sem permissão."), 403

    id_tenant = session.get("id_tenant")
    bling_conectado = False
    mp_ok = False
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT status FROM tbl_integracao_bling WHERE id_tenant = %s",
            (id_tenant,),
        )
        row = cur.fetchone()
        bling_conectado = bool(row and row[0] == "conectado")
        if id_tenant:
            from api.mercadopago.cliente import mp_conectado

            try:
                mp_ok = mp_conectado(cur, int(id_tenant))
            except Exception:
                mp_ok = False
    finally:
        conn.close()

    return jsonify(
        success=True,
        contexto_modulo=garantir_modulo_sessao(),
        integracoes={
            "bling": {
                "conectado": bling_conectado,
                "config_url": url_for("integracoes.pagina_bling"),
                "oauth_url": url_for("bling.oauth_iniciar"),
            },
            "mercado-pago": {
                "conectado": mp_ok,
                "config_url": url_for("integracoes.pagina_mercadopago"),
                "oauth_url": url_for("mercadopago.oauth_iniciar"),
            },
        },
    )


@integracoes_bp.get("/integracoes/catalogo")
@login_obrigatorio()
def catalogo():
    if not _pode_ver_integracoes():
        return jsonify(success=False, message="Sem permissão."), 403
    return jsonify(success=True, categorias=catalogo_integracoes_modulo(_icones_base_url()))
