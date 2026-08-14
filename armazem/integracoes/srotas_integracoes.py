# armazem/integracoes — mesmo hub do fornecedor no módulo armazém
from __future__ import annotations

from pathlib import Path

from flask import Blueprint, redirect, session, url_for

from global_utils import exigir_modulo, login_obrigatorio, usuario_tem_permissao
from sistema.plataforma.sessao import MODULO_ARMAZEM

_MOD = Path(__file__).resolve().parent

az_integracoes_bp = Blueprint(
    "az_integracoes",
    __name__,
    root_path=str(_MOD),
)


def init_app(app):
    app.register_blueprint(az_integracoes_bp)


def _pode_ver() -> bool:
    return bool(
        session.get("eh_desenvolvedor")
        or usuario_tem_permissao("integracoes.ver")
        or usuario_tem_permissao("fn_integracoes.ver")
        or usuario_tem_permissao("az_integracoes.ver")
    )


@az_integracoes_bp.get("/armazem/integracoes")
@login_obrigatorio()
@exigir_modulo(MODULO_ARMAZEM)
def pagina():
    from sistema.integracoes.srotas_integracoes import _icones_base_url, render_pagina_integracoes

    if not _pode_ver():
        return redirect(url_for("dashboard.index"))
    return render_pagina_integracoes(
        nav_codigo="az_integracoes",
        icones_base_url=_icones_base_url(),
    )
