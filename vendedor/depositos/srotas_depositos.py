from __future__ import annotations

import re

from pathlib import Path

from flask import Blueprint, jsonify, render_template, request, session

from global_utils import Var_ConectarBanco, agora_utc, exigir_modulo, exigir_permissao, login_obrigatorio
from sistema.plataforma.sessao import MODULO_VENDEDOR
from vendedor.meus_produtos.servico_deposito_vendedor import sincronizar_espelhos_integrados

_MOD = Path(__file__).resolve().parent

vd_depositos_bp = Blueprint(
    "vd_depositos",
    __name__,
    root_path=str(_MOD),
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/vendedor/depositos",
)


def init_app(app):
    app.register_blueprint(vd_depositos_bp)


def _id_tenant() -> int | None:
    tid = session.get("id_tenant")
    return int(tid) if tid else None


def _exigir_vendedor_tenant():
    if session.get("tenant_tipo_negocio") in ("vendedor", "hibrido") or session.get("eh_desenvolvedor"):
        return None
    return jsonify(success=False, message="Conta não é vendedor."), 403


def _so_digitos(v: str) -> str:
    return re.sub(r"\D", "", v or "")


def _deposito_row_dict(row) -> dict:
    return {
        "id": row[0],
        "nome": row[1],
        "cep": row[2],
        "logradouro": row[3],
        "numero": row[4],
        "complemento": row[5] or "",
        "bairro": row[6],
        "cidade": row[7],
        "uf": row[8],
        "remetente_nome": row[9] or "",
        "remetente_documento": row[10] or "",
        "principal": bool(row[11]),
        "ativo": bool(row[12]),
        "espelho_somente_leitura": bool(row[13]) if len(row) > 13 else False,
        "id_deposito_espelho": row[14] if len(row) > 14 else None,
    }


_DEPOSITO_COLS = """
    id, nome, cep, logradouro, numero, complemento, bairro, cidade, uf,
    remetente_nome, remetente_documento, principal, ativo,
    espelho_somente_leitura, id_deposito_espelho
"""


@vd_depositos_bp.get("/vendedor/depositos")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_depositos.ver")
def depositos():
    if (r := _exigir_vendedor_tenant()) is not None:
        return r
    return render_template("frm_vd_depositos.html", nav_ativo="vd_depositos")


@vd_depositos_bp.get("/vendedor/depositos/dados")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_depositos.ver")
def depositos_dados():
    if (r := _exigir_vendedor_tenant()) is not None:
        return r
    id_tenant = _id_tenant()
    if not id_tenant:
        return jsonify(success=False, message="Sessão inválida."), 403
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        sincronizar_espelhos_integrados(cur, id_tenant)
        conn.commit()
        cur.execute(
            f"""
            SELECT {_DEPOSITO_COLS}
            FROM tbl_deposito_expedicao
            WHERE id_tenant = %s AND ativo = TRUE
            ORDER BY espelho_somente_leitura DESC, principal DESC, nome
            """,
            (id_tenant,),
        )
        dados = [_deposito_row_dict(row) for row in cur.fetchall()]
        return jsonify(success=True, dados=dados)
    finally:
        conn.close()


