# armazem/parametros — visibilidade A/B e requisitos comerciais do armazém
from __future__ import annotations

from pathlib import Path

from flask import Blueprint, jsonify, render_template, request, session

from global_utils import Var_ConectarBanco, exigir_modulo, exigir_permissao, login_obrigatorio
from sistema.plataforma.sessao import MODULO_ARMAZEM

_MOD = Path(__file__).resolve().parent

az_parametros_bp = Blueprint(
    "az_parametros",
    __name__,
    root_path=str(_MOD),
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/armazem/parametros",
)

MODO_VITRINE_ARMAZEM = "armazem"
MODO_VITRINE_FORNECEDORES = "fornecedores"


def init_app(app):
    app.register_blueprint(az_parametros_bp)


def _id_tenant() -> int:
    return int(session["id_tenant"])


def _exigir_armazem_tenant():
    if session.get("tenant_tipo_negocio") in ("armazem",) or session.get("eh_desenvolvedor"):
        return None
    return jsonify(success=False, message="Conta não é armazém."), 403


def garantir_tabela_parametros(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tbl_armazem_parametros (
            id_tenant BIGINT PRIMARY KEY REFERENCES tbl_tenant(id) ON DELETE CASCADE,
            modo_vitrine VARCHAR(20) NOT NULL DEFAULT 'armazem',
            visivel_rede_vendedor BOOLEAN NOT NULL DEFAULT FALSE,
            aprovacao_automatica BOOLEAN NOT NULL DEFAULT FALSE,
            texto_adicional TEXT,
            atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT tbl_armazem_parametros_modo_check
              CHECK (modo_vitrine IN ('armazem', 'fornecedores'))
        )
        """
    )


def carregar_parametros(cur, id_tenant: int) -> dict:
    garantir_tabela_parametros(cur)
    cur.execute(
        """
        SELECT modo_vitrine, visivel_rede_vendedor, aprovacao_automatica, texto_adicional
        FROM tbl_armazem_parametros
        WHERE id_tenant = %s
        """,
        (id_tenant,),
    )
    row = cur.fetchone()
    if not row:
        return {
            "modo_vitrine": MODO_VITRINE_ARMAZEM,
            "visivel_rede_vendedor": False,
            "aprovacao_automatica": False,
            "texto_adicional": "",
        }
    return {
        "modo_vitrine": (row[0] or MODO_VITRINE_ARMAZEM).strip().lower(),
        "visivel_rede_vendedor": bool(row[1]),
        "aprovacao_automatica": bool(row[2]),
        "texto_adicional": row[3] or "",
    }


@az_parametros_bp.get("/armazem/parametros")
@login_obrigatorio()
@exigir_modulo(MODULO_ARMAZEM)
@exigir_permissao(codigo="az_parametros.ver")
def parametros_pagina():
    if (r := _exigir_armazem_tenant()) is not None:
        return r
    return render_template("frm_az_parametros.html", nav_ativo="az_parametros")


@az_parametros_bp.get("/armazem/parametros/dados")
@login_obrigatorio()
@exigir_modulo(MODULO_ARMAZEM)
@exigir_permissao(codigo="az_parametros.ver")
def parametros_dados():
    if (r := _exigir_armazem_tenant()) is not None:
        return r
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        dados = carregar_parametros(cur, _id_tenant())
        conn.commit()
        return jsonify(success=True, parametros=dados)
    finally:
        conn.close()


@az_parametros_bp.post("/armazem/parametros/salvar")
@login_obrigatorio()
@exigir_modulo(MODULO_ARMAZEM)
@exigir_permissao(codigo="az_parametros.editar")
def parametros_salvar():
    if (r := _exigir_armazem_tenant()) is not None:
        return r
    body = request.get_json(silent=True) or {}
    modo = (body.get("modo_vitrine") or MODO_VITRINE_ARMAZEM).strip().lower()
    if modo not in (MODO_VITRINE_ARMAZEM, MODO_VITRINE_FORNECEDORES):
        return jsonify(success=False, message="Modo de vitrine inválido."), 400
    visivel = bool(body.get("visivel_rede_vendedor"))
    auto = bool(body.get("aprovacao_automatica"))
    texto = (body.get("texto_adicional") or "").strip() or None
    id_tenant = _id_tenant()
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        garantir_tabela_parametros(cur)
        cur.execute(
            """
            INSERT INTO tbl_armazem_parametros (
                id_tenant, modo_vitrine, visivel_rede_vendedor,
                aprovacao_automatica, texto_adicional, atualizado_em
            ) VALUES (%s, %s, %s, %s, %s, NOW())
            ON CONFLICT (id_tenant) DO UPDATE SET
                modo_vitrine = EXCLUDED.modo_vitrine,
                visivel_rede_vendedor = EXCLUDED.visivel_rede_vendedor,
                aprovacao_automatica = EXCLUDED.aprovacao_automatica,
                texto_adicional = EXCLUDED.texto_adicional,
                atualizado_em = NOW()
            """,
            (id_tenant, modo, visivel, auto, texto),
        )
        conn.commit()
        return jsonify(
            success=True,
            message="Parâmetros salvos.",
            parametros=carregar_parametros(cur, id_tenant),
        )
    finally:
        conn.close()
