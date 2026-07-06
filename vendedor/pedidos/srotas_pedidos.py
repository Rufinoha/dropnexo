from __future__ import annotations

from pathlib import Path

from flask import Blueprint, jsonify, render_template, request, session, url_for

from api.mercadopago.cliente import meios_pagamento_fornecedor

from global_utils import Var_ConectarBanco, exigir_modulo, exigir_permissao, login_obrigatorio
from servico_pedido import (
    buscar_produtos_pedido,
    cancelar_pedido,
    confirmar_grupo,
    confirmar_pedido,
    listar_fornecedores_pedido,
    listar_pedidos_vendedor,
    obter_pedido,
    salvar_rascunho,
    taxas_fornecedores_vendedor,
)
from servico_pedido_mp import iniciar_pagamento, meios_pagamento_pedido, sincronizar_pagamento_pedido
from srotas_plataforma import MODULO_VENDEDOR

_MOD = Path(__file__).resolve().parent
vd_pedidos_bp = Blueprint(
    "vd_pedidos",
    __name__,
    root_path=str(_MOD),
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/vendedor/pedidos",
)


def init_app(app):
    app.register_blueprint(vd_pedidos_bp)


def _id_vendedor() -> int | None:
    tid = session.get("id_tenant")
    return int(tid) if tid else None


def _id_usuario() -> int | None:
    uid = session.get("id_usuario")
    return int(uid) if uid else None


@vd_pedidos_bp.get("/vendedor/pedidos")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_pedidos.ver")
def pedidos():
    return render_template("frm_vd_pedidos.html", nav_ativo="vd_pedidos")


def _taxas_fornecedores_map(cur, id_vendedor: int) -> dict:
    return {str(k): v for k, v in taxas_fornecedores_vendedor(cur, id_vendedor).items()}


@vd_pedidos_bp.get("/vendedor/pedidos/dados")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_pedidos.ver")
def pedidos_dados():
    id_v = _id_vendedor()
    if not id_v:
        return jsonify(success=False, message="Sessão inválida."), 403
    status = (request.args.get("status") or "").strip() or None
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        return jsonify(
            success=True,
            pedidos=listar_pedidos_vendedor(cur, id_v, status),
            fornecedores=listar_fornecedores_pedido(cur, id_v),
            taxas_fornecedor=_taxas_fornecedores_map(cur, id_v),
        )
    finally:
        conn.close()


@vd_pedidos_bp.get("/vendedor/pedidos/produtos")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_pedidos.ver")
def pedidos_produtos():
    id_v = _id_vendedor()
    if not id_v:
        return jsonify(success=False, message="Sessão inválida."), 403
    termo = request.args.get("q") or ""
    id_forn = request.args.get("id_fornecedor")
    id_forn_i = int(id_forn) if id_forn else None
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        return jsonify(
            success=True,
            produtos=buscar_produtos_pedido(cur, id_v, termo, id_forn_i),
        )
    finally:
        conn.close()


@vd_pedidos_bp.get("/vendedor/pedidos/<int:id_pedido>")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_pedidos.ver")
def pedido_detalhe(id_pedido: int):
    id_v = _id_vendedor()
    if not id_v:
        return jsonify(success=False, message="Sessão inválida."), 403
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        ped = obter_pedido(cur, id_pedido, id_vendedor=id_v)
        if not ped:
            return jsonify(success=False, message="Pedido não encontrado."), 404
        return jsonify(success=True, pedido=ped)
    finally:
        conn.close()


@vd_pedidos_bp.post("/vendedor/pedidos/salvar")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_pedidos.editar")
def pedidos_salvar():
    id_v = _id_vendedor()
    if not id_v:
        return jsonify(success=False, message="Sessão inválida."), 403
    body = request.get_json(silent=True) or {}
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        res = salvar_rascunho(cur, id_v, body, id_usuario=_id_usuario())
        conn.commit()
        return jsonify(success=True, message="Rascunho salvo.", **res)
    except ValueError as e:
        return jsonify(success=False, message=str(e)), 400
    finally:
        conn.close()


@vd_pedidos_bp.post("/vendedor/pedidos/confirmar")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_pedidos.editar")
def pedidos_confirmar():
    id_v = _id_vendedor()
    if not id_v:
        return jsonify(success=False, message="Sessão inválida."), 403
    body = request.get_json(silent=True) or {}
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        if body.get("id_grupo"):
            ids = confirmar_grupo(cur, id_v, int(body["id_grupo"]), id_usuario=_id_usuario())
            msg = f"{len(ids)} pedido(s) confirmado(s). Estoque reservado. Aguardando pagamento."
        elif body.get("id_pedido"):
            confirmar_pedido(cur, id_v, int(body["id_pedido"]), id_usuario=_id_usuario())
            ids = [int(body["id_pedido"])]
            msg = "Pedido confirmado. Estoque reservado. Aguardando pagamento."
        else:
            return jsonify(success=False, message="Informe id_grupo ou id_pedido."), 400
        conn.commit()
        return jsonify(success=True, message=msg, pedidos_ids=ids)
    except ValueError as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 400
    finally:
        conn.close()


