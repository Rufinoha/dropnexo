from __future__ import annotations

from pathlib import Path

from flask import Blueprint, jsonify, render_template, request, session, url_for
from global_utils import exigir_modulo, exigir_permissao, login_obrigatorio, usuario_tem_permissao
from srotas_plataforma import PERFIS_EQUIPE_FORNECEDOR, carregar_usuario_apoio, inativar_usuario_tenant, listar_perfis_combo, listar_usuarios_tenant, normalizar_bool, reenviar_convite_usuario, salvar_usuario_tenant


_MOD = Path(__file__).resolve().parent

fn_usuarios_bp = Blueprint(
    "fn_usuarios",
    __name__,
    root_path=str(_MOD),
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/fornecedor/usuarios",
)


def init_app(app):
    app.register_blueprint(fn_usuarios_bp)


def _exigir_fornecedor_tenant():
    if session.get("tenant_tipo_negocio") in ("fornecedor", "hibrido") or session.get("eh_desenvolvedor"):
        return None
    return jsonify(success=False, message="Conta não é fornecedor."), 403


def _exigir_escrita():
    if session.get("eh_desenvolvedor") or usuario_tem_permissao("fn_usuarios.editar"):
        return None
    return jsonify(success=False, message="Sem permissão para gerenciar usuários."), 403



@fn_usuarios_bp.get("/fornecedor/usuarios")
@login_obrigatorio()
@exigir_modulo("fornecedor")
@exigir_permissao(codigo="fn_usuarios.ver")
def usuarios():
    if (r := _exigir_fornecedor_tenant()) is not None:
        return r
    return render_template("frm_fn_usuarios.html", nav_ativo="fn_usuarios")

@fn_usuarios_bp.get("/fornecedor/usuarios/dados")
@login_obrigatorio()
@exigir_modulo("fornecedor")
@exigir_permissao(codigo="fn_usuarios.ver")
def usuarios_dados():
    if (r := _exigir_fornecedor_tenant()) is not None:
        return r
    resultado = listar_usuarios_tenant(
        id_tenant=int(session["id_tenant"]),
        pagina=int(request.args.get("pagina", 1)),
        por_pagina=int(request.args.get("porPagina", 20)),
        busca=request.args.get("busca") or "",
        filtro_status=request.args.get("status") or "",
        filtro_convite=request.args.get("convite") or "",
        id_usuario_sessao=session.get("id_usuario"),
    )
    return jsonify(resultado)

@fn_usuarios_bp.get("/fornecedor/usuarios/combos")
@login_obrigatorio()
@exigir_modulo("fornecedor")
@exigir_permissao(codigo="fn_usuarios.ver")
def usuarios_combos():
    if (r := _exigir_fornecedor_tenant()) is not None:
        return r
    excluir = ("dono", "vendedor")
    perfis = listar_perfis_combo(excluir_codigos=excluir)
    perfis["perfis"] = [
        p for p in perfis.get("perfis", []) if p.get("codigo") in PERFIS_EQUIPE_FORNECEDOR
    ]
    return jsonify(perfis)

@fn_usuarios_bp.get("/fornecedor/usuarios/incluir")
@login_obrigatorio()
@exigir_modulo("fornecedor")
@exigir_permissao(codigo="fn_usuarios.editar")
def usuarios_incluir():
    if (r := _exigir_fornecedor_tenant()) is not None:
        return r
    return render_template("frm_fn_usuarios_apoio.html")

@fn_usuarios_bp.get("/fornecedor/usuarios/editar")
@login_obrigatorio()
@exigir_modulo("fornecedor")
@exigir_permissao(codigo="fn_usuarios.editar")
def usuarios_editar():
    if (r := _exigir_fornecedor_tenant()) is not None:
        return r
    return render_template("frm_fn_usuarios_apoio.html")

@fn_usuarios_bp.post("/fornecedor/usuarios/apoio")
@login_obrigatorio()
@exigir_modulo("fornecedor")
@exigir_permissao(codigo="fn_usuarios.ver")
def usuarios_apoio():
    if (r := _exigir_fornecedor_tenant()) is not None:
        return r
    uid = int((request.get_json(silent=True) or {}).get("id") or 0)
    if not uid:
        return jsonify(success=False, message="ID inválido."), 400
    payload, status = carregar_usuario_apoio(id_tenant=int(session["id_tenant"]), uid=uid)
    return jsonify(payload), status

@fn_usuarios_bp.post("/fornecedor/usuarios/salvar")
@login_obrigatorio()
@exigir_modulo("fornecedor")
@exigir_permissao(codigo="fn_usuarios.editar")
def usuarios_salvar():
    if (r := _exigir_fornecedor_tenant()) is not None:
        return r
    if (resp := _exigir_escrita()) is not None:
        return resp
    body = request.get_json(silent=True) or {}
    payload, status = salvar_usuario_tenant(
        id_tenant=int(session["id_tenant"]),
        uid=body.get("id"),
        email=body.get("email") or "",
        nome=body.get("nome") or "",
        whatsapp=body.get("whatsapp") or "",
        id_perfil=int(body.get("id_perfil") or 0),
        status=normalizar_bool(body.get("status"), True),
        enviar_convite=normalizar_bool(body.get("enviar_convite"), True),
    )
    return jsonify(payload), status

@fn_usuarios_bp.post("/fornecedor/usuarios/inativar")
@login_obrigatorio()
@exigir_modulo("fornecedor")
@exigir_permissao(codigo="fn_usuarios.editar")
def usuarios_inativar():
    if (r := _exigir_fornecedor_tenant()) is not None:
        return r
    if (resp := _exigir_escrita()) is not None:
        return resp
    uid = int((request.get_json(silent=True) or {}).get("id") or 0)
    payload, status = inativar_usuario_tenant(
        id_tenant=int(session["id_tenant"]),
        uid=uid,
        id_usuario_sessao=int(session.get("id_usuario") or 0),
    )
    return jsonify(payload), status

@fn_usuarios_bp.post("/fornecedor/usuarios/reenviar-convite")
@login_obrigatorio()
@exigir_modulo("fornecedor")
@exigir_permissao(codigo="fn_usuarios.editar")
def usuarios_reenviar_convite():
    if (r := _exigir_fornecedor_tenant()) is not None:
        return r
    if (resp := _exigir_escrita()) is not None:
        return resp
    uid = int((request.get_json(silent=True) or {}).get("id") or 0)
    payload, status = reenviar_convite_usuario(id_tenant=int(session["id_tenant"]), uid=uid)
    return jsonify(payload), status
