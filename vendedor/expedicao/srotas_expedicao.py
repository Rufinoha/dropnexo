from __future__ import annotations

from pathlib import Path

from flask import Blueprint, jsonify, redirect, session, url_for

from global_utils import exigir_modulo, login_obrigatorio
from sistema.plataforma.sessao import MODULO_VENDEDOR

_MOD = Path(__file__).resolve().parent
vd_expedicao_bp = Blueprint(
    "vd_expedicao",
    __name__,
    root_path=str(_MOD),
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/vendedor/expedicao",
)


def init_app(app):
    app.register_blueprint(vd_expedicao_bp)


def _id_vendedor() -> int | None:
    tid = session.get("id_tenant")
    return int(tid) if tid else None


@vd_expedicao_bp.get("/vendedor/expedicao")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
def expedicao():
    """Tela descontinuada — redireciona para Pedidos."""
    return redirect(url_for("vd_pedidos.pedidos"))


@vd_expedicao_bp.get("/vendedor/expedicao/dados")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
def expedicao_dados():
    return jsonify(
        success=False,
        message="A tela de Expedição foi descontinuada. Use Pedidos.",
    ), 410
