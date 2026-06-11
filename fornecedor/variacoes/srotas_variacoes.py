from __future__ import annotations

from pathlib import Path

from flask import Blueprint, jsonify, render_template, request, session, url_for
from global_utils import Var_ConectarBanco, agora_utc, exigir_modulo, exigir_permissao, login_obrigatorio


_MOD = Path(__file__).resolve().parent

fn_variacoes_bp = Blueprint(
    "fn_variacoes",
    __name__,
    root_path=str(_MOD),
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/fornecedor/variacoes",
)




def _exigir_fornecedor_tenant():
    if session.get("tenant_tipo_negocio") in ("fornecedor", "hibrido") or session.get("eh_desenvolvedor"):
        return None
    return jsonify(success=False, message="Conta não é fornecedor."), 403

def init_app(app):
    app.register_blueprint(fn_variacoes_bp)

# Modelos de variação pré-cadastrados (fornecedor)
import json
import re

from flask import jsonify, render_template, request, session

from global_utils import Var_ConectarBanco, agora_utc, exigir_modulo, exigir_permissao, login_obrigatorio




@fn_variacoes_bp.get("/fornecedor/variacoes")
@login_obrigatorio()
@exigir_modulo("fornecedor")
@exigir_permissao(codigo="fn_variacoes.ver")
def variacoes():
    
    if (r := _exigir_fornecedor_tenant()) is not None:
        return r
    return render_template("frm_fn_variacoes.html", nav_ativo="fn_variacoes")

@fn_variacoes_bp.get("/fornecedor/variacoes/dados")
@login_obrigatorio()
@exigir_permissao(codigo="fn_variacoes.ver")
def variacoes_dados():
    
    if (r := _exigir_fornecedor_tenant()) is not None:
        return r
    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, nome, descricao, atributos, ativo, atualizado_em
            FROM tbl_variacao_preset
            WHERE id_tenant = %s
            ORDER BY nome
            """,
            (id_tenant,),
        )
        linhas = []
        for r in cur.fetchall():
            atr = r[3] if isinstance(r[3], list) else (json.loads(r[3]) if r[3] else [])
            linhas.append(
                {
                    "id": r[0],
                    "nome": r[1],
                    "descricao": r[2] or "",
                    "atributos": atr,
                    "ativo": bool(r[4]),
                    "atualizado_em": r[5].isoformat() if r[5] else None,
                }
            )
        return jsonify(success=True, linhas=linhas)
    finally:
        conn.close()

@fn_variacoes_bp.post("/fornecedor/variacoes/salvar")
@login_obrigatorio()
@exigir_permissao(codigo="fn_variacoes.editar")
def variacoes_salvar():
    
    if (r := _exigir_fornecedor_tenant()) is not None:
        return r
    body = request.get_json(silent=True) or {}
    nome = (body.get("nome") or "").strip()
    if not nome:
        return jsonify(success=False, message="Informe o nome do modelo."), 400
    atributos = body.get("atributos") or []
    if not isinstance(atributos, list) or not atributos:
        return jsonify(success=False, message="Adicione ao menos um atributo com opções."), 400
    normalizados = []
    for i, item in enumerate(atributos):
        n = (item.get("nome") or "").strip()
        vals = item.get("valores") or []
        if isinstance(vals, str):
            vals = [s.strip() for s in re.split(r"[,;\n]+", vals) if s.strip()]
        vals = [str(v).strip() for v in vals if str(v).strip()]
        if n and vals:
            normalizados.append({"nome": n, "valores": vals, "ordem": i})
    if not normalizados:
        return jsonify(success=False, message="Atributos inválidos."), 400

    id_tenant = session.get("id_tenant")
    _id = body.get("id")
    descricao = (body.get("descricao") or "").strip() or None
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        if _id:
            cur.execute(
                """
                UPDATE tbl_variacao_preset SET
                    nome=%s, descricao=%s, atributos=%s, ativo=%s, atualizado_em=%s
                WHERE id=%s AND id_tenant=%s
                RETURNING id
                """,
                (
                    nome,
                    descricao,
                    json.dumps(normalizados, ensure_ascii=False),
                    bool(body.get("ativo", True)),
                    agora_utc(),
                    int(_id),
                    id_tenant,
                ),
            )
            row = cur.fetchone()
            if not row:
                return jsonify(success=False, message="Modelo não encontrado."), 404
            pid = row[0]
        else:
            cur.execute(
                """
                INSERT INTO tbl_variacao_preset (id_tenant, nome, descricao, atributos, ativo, atualizado_em)
                VALUES (%s, %s, %s, %s, TRUE, %s)
                RETURNING id
                """,
                (
                    id_tenant,
                    nome,
                    descricao,
                    json.dumps(normalizados, ensure_ascii=False),
                    agora_utc(),
                ),
            )
            pid = cur.fetchone()[0]
        conn.commit()
        return jsonify(success=True, message="Modelo salvo.", id=pid)
    except Exception as e:
        conn.rollback()
        err = str(e)
        if "uq_variacao_preset_tenant_nome" in err:
            return jsonify(success=False, message="Já existe um modelo com este nome."), 409
        return jsonify(success=False, message=err), 500
    finally:
        conn.close()

@fn_variacoes_bp.post("/fornecedor/variacoes/excluir")
@login_obrigatorio()
@exigir_permissao(codigo="fn_variacoes.editar")
def variacoes_excluir():
    
    if (r := _exigir_fornecedor_tenant()) is not None:
        return r
    _id = int((request.get_json(silent=True) or {}).get("id") or 0)
    if not _id:
        return jsonify(success=False, message="ID inválido."), 400
    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE tbl_variacao_preset SET ativo = FALSE, atualizado_em = %s WHERE id = %s AND id_tenant = %s",
            (agora_utc(), _id, id_tenant),
        )
        conn.commit()
        if cur.rowcount == 0:
            return jsonify(success=False, message="Modelo não encontrado."), 404
        return jsonify(success=True, message="Modelo removido.")
    finally:
        conn.close()