@vd_depositos_bp.post("/vendedor/depositos/apoio")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_depositos.ver")
def depositos_apoio():
    if (r := _exigir_vendedor_tenant()) is not None:
        return r
    id_tenant = _id_tenant()
    body = request.get_json(silent=True) or {}
    dep_id = body.get("id")
    if not dep_id:
        return jsonify(success=True, dados=None)
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT {_DEPOSITO_COLS}
            FROM tbl_deposito_expedicao
            WHERE id = %s AND id_tenant = %s
            """,
            (int(dep_id), id_tenant),
        )
        row = cur.fetchone()
        if not row:
            return jsonify(success=False, message="Depósito não encontrado."), 404
        return jsonify(success=True, dados=_deposito_row_dict(row))
    finally:
        conn.close()


@vd_depositos_bp.post("/vendedor/depositos/salvar")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_depositos.editar")
def depositos_salvar():
    if (r := _exigir_vendedor_tenant()) is not None:
        return r
    id_tenant = _id_tenant()
    if not id_tenant:
        return jsonify(success=False, message="Sessão inválida."), 403

    body = request.get_json(silent=True) or {}
    dep_id = body.get("id")
    if dep_id:
        conn = Var_ConectarBanco()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT espelho_somente_leitura FROM tbl_deposito_expedicao
                WHERE id = %s AND id_tenant = %s
                """,
                (int(dep_id), id_tenant),
            )
            row = cur.fetchone()
            if row and bool(row[0]):
                return jsonify(
                    success=False,
                    message="Depósito espelhado do fornecedor — somente leitura.",
                ), 403
        finally:
            conn.close()

    cep = _so_digitos(body.get("cep") or "")
    if len(cep) != 8:
        return jsonify(success=False, message="Informe um CEP válido (8 dígitos)."), 400
    nome_dep = (body.get("nome") or "").strip() or "Depósito"
    log = (body.get("logradouro") or "").strip()
    bairro = (body.get("bairro") or "").strip()
    cidade = (body.get("cidade") or "").strip()
    uf = (body.get("uf") or "").strip()[:2].upper()
    if not log or not bairro or not cidade or len(uf) != 2:
        return jsonify(success=False, message="Preencha o endereço (use Buscar CEP ou informe manualmente)."), 400

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        principal = bool(body.get("principal"))
        if principal:
            cur.execute(
                """
                UPDATE tbl_deposito_expedicao SET principal = FALSE
                WHERE id_tenant = %s AND espelho_somente_leitura = FALSE
                """,
                (id_tenant,),
            )
        campos = (
            nome_dep,
            cep,
            log,
            (body.get("numero") or "S/N").strip(),
            (body.get("complemento") or "").strip() or None,
            bairro,
            cidade,
            uf,
            (body.get("remetente_nome") or "").strip() or None,
            _so_digitos(body.get("remetente_documento") or "") or None,
            principal,
            bool(body.get("ativo", True)),
            agora_utc(),
        )
        if dep_id:
            cur.execute(
                """
                UPDATE tbl_deposito_expedicao SET
                    nome=%s, cep=%s, logradouro=%s, numero=%s, complemento=%s,
                    bairro=%s, cidade=%s, uf=%s, remetente_nome=%s, remetente_documento=%s,
                    principal=%s, ativo=%s, atualizado_em=%s
                WHERE id=%s AND id_tenant=%s AND espelho_somente_leitura = FALSE
                RETURNING id
                """,
                campos + (int(dep_id), id_tenant),
            )
        else:
            cur.execute(
                """
                INSERT INTO tbl_deposito_expedicao (
                    id_tenant, nome, cep, logradouro, numero, complemento,
                    bairro, cidade, uf, remetente_nome, remetente_documento,
                    principal, ativo, espelho_somente_leitura, atualizado_em
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,FALSE,%s)
                RETURNING id
                """,
                (id_tenant,) + campos,
            )
        row = cur.fetchone()
        if not row:
            return jsonify(success=False, message="Depósito não encontrado ou é espelho."), 404
        conn.commit()
        return jsonify(success=True, id=row[0], message="Depósito salvo com sucesso.")
    except Exception as e:
        conn.rollback()
        if "unique" in str(e).lower():
            return jsonify(success=False, message="Já existe um depósito com este CEP."), 409
        raise
    finally:
        conn.close()


@vd_depositos_bp.post("/vendedor/depositos/excluir")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_depositos.editar")
def depositos_excluir():
    if (r := _exigir_vendedor_tenant()) is not None:
        return r
    id_tenant = _id_tenant()
    body = request.get_json(silent=True) or {}
    try:
        dep_id = int(body.get("id"))
    except (TypeError, ValueError):
        return jsonify(success=False, message="Depósito inválido."), 400

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT espelho_somente_leitura FROM tbl_deposito_expedicao
            WHERE id = %s AND id_tenant = %s
            """,
            (dep_id, id_tenant),
        )
        row = cur.fetchone()
        if not row:
            return jsonify(success=False, message="Depósito não encontrado."), 404
        if bool(row[0]):
            return jsonify(success=False, message="Não é possível excluir depósito espelhado do fornecedor."), 403
        cur.execute(
            "UPDATE tbl_produto SET id_deposito_expedicao = NULL WHERE id_deposito_expedicao = %s",
            (dep_id,),
        )
        cur.execute(
            "DELETE FROM tbl_deposito_expedicao WHERE id = %s AND id_tenant = %s",
            (dep_id, id_tenant),
        )
        conn.commit()
        return jsonify(success=True, message="Depósito removido.")
    finally:
        conn.close()
