# api/pix_manual/srotas_pix_manual.py
from __future__ import annotations

from pathlib import Path

from flask import Blueprint, jsonify, request, session

from api.pix_manual.pix_manual import (
    carregar_config_pix_manual,
    desativar_pix_manual,
    pix_manual_ativo,
    salvar_config_pix_manual,
)
from global_utils import Var_ConectarBanco, login_obrigatorio
from sistema.plataforma.sessao import MODULO_FORNECEDOR, garantir_modulo_sessao

_MOD = Path(__file__).resolve().parent
pix_manual_bp = Blueprint(
    "pix_manual",
    __name__,
    root_path=str(_MOD),
    static_folder="static",
    static_url_path="/static/api/pixmanual",
)


def init_app(app):
    app.register_blueprint(pix_manual_bp)


def _id_tenant() -> int | None:
    tid = session.get("id_tenant")
    return int(tid) if tid else None


def _exigir_fornecedor():
    if session.get("eh_desenvolvedor"):
        return None
    if garantir_modulo_sessao() == MODULO_FORNECEDOR:
        return None
    return jsonify(success=False, message="Apenas fornecedores."), 403


@pix_manual_bp.get("/api/integracoes/pix-manual/status")
@login_obrigatorio()
def pix_manual_status():
    if (resp := _exigir_fornecedor()) is not None:
        return resp
    id_t = _id_tenant()
    if not id_t:
        return jsonify(success=False, message="Sessão inválida."), 403
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cfg = carregar_config_pix_manual(cur, id_t)
        cfg["conectado"] = pix_manual_ativo(cur, id_t)
        return jsonify(success=True, **cfg)
    finally:
        conn.close()


@pix_manual_bp.post("/api/integracoes/pix-manual/salvar")
@login_obrigatorio()
def pix_manual_salvar():
    if (resp := _exigir_fornecedor()) is not None:
        return resp
    id_t = _id_tenant()
    if not id_t:
        return jsonify(success=False, message="Sessão inválida."), 403
    body = request.get_json(silent=True) or {}
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        salvar_config_pix_manual(
            cur,
            id_t,
            ativo=bool(body.get("ativo", True)),
            tipo_chave=body.get("tipo_chave") or "aleatoria",
            chave_pix=body.get("chave_pix") or "",
            nome_beneficiario=body.get("nome_beneficiario") or "",
            cidade_beneficiario=body.get("cidade_beneficiario") or "",
        )
        conn.commit()
        return jsonify(success=True, message="PIX manual salvo.")
    except ValueError as e:
        return jsonify(success=False, message=str(e)), 400
    finally:
        conn.close()


@pix_manual_bp.post("/api/integracoes/pix-manual/desativar")
@login_obrigatorio()
def pix_manual_desativar():
    if (resp := _exigir_fornecedor()) is not None:
        return resp
    id_t = _id_tenant()
    if not id_t:
        return jsonify(success=False, message="Sessão inválida."), 403
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        desativar_pix_manual(cur, id_t)
        conn.commit()
        return jsonify(success=True, message="PIX manual desativado.")
    finally:
        conn.close()
