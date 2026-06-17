"""Marktplace — vitrine de add-ons e treinamentos."""
from __future__ import annotations

from pathlib import Path

from flask import Blueprint, jsonify, render_template, session

from global_utils import Var_ConectarBanco, login_obrigatorio
from sistema.marktplace.servico_marktplace import (
    SQL_LISTA_ATIVOS,
    filtrar_para_tenant,
    formatar_preco,
    produto_dict,
)

_MOD_DIR = Path(__file__).resolve().parent

marktplace_bp = Blueprint(
    "marktplace",
    __name__,
    root_path=str(_MOD_DIR),
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/marktplace",
)


def init_app(app):
    app.register_blueprint(marktplace_bp)


@marktplace_bp.get("/marktplace")
@login_obrigatorio()
def pagina():
    return render_template("frm_marktplace.html", nav_ativo="marktplace")


@marktplace_bp.get("/marktplace/catalogo")
@login_obrigatorio()
def catalogo():
    tipo = session.get("tenant_tipo_negocio", "vendedor")
    plano = session.get("tenant_plano", "starter")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(SQL_LISTA_ATIVOS)
        rows = [produto_dict(r) for r in cur.fetchall()]
    finally:
        conn.close()
    lista = filtrar_para_tenant(rows, tipo_negocio=tipo, plano=plano)
    for p in lista:
        p["preco_label"] = formatar_preco(p["valor_centavos"], p["tipo_pagamento"])
    return jsonify(
        success=True,
        produtos=lista,
        tipo_negocio=tipo,
        plano=plano,
    )
