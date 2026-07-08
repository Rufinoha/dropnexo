from __future__ import annotations

from pathlib import Path

from flask import Blueprint, jsonify, render_template, request, session

from global_utils import Var_ConectarBanco, exigir_modulo, exigir_permissao, login_obrigatorio
from core.pedidos.servico import listar_pedidos_expedicao_vendedor
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
@exigir_permissao(codigo="vd_pedidos.ver")
def expedicao():
    return render_template("frm_vd_expedicao.html", nav_ativo="vd_expedicao")


@vd_expedicao_bp.get("/vendedor/expedicao/dados")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_pedidos.ver")
def expedicao_dados():
    id_v = _id_vendedor()
    if not id_v:
        return jsonify(success=False, message="Sessão inválida."), 403
    status = (request.args.get("status") or "").strip() or None
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        pedidos = listar_pedidos_expedicao_vendedor(cur, id_v)
        if status:
            pedidos = [p for p in pedidos if p.get("status") == status]
        return jsonify(success=True, pedidos=pedidos)
    finally:
        conn.close()
