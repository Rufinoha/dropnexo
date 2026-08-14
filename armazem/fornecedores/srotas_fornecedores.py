# armazem/fornecedores — cadastro local de fornecedores do armazém
from __future__ import annotations

import re
from pathlib import Path

from flask import Blueprint, jsonify, render_template, request, session

from global_utils import Var_ConectarBanco, agora_utc, exigir_modulo, exigir_permissao, login_obrigatorio
from sistema.plataforma.sessao import MODULO_ARMAZEM

_MOD = Path(__file__).resolve().parent

az_fornecedores_bp = Blueprint(
    "az_fornecedores",
    __name__,
    root_path=str(_MOD),
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/armazem/fornecedores",
)


def init_app(app):
    app.register_blueprint(az_fornecedores_bp)


def _id_tenant() -> int | None:
    tid = session.get("id_tenant")
    return int(tid) if tid else None


def _exigir_armazem_tenant():
    if session.get("tenant_tipo_negocio") in ("armazem",) or session.get("eh_desenvolvedor"):
        return None
    return jsonify(success=False, message="Conta não é armazém."), 403


def _so_digitos(v: str) -> str:
    return re.sub(r"\D", "", v or "")


def garantir_tabela_fornecedor_armazem(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tbl_armazem_fornecedor (
            id BIGSERIAL PRIMARY KEY,
            id_tenant_armazem BIGINT NOT NULL REFERENCES tbl_tenant(id) ON DELETE CASCADE,
            nome VARCHAR(200) NOT NULL,
            nome_fantasia VARCHAR(200),
            documento VARCHAR(20),
            email VARCHAR(200),
            telefone VARCHAR(30),
            whatsapp VARCHAR(30),
            observacoes TEXT,
            ativo BOOLEAN NOT NULL DEFAULT TRUE,
            criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_armazem_fornecedor_tenant
          ON tbl_armazem_fornecedor (id_tenant_armazem)
        """
    )


def _row_dict(row) -> dict:
    return {
        "id": row[0],
        "nome": row[1] or "",
        "nome_fantasia": row[2] or "",
        "documento": row[3] or "",
        "email": row[4] or "",
        "telefone": row[5] or "",
        "whatsapp": row[6] or "",
        "observacoes": row[7] or "",
        "ativo": bool(row[8]),
    }


_COLS = """
    id, nome, nome_fantasia, documento, email, telefone, whatsapp, observacoes, ativo
"""


@az_fornecedores_bp.get("/armazem/fornecedores")
@login_obrigatorio()
@exigir_modulo(MODULO_ARMAZEM)
@exigir_permissao(codigo="az_fornecedores.ver")
def pagina():
    if (r := _exigir_armazem_tenant()) is not None:
        return r
    return render_template("frm_az_fornecedores.html", nav_ativo="az_fornecedores")


@az_fornecedores_bp.get("/armazem/fornecedores/dados")
@login_obrigatorio()
@exigir_modulo(MODULO_ARMAZEM)
@exigir_permissao(codigo="az_fornecedores.ver")
def dados():
    if (r := _exigir_armazem_tenant()) is not None:
        return r
    id_tenant = _id_tenant()
    if not id_tenant:
        return jsonify(success=False, message="Sessão inválida."), 403
    busca = (request.args.get("busca") or "").strip()
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        garantir_tabela_fornecedor_armazem(cur)
        conn.commit()
        params: list = [id_tenant]
        where = "id_tenant_armazem = %s AND ativo = TRUE"
        if busca:
            where += " AND (nome ILIKE %s OR nome_fantasia ILIKE %s OR documento ILIKE %s)"
            like = f"%{busca}%"
            params.extend([like, like, like])
        cur.execute(
            f"""
            SELECT {_COLS}
            FROM tbl_armazem_fornecedor
            WHERE {where}
            ORDER BY COALESCE(NULLIF(nome_fantasia, ''), nome)
            """,
            params,
        )
        return jsonify(success=True, dados=[_row_dict(r) for r in cur.fetchall()])
    finally:
        conn.close()


@az_fornecedores_bp.post("/armazem/fornecedores/apoio")
@login_obrigatorio()
@exigir_modulo(MODULO_ARMAZEM)
@exigir_permissao(codigo="az_fornecedores.editar")
def apoio():
    if (r := _exigir_armazem_tenant()) is not None:
        return r
    id_tenant = _id_tenant()
    body = request.get_json(silent=True) or {}
    fid = body.get("id")
    if not fid:
        return jsonify(success=True, dados=None)
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        garantir_tabela_fornecedor_armazem(cur)
        cur.execute(
            f"""
            SELECT {_COLS}
            FROM tbl_armazem_fornecedor
            WHERE id = %s AND id_tenant_armazem = %s
            """,
            (int(fid), id_tenant),
        )
        row = cur.fetchone()
        if not row:
            return jsonify(success=False, message="Fornecedor não encontrado."), 404
        return jsonify(success=True, dados=_row_dict(row))
    finally:
        conn.close()


@az_fornecedores_bp.post("/armazem/fornecedores/salvar")
@login_obrigatorio()
@exigir_modulo(MODULO_ARMAZEM)
@exigir_permissao(codigo="az_fornecedores.editar")
def salvar():
    if (r := _exigir_armazem_tenant()) is not None:
        return r
    id_tenant = _id_tenant()
    if not id_tenant:
        return jsonify(success=False, message="Sessão inválida."), 403
    body = request.get_json(silent=True) or {}
    nome = (body.get("nome") or "").strip()
    if len(nome) < 2:
        return jsonify(success=False, message="Informe o nome do fornecedor."), 400
    fantasia = (body.get("nome_fantasia") or "").strip() or None
    documento = _so_digitos(body.get("documento") or "") or None
    email = (body.get("email") or "").strip() or None
    telefone = _so_digitos(body.get("telefone") or "") or None
    whatsapp = _so_digitos(body.get("whatsapp") or "") or None
    obs = (body.get("observacoes") or "").strip() or None
    ativo = bool(body.get("ativo", True))
    agora = agora_utc()

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        garantir_tabela_fornecedor_armazem(cur)
        fid = body.get("id")
        if fid:
            cur.execute(
                """
                UPDATE tbl_armazem_fornecedor SET
                    nome=%s, nome_fantasia=%s, documento=%s, email=%s,
                    telefone=%s, whatsapp=%s, observacoes=%s, ativo=%s, atualizado_em=%s
                WHERE id=%s AND id_tenant_armazem=%s
                RETURNING id
                """,
                (
                    nome,
                    fantasia,
                    documento,
                    email,
                    telefone,
                    whatsapp,
                    obs,
                    ativo,
                    agora,
                    int(fid),
                    id_tenant,
                ),
            )
        else:
            cur.execute(
                """
                INSERT INTO tbl_armazem_fornecedor (
                    id_tenant_armazem, nome, nome_fantasia, documento, email,
                    telefone, whatsapp, observacoes, ativo, atualizado_em
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING id
                """,
                (
                    id_tenant,
                    nome,
                    fantasia,
                    documento,
                    email,
                    telefone,
                    whatsapp,
                    obs,
                    ativo,
                    agora,
                ),
            )
        row = cur.fetchone()
        if not row:
            return jsonify(success=False, message="Fornecedor não encontrado."), 404
        conn.commit()
        return jsonify(success=True, id=row[0], message="Fornecedor salvo.")
    finally:
        conn.close()


@az_fornecedores_bp.post("/armazem/fornecedores/excluir")
@login_obrigatorio()
@exigir_modulo(MODULO_ARMAZEM)
@exigir_permissao(codigo="az_fornecedores.editar")
def excluir():
    if (r := _exigir_armazem_tenant()) is not None:
        return r
    id_tenant = _id_tenant()
    body = request.get_json(silent=True) or {}
    try:
        fid = int(body.get("id"))
    except (TypeError, ValueError):
        return jsonify(success=False, message="Fornecedor inválido."), 400
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        garantir_tabela_fornecedor_armazem(cur)
        cur.execute(
            """
            UPDATE tbl_armazem_fornecedor
            SET ativo = FALSE, atualizado_em = %s
            WHERE id = %s AND id_tenant_armazem = %s
            """,
            (agora_utc(), fid, id_tenant),
        )
        if cur.rowcount == 0:
            return jsonify(success=False, message="Fornecedor não encontrado."), 404
        conn.commit()
        return jsonify(success=True, message="Fornecedor removido.")
    finally:
        conn.close()
