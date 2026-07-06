from __future__ import annotations

from pathlib import Path

from flask import Blueprint, jsonify, render_template, request, session

from global_utils import Var_ConectarBanco, exigir_modulo, exigir_permissao, login_obrigatorio
from servico_pedido import listar_pedidos_fornecedor, obter_pedido
from srotas_plataforma import MODULO_FORNECEDOR

_MOD = Path(__file__).resolve().parent
fn_pedidos_bp = Blueprint(
    "fn_pedidos",
    __name__,
    root_path=str(_MOD),
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/fornecedor/pedidos",
)


def init_app(app):
    app.register_blueprint(fn_pedidos_bp)


def _id_fornecedor() -> int | None:
    tid = session.get("id_tenant")
    return int(tid) if tid else None


@fn_pedidos_bp.get("/fornecedor/pedidos")
@login_obrigatorio()
@exigir_modulo(MODULO_FORNECEDOR)
@exigir_permissao(codigo="fn_pedidos.ver")
def pedidos():
    return render_template("frm_fn_pedidos.html", nav_ativo="fn_pedidos")


@fn_pedidos_bp.get("/fornecedor/pedidos/dados")
@login_obrigatorio()
@exigir_modulo(MODULO_FORNECEDOR)
@exigir_permissao(codigo="fn_pedidos.ver")
def pedidos_dados():
    id_f = _id_fornecedor()
    if not id_f:
        return jsonify(success=False, message="Sessão inválida."), 403
    status = (request.args.get("status") or "").strip() or None
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        return jsonify(success=True, pedidos=listar_pedidos_fornecedor(cur, id_f, status))
    finally:
        conn.close()


@fn_pedidos_bp.get("/fornecedor/pedidos/<int:id_pedido>")
@login_obrigatorio()
@exigir_modulo(MODULO_FORNECEDOR)
@exigir_permissao(codigo="fn_pedidos.ver")
def pedido_detalhe(id_pedido: int):
    id_f = _id_fornecedor()
    if not id_f:
        return jsonify(success=False, message="Sessão inválida."), 403
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        ped = obter_pedido(cur, id_pedido, id_fornecedor=id_f)
        if not ped:
            return jsonify(success=False, message="Pedido não encontrado."), 404
        return jsonify(success=True, pedido=ped)
    finally:
        conn.close()
