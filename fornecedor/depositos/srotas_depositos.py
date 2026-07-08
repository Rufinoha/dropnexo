from __future__ import annotations

import json
import re

from pathlib import Path

from flask import Blueprint, jsonify, render_template, request, session

from global_utils import Var_ConectarBanco, agora_utc, exigir_modulo, exigir_permissao, login_obrigatorio
from sistema.plataforma.sessao import MODULO_FORNECEDOR
from core.dominio import inativar_vinculo


_MOD = Path(__file__).resolve().parent

fn_depositos_bp = Blueprint(
    "fn_depositos",
    __name__,
    root_path=str(_MOD),
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/fornecedor/depositos",
)


def init_app(app):
    app.register_blueprint(fn_depositos_bp)

def _id_tenant() -> int | None:
    tid = session.get("id_tenant")
    return int(tid) if tid else None


def _exigir_fornecedor_tenant():
    if session.get("tenant_tipo_negocio") in ("fornecedor", "hibrido") or session.get("eh_desenvolvedor"):
        return None
    return jsonify(success=False, message="Conta não é fornecedor."), 403

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
    }


_DEPOSITO_COLS = """
    id, nome, cep, logradouro, numero, complemento, bairro, cidade, uf,
    remetente_nome, remetente_documento, principal, ativo
"""

@fn_depositos_bp.get("/fornecedor/depositos")
@login_obrigatorio()
@exigir_modulo(MODULO_FORNECEDOR)
@exigir_permissao(codigo="catalogos.ver")
def depositos():
    if (r := _exigir_fornecedor_tenant()) is not None:
        return r
    return render_template("frm_fn_depositos.html", nav_ativo="fn_depositos")



@fn_depositos_bp.get("/fornecedor/depositos/dados")
@login_obrigatorio()
@exigir_modulo(MODULO_FORNECEDOR)
def depositos_dados():
    if (r := _exigir_fornecedor_tenant()) is not None:
        return r
    id_tenant = _id_tenant()
    if not id_tenant:
        return jsonify(success=False, message="Sessão inválida."), 403
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT {_DEPOSITO_COLS}
            FROM tbl_deposito_expedicao
            WHERE id_tenant = %s AND ativo = TRUE
            ORDER BY principal DESC, nome
            """,
            (id_tenant,),
        )
        dados = [_deposito_row_dict(row) for row in cur.fetchall()]
        return jsonify(success=True, dados=dados)
    finally:
        conn.close()



@fn_depositos_bp.post("/fornecedor/depositos/apoio")
@login_obrigatorio()
@exigir_modulo(MODULO_FORNECEDOR)
@exigir_permissao(codigo="catalogos.editar")
def depositos_apoio():
    if (r := _exigir_fornecedor_tenant()) is not None:
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



@fn_depositos_bp.post("/fornecedor/depositos/salvar")
@login_obrigatorio()
@exigir_modulo(MODULO_FORNECEDOR)
@exigir_permissao(codigo="catalogos.editar")
def depositos_salvar():
    if (r := _exigir_fornecedor_tenant()) is not None:
        return r
    id_tenant = _id_tenant()
    if not id_tenant:
        return jsonify(success=False, message="Sessão inválida."), 403

    body = request.get_json(silent=True) or {}
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
                "UPDATE tbl_deposito_expedicao SET principal = FALSE WHERE id_tenant = %s",
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
        dep_id = body.get("id")
        if dep_id:
            cur.execute(
                """
                UPDATE tbl_deposito_expedicao SET
                    nome=%s, cep=%s, logradouro=%s, numero=%s, complemento=%s,
                    bairro=%s, cidade=%s, uf=%s, remetente_nome=%s, remetente_documento=%s,
                    principal=%s, ativo=%s, atualizado_em=%s
                WHERE id=%s AND id_tenant=%s
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
                    principal, ativo, atualizado_em
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING id
                """,
                (id_tenant,) + campos,
            )
        row = cur.fetchone()
        conn.commit()
        return jsonify(success=True, id=row[0], message="Depósito salvo com sucesso.")
    except Exception as e:
        conn.rollback()
        if "unique" in str(e).lower():
            return jsonify(success=False, message="Já existe um depósito com este CEP."), 409
        raise
    finally:
        conn.close()



@fn_depositos_bp.post("/fornecedor/depositos/excluir")
@login_obrigatorio()
@exigir_modulo(MODULO_FORNECEDOR)
@exigir_permissao(codigo="catalogos.editar")
def depositos_excluir():
    if (r := _exigir_fornecedor_tenant()) is not None:
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
            "UPDATE tbl_produto SET id_deposito_expedicao = NULL WHERE id_deposito_expedicao = %s",
            (dep_id,),
        )
        cur.execute(
            "DELETE FROM tbl_deposito_expedicao WHERE id = %s AND id_tenant = %s",
            (dep_id, id_tenant),
        )
        if cur.rowcount == 0:
            return jsonify(success=False, message="Depósito não encontrado."), 404
        conn.commit()
        return jsonify(success=True, message="Depósito removido.")
    finally:
        conn.close()


def _stats_categorias_segmento(cur, id_tenant: int, id_segmento: int) -> tuple[list[dict], int, int]:
    """Retorna (categorias nível 1 para gráfico, total de nós na árvore, total de produtos)."""
    cur.execute(
        """
        SELECT COUNT(*)::int FROM tbl_categoria
        WHERE id_tenant = %s AND id_segmento = %s AND ativo = TRUE
        """,
        (id_tenant, id_segmento),
    )
    qtd_total = int(cur.fetchone()[0] or 0)

    cur.execute(
        """
        SELECT c.id, c.nome,
               (SELECT COUNT(*)::int FROM tbl_produto p
                WHERE p.id_categoria = c.id AND p.id_tenant = %s AND p.ativo = TRUE)
        FROM tbl_categoria c
        WHERE c.id_tenant = %s AND c.id_segmento = %s AND c.ativo = TRUE
          AND COALESCE(c.nivel, 1) = 1
        ORDER BY c.ordem, c.nome
        """,
        (id_tenant, id_tenant, id_segmento),
    )
    cats = []
    for cid, cnome, qtd in cur.fetchall():
        cats.append({"id": cid, "nome": cnome, "qtd_produtos": int(qtd or 0)})
    cur.execute(
        """
        SELECT COUNT(*)::int FROM tbl_produto p
        JOIN tbl_categoria c ON c.id = p.id_categoria
        WHERE p.id_tenant = %s AND c.id_segmento = %s AND p.ativo = TRUE
        """,
        (id_tenant, id_segmento),
    )
    total_prod = int(cur.fetchone()[0] or 0)
    return cats, qtd_total, total_prod

