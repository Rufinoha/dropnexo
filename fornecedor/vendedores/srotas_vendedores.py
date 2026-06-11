from __future__ import annotations

import json
import re

from pathlib import Path

from flask import Blueprint, jsonify, render_template, request, session

from global_utils import Var_ConectarBanco, agora_utc, exigir_modulo, exigir_permissao, login_obrigatorio
from srotas_plataforma import MODULO_FORNECEDOR
from srotas_negocio import inativar_vinculo


_MOD = Path(__file__).resolve().parent

fn_vendedores_bp = Blueprint(
    "fn_vendedores",
    __name__,
    root_path=str(_MOD),
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/fornecedor/vendedores",
)


def init_app(app):
    app.register_blueprint(fn_vendedores_bp)

def _id_tenant() -> int | None:
    tid = session.get("id_tenant")
    return int(tid) if tid else None


def _exigir_fornecedor_tenant():
    if session.get("tenant_tipo_negocio") in ("fornecedor", "hibrido") or session.get("eh_desenvolvedor"):
        return None
    return jsonify(success=False, message="Conta não é fornecedor."), 403

@fn_vendedores_bp.get("/fornecedor/vendedores")
@login_obrigatorio()
@exigir_modulo(MODULO_FORNECEDOR)
@exigir_permissao(codigo="fn_vendedores.ver")
def vendedores():
    if (r := _exigir_fornecedor_tenant()) is not None:
        return r
    return render_template("frm_fn_vendedores.html", nav_ativo="fn_vendedores")



@fn_vendedores_bp.get("/fornecedor/vendedores/dados")
@login_obrigatorio()
@exigir_modulo(MODULO_FORNECEDOR)
def vendedores_dados():
    if (r := _exigir_fornecedor_tenant()) is not None:
        return r
    id_forn = _id_tenant()
    if not id_forn:
        return jsonify(success=False, message="Sessão inválida."), 403
    status = (request.args.get("status") or "").strip()
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        where = ["v.id_tenant_fornecedor = %s"]
        params: list = [id_forn]
        if status:
            where.append("v.status = %s")
            params.append(status)
        cur.execute(
            f"""
            SELECT v.id, v.status, v.solicitado_em, v.respondido_em,
                   t.nome, t.cidade, t.uf, t.email_comercial, t.telefone_comercial,
                   v.snapshot_vendedor
            FROM tbl_vinculo_vendedor_fornecedor v
            JOIN tbl_tenant t ON t.id = v.id_tenant_vendedor
            WHERE {' AND '.join(where)}
            ORDER BY v.solicitado_em DESC
            LIMIT 200
            """,
            params,
        )
        dados = []
        for row in cur.fetchall():
            snap = row[9]
            if isinstance(snap, str):
                try:
                    snap = json.loads(snap)
                except Exception:
                    snap = {}
            dados.append(
                {
                    "id": row[0],
                    "status": row[1],
                    "solicitado_em": row[2].isoformat() if row[2] else "",
                    "respondido_em": row[3].isoformat() if row[3] else "",
                    "nome": row[4],
                    "cidade": row[5] or "",
                    "uf": row[6] or "",
                    "email": row[7] or "",
                    "telefone": row[8] or "",
                    "snapshot": snap or {},
                }
            )
        return jsonify(success=True, dados=dados)
    finally:
        conn.close()



@fn_vendedores_bp.post("/fornecedor/vendedores/responder")
@login_obrigatorio()
@exigir_modulo(MODULO_FORNECEDOR)
@exigir_permissao(codigo="fn_vendedores.editar")
def vendedores_responder():
    if (r := _exigir_fornecedor_tenant()) is not None:
        return r
    id_forn = _id_tenant()
    body = request.get_json(silent=True) or {}
    try:
        id_vinculo = int(body.get("id"))
    except (TypeError, ValueError):
        return jsonify(success=False, message="Vínculo inválido."), 400
    acao = (body.get("acao") or "").strip().lower()
    if acao not in ("aprovar", "recusar", "inativar"):
        return jsonify(success=False, message="Ação inválida."), 400

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        if acao == "inativar":
            inativar_vinculo(cur, id_vinculo, id_forn)
            conn.commit()
            return jsonify(success=True, message="Vínculo encerrado. Produtos desativados e estoque zerado na vitrine.")

        novo = "ativo" if acao == "aprovar" else "recusado"
        cur.execute(
            """
            UPDATE tbl_vinculo_vendedor_fornecedor
            SET status = %s, respondido_em = NOW(),
                mensagem_resposta = %s
            WHERE id = %s AND id_tenant_fornecedor = %s AND status = 'aguardando'
            """,
            (novo, (body.get("mensagem") or "").strip() or None, id_vinculo, id_forn),
        )
        if cur.rowcount == 0:
            return jsonify(success=False, message="Solicitação não encontrada ou já respondida."), 404
        conn.commit()
        msg = "Vendedor aprovado." if novo == "ativo" else "Solicitação recusada."
        return jsonify(success=True, message=msg)
    finally:
        conn.close()
