from __future__ import annotations

from pathlib import Path

from flask import Blueprint, jsonify, redirect, request, session, url_for

from global_utils import Var_ConectarBanco, exigir_modulo, exigir_permissao, login_obrigatorio
from sistema.plataforma.sessao import MODULO_VENDEDOR

_MOD = Path(__file__).resolve().parent

vd_parametros_bp = Blueprint(
    "vd_parametros",
    __name__,
    root_path=str(_MOD),
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/vendedor/parametros",
)


def init_app(app):
    app.register_blueprint(vd_parametros_bp)


def _tid() -> int | None:
    tid = session.get("id_tenant")
    return int(tid) if tid else None


def _vendedor():
    if session.get("tenant_tipo_negocio") in ("vendedor", "hibrido") or session.get("eh_desenvolvedor"):
        return None
    return jsonify(success=False, message="Conta não é vendedor."), 403


@vd_parametros_bp.get("/vendedor/parametros")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_notas.ver")
def parametros_pagina():
    if (r := _vendedor()) is not None:
        return r
    return redirect(url_for("vd_notas.notas_pagina", aba="parametros"))


@vd_parametros_bp.get("/vendedor/parametros/fiscal")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_notas.ver")
def fiscal_dados():
    if (r := _vendedor()) is not None:
        return r
    tid = _tid()
    if not tid:
        return jsonify(success=False, message="Sessão sem tenant."), 401
    conn = Var_ConectarBanco()
    try:
        from sistema.fiscal.nfe_servico import ler_config

        return jsonify(success=True, **ler_config(conn.cursor(), tid))
    except Exception as e:
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@vd_parametros_bp.post("/vendedor/parametros/fiscal")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_notas.ver")
def fiscal_salvar():
    if (r := _vendedor()) is not None:
        return r
    tid = _tid()
    if not tid:
        return jsonify(success=False, message="Sessão sem tenant."), 401
    arquivo = None
    enviado = request.files.get("certificado")
    if enviado and enviado.filename:
        arquivo = (enviado.filename, enviado.read())
    body = request.form if request.form else (request.get_json(silent=True) or {})
    senha = (body.get("senha_certificado") or "").strip()
    conn = Var_ConectarBanco()
    try:
        from sistema.fiscal.nfe_servico import salvar_config, sincronizar_empresa

        cur = conn.cursor()
        dados = salvar_config(
            cur, tid, body, arquivo, senha,
            editar_regras=bool(session.get("eh_desenvolvedor")),
        )
        conn.commit()
        aviso = ""
        if dados.get("tem_certificado") and dados.get("token_configurado"):
            try:
                sincronizar_empresa(cur, tid)
                conn.commit()
                dados = {**dados, "focus_empresa_id": "ok"}
            except ValueError as e:
                conn.rollback()
                aviso = str(e)
                from sistema.fiscal.nfe_servico import ler_config

                dados = ler_config(conn.cursor(), tid)
        return jsonify(success=True, message="Parâmetros fiscais salvos.", aviso=aviso, **dados)
    except ValueError as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 400
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()
