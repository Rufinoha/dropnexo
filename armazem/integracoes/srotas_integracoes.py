# armazem/integracoes — reusa hub de integrações no módulo armazém
from __future__ import annotations

from pathlib import Path

from flask import Blueprint, redirect, url_for

from global_utils import exigir_modulo, login_obrigatorio
from sistema.plataforma.sessao import MODULO_ARMAZEM

_MOD = Path(__file__).resolve().parent

az_integracoes_bp = Blueprint(
    "az_integracoes",
    __name__,
    root_path=str(_MOD),
)


def init_app(app):
    app.register_blueprint(az_integracoes_bp)


@az_integracoes_bp.get("/armazem/integracoes")
@login_obrigatorio()
@exigir_modulo(MODULO_ARMAZEM)
def pagina():
    return redirect(url_for("integracoes.pagina"))