@vd_pedidos_bp.post("/vendedor/pedidos/cancelar")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_pedidos.editar")
def pedidos_cancelar():
    id_v = _id_vendedor()
    if not id_v:
        return jsonify(success=False, message="Sessão inválida."), 403
    body = request.get_json(silent=True) or {}
    try:
        id_pedido = int(body.get("id_pedido"))
    except (TypeError, ValueError):
        return jsonify(success=False, message="Pedido inválido."), 400
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cancelar_pedido(
            cur,
            id_pedido,
            id_vendedor=id_v,
            id_usuario=_id_usuario(),
            motivo=body.get("motivo"),
        )
        conn.commit()
        return jsonify(success=True, message="Pedido cancelado.")
    except ValueError as e:
        return jsonify(success=False, message=str(e)), 400
    finally:
        conn.close()


@vd_pedidos_bp.get("/vendedor/pedidos/meios-pagamento/preview")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_pedidos.ver")
def pedidos_meios_preview():
    """Meios de pagamento por fornecedor (preview antes de confirmar o pedido)."""
    id_v = _id_vendedor()
    if not id_v:
        return jsonify(success=False, message="Sessão inválida."), 403
    raw = (request.args.get("fornecedores") or "").strip()
    ids: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            ids.append(int(part))
    if not ids:
        return jsonify(success=True, fornecedores=[])

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        mp_icone = url_for("mercadopago.static", filename="imge/icone_mercadopago.png")
        out = []
        for id_f in ids:
            cur.execute(
                "SELECT COALESCE(NULLIF(TRIM(nome_fantasia), ''), nome) FROM tbl_tenant WHERE id = %s",
                (id_f,),
            )
            row = cur.fetchone()
            nome = (row[0] if row else "") or f"Fornecedor #{id_f}"
            meios = meios_pagamento_fornecedor(cur, id_f)
            out.append(
                {
                    "id_fornecedor": id_f,
                    "fornecedor_nome": nome,
                    "integracao": "mercado-pago",
                    "integracao_nome": "Mercado Pago",
                    "icone_url": mp_icone,
                    **meios,
                }
            )
        return jsonify(success=True, fornecedores=out)
    finally:
        conn.close()


@vd_pedidos_bp.get("/vendedor/pedidos/<int:id_pedido>/meios-pagamento")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_pedidos.ver")
def pedido_meios_pagamento(id_pedido: int):
    id_v = _id_vendedor()
    if not id_v:
        return jsonify(success=False, message="Sessão inválida."), 403
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        dados = meios_pagamento_pedido(cur, id_v, id_pedido)
        return jsonify(success=True, **dados)
    except ValueError as e:
        return jsonify(success=False, message=str(e)), 400
    finally:
        conn.close()


@vd_pedidos_bp.post("/vendedor/pedidos/pagar")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_pedidos.editar")
def pedidos_pagar():
    id_v = _id_vendedor()
    if not id_v:
        return jsonify(success=False, message="Sessão inválida."), 403
    body = request.get_json(silent=True) or {}
    try:
        id_pedido = int(body.get("id_pedido"))
    except (TypeError, ValueError):
        return jsonify(success=False, message="Pedido inválido."), 400
    meio = (body.get("meio") or "").strip().lower()
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        result = iniciar_pagamento(
            cur,
            id_v,
            id_pedido,
            meio,
            email_sessao=session.get("email"),
        )
        conn.commit()
        return jsonify(success=True, message="Pagamento iniciado.", **result)
    except ValueError as e:
        return jsonify(success=False, message=str(e)), 400
    except RuntimeError as e:
        return jsonify(success=False, message=str(e)), 502
    finally:
        conn.close()


@vd_pedidos_bp.get("/vendedor/pedidos/<int:id_pedido>/pagamento/status")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_pedidos.ver")
def pedido_pagamento_status(id_pedido: int):
    id_v = _id_vendedor()
    if not id_v:
        return jsonify(success=False, message="Sessão inválida."), 403
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        result = sincronizar_pagamento_pedido(cur, id_v, id_pedido)
        conn.commit()
        return jsonify(success=True, **result)
    except ValueError as e:
        return jsonify(success=False, message=str(e)), 400
    except RuntimeError as e:
        return jsonify(success=False, message=str(e)), 502
    finally:
        conn.close()


@vd_pedidos_bp.get("/vendedor/pedidos/pagamento/retorno")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_pedidos.ver")
def pedidos_pagamento_retorno():
    from flask import redirect, url_for

    id_v = _id_vendedor()
    st = (request.args.get("status") or "").strip().lower()
    try:
        id_pedido = int(request.args.get("id_pedido") or 0)
    except (TypeError, ValueError):
        id_pedido = 0

    if id_v and id_pedido:
        conn = Var_ConectarBanco()
        try:
            cur = conn.cursor()
            sincronizar_pagamento_pedido(cur, id_v, id_pedido)
            conn.commit()
        except Exception:
            conn.rollback()
        finally:
            conn.close()

    q = f"pagamento={st or 'retorno'}"
    if id_pedido:
        q += f"&id_pedido={id_pedido}"
    return redirect(f"/vendedor/pedidos?{q}")
