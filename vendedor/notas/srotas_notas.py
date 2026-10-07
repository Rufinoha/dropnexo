from __future__ import annotations

from pathlib import Path

from flask import Blueprint, jsonify, render_template, request, send_file, session, url_for

from global_utils import Var_ConectarBanco, exigir_modulo, exigir_permissao, login_obrigatorio
from sistema.plataforma.sessao import MODULO_VENDEDOR

_MOD = Path(__file__).resolve().parent

vd_notas_bp = Blueprint(
    "vd_notas",
    __name__,
    root_path=str(_MOD),
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/vendedor/notas",
)


def init_app(app):
    app.register_blueprint(vd_notas_bp)


def _tid() -> int | None:
    tid = session.get("id_tenant")
    return int(tid) if tid else None


def _vendedor():
    if session.get("tenant_tipo_negocio") in ("vendedor", "hibrido") or session.get("eh_desenvolvedor"):
        return None
    return jsonify(success=False, message="Conta não é vendedor."), 403


_PLANOS_NOTA = frozenset({"professional", "scale", "enterprise"})


def _pode_emitir_nota(cur, id_tenant: int) -> dict:
    """Nota do vendedor começa no plano Crescer. Certificado é a segunda trava."""
    from global_utils import plano_slug_banco
    from sistema.fiscal.nfe_servico import ler_config

    slug = plano_slug_banco(session.get("tenant_plano"))
    try:
        cur.execute("SAVEPOINT sp_plano_nota")
        cur.execute(
            "SELECT plano_slug FROM tbl_tenant_cobranca WHERE id_tenant = %s",
            (int(id_tenant),),
        )
        row = cur.fetchone()
        cur.execute("RELEASE SAVEPOINT sp_plano_nota")
        if row and row[0]:
            slug = plano_slug_banco(row[0])
    except Exception:
        try:
            cur.execute("ROLLBACK TO SAVEPOINT sp_plano_nota")
        except Exception:
            pass
    cfg = ler_config(cur, int(id_tenant))
    return {
        "plano_ok": slug in _PLANOS_NOTA,
        "tem_certificado": bool(cfg.get("tem_certificado")),
    }


@vd_notas_bp.get("/vendedor/notas")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_notas.ver")
def notas_pagina():
    if (r := _vendedor()) is not None:
        return r
    return render_template(
        "frm_vd_notas.html",
        nav_ativo="vd_notas",
        nf_planos=url_for("planos.meu_plano", escolher=1),
    )


@vd_notas_bp.get("/vendedor/notas/listar")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_notas.ver")
def notas_listar():
    if (r := _vendedor()) is not None:
        return r
    tid = _tid()
    conn = Var_ConectarBanco()
    try:
        from sistema.fiscal.nfe_servico import listar_nfe

        return jsonify(success=True, notas=listar_nfe(conn.cursor(), tid))
    finally:
        conn.close()


@vd_notas_bp.get("/vendedor/notas/pode-emitir")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_notas.ver")
def notas_pode_emitir():
    if (r := _vendedor()) is not None:
        return r
    conn = Var_ConectarBanco()
    try:
        return jsonify(success=True, **_pode_emitir_nota(conn.cursor(), _tid()))
    finally:
        conn.close()


@vd_notas_bp.post("/vendedor/notas/emitir")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_notas.ver")
def notas_emitir():
    if (r := _vendedor()) is not None:
        return r
    tid = _tid()
    body = request.get_json(silent=True) or {}
    conn = Var_ConectarBanco()
    try:
        from sistema.fiscal.nfe_servico import emitir_avulsa, emitir_pedido

        gate = _pode_emitir_nota(conn.cursor(), tid)
        if not gate["plano_ok"]:
            return jsonify(success=False, message="A emissão de nota começa no plano Crescer."), 400
        id_pedido = int(body.get("id_pedido") or 0)
        if id_pedido:
            dados = emitir_pedido(conn, tid, id_pedido, session.get("id_usuario"))
        else:
            dados = emitir_avulsa(conn, tid, body, session.get("id_usuario"))
        return jsonify(success=True, message="Nota enviada.", nota=dados)
    except ValueError as e:
        return jsonify(success=False, message=str(e)), 400
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@vd_notas_bp.post("/vendedor/notas/<int:id_nfe>/atualizar")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_notas.ver")
def notas_atualizar(id_nfe: int):
    if (r := _vendedor()) is not None:
        return r
    conn = Var_ConectarBanco()
    try:
        from sistema.fiscal.nfe_servico import atualizar_status

        dados = atualizar_status(conn, _tid(), id_nfe)
        return jsonify(success=True, nota=dados)
    except ValueError as e:
        return jsonify(success=False, message=str(e)), 400
    finally:
        conn.close()


@vd_notas_bp.get("/vendedor/notas/<int:id_nfe>/arquivo/<tipo>")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_notas.ver")
def notas_arquivo(id_nfe: int, tipo: str):
    if (r := _vendedor()) is not None:
        return r
    if tipo not in ("pdf", "xml"):
        return jsonify(success=False, message="Arquivo inválido."), 400
    conn = Var_ConectarBanco()
    try:
        from sistema.fiscal.nfe_servico import caminho_arquivo_nfe

        caminho = caminho_arquivo_nfe(conn.cursor(), _tid(), id_nfe, tipo)
        mime = "application/pdf" if tipo == "pdf" else "application/xml"
        return send_file(caminho, mimetype=mime, as_attachment=tipo == "xml", download_name=caminho.name)
    except ValueError as e:
        return jsonify(success=False, message=str(e)), 404
    finally:
        conn.close()
