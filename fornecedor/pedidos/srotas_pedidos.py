from __future__ import annotations

from pathlib import Path

from flask import Blueprint, jsonify, render_template, request, session

from global_utils import Var_ConectarBanco, exigir_modulo, exigir_permissao, login_obrigatorio
from servico_pedido import (
    listar_anexos_pedido,
    listar_pedidos_fornecedor,
    marcar_em_expedicao,
    marcar_entregue,
    obter_pedido,
)
from servico_pedido_pix_manual import confirmar_pix_manual, rejeitar_comprovante_pix
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


def _id_usuario() -> int | None:
    uid = session.get("id_usuario")
    return int(uid) if uid else None


@fn_pedidos_bp.post("/fornecedor/pedidos/<int:id_pedido>/expedir")
@login_obrigatorio()
@exigir_modulo(MODULO_FORNECEDOR)
@exigir_permissao(codigo="fn_pedidos.editar")
def pedido_expedir(id_pedido: int):
    id_f = _id_fornecedor()
    if not id_f:
        return jsonify(success=False, message="Sessão inválida."), 403
    body = request.get_json(silent=True) or {}
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        marcar_em_expedicao(
            cur,
            id_pedido,
            id_fornecedor=id_f,
            codigo_rastreio=body.get("codigo_rastreio"),
            transportadora=body.get("transportadora"),
            id_usuario=_id_usuario(),
        )
        conn.commit()
        return jsonify(success=True, message="Pedido marcado em expedição. Estoque baixado.")
    except ValueError as e:
        return jsonify(success=False, message=str(e)), 400
    finally:
        conn.close()


@fn_pedidos_bp.post("/fornecedor/pedidos/<int:id_pedido>/entregue")
@login_obrigatorio()
@exigir_modulo(MODULO_FORNECEDOR)
@exigir_permissao(codigo="fn_pedidos.editar")
def pedido_entregue(id_pedido: int):
    id_f = _id_fornecedor()
    if not id_f:
        return jsonify(success=False, message="Sessão inválida."), 403
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        marcar_entregue(cur, id_pedido, id_fornecedor=id_f, id_usuario=_id_usuario())
        conn.commit()
        return jsonify(success=True, message="Pedido marcado como entregue.")
    except ValueError as e:
        return jsonify(success=False, message=str(e)), 400
    finally:
        conn.close()


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
        ped["anexos"] = listar_anexos_pedido(cur, id_pedido, id_fornecedor=id_f)
        return jsonify(success=True, pedido=ped)
    finally:
        conn.close()


@fn_pedidos_bp.post("/fornecedor/pedidos/<int:id_pedido>/pagamento/confirmar")
@login_obrigatorio()
@exigir_modulo(MODULO_FORNECEDOR)
@exigir_permissao(codigo="fn_pedidos.editar")
def pedido_confirmar_pix(id_pedido: int):
    id_f = _id_fornecedor()
    if not id_f:
        return jsonify(success=False, message="Sessão inválida."), 403
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        confirmar_pix_manual(cur, id_pedido, id_fornecedor=id_f, id_usuario=_id_usuario())
        conn.commit()
        return jsonify(success=True, message="Pagamento confirmado. Pedido liberado.")
    except ValueError as e:
        return jsonify(success=False, message=str(e)), 400
    finally:
        conn.close()


@fn_pedidos_bp.post("/fornecedor/pedidos/<int:id_pedido>/pagamento/rejeitar")
@login_obrigatorio()
@exigir_modulo(MODULO_FORNECEDOR)
@exigir_permissao(codigo="fn_pedidos.editar")
def pedido_rejeitar_pix(id_pedido: int):
    id_f = _id_fornecedor()
    if not id_f:
        return jsonify(success=False, message="Sessão inválida."), 403
    body = request.get_json(silent=True) or {}
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        rejeitar_comprovante_pix(
            cur,
            id_pedido,
            id_fornecedor=id_f,
            id_usuario=_id_usuario(),
            motivo=body.get("motivo"),
        )
        conn.commit()
        return jsonify(success=True, message="Comprovante rejeitado. Solicite novo envio ao vendedor.")
    except ValueError as e:
        return jsonify(success=False, message=str(e)), 400
    finally:
        conn.close()
